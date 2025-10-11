#api_app.py
import os
from flask import Flask, request, jsonify, render_template
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import TextMessage, MessageEvent, StickerMessage, ImageMessage 
from linebot.models import TextSendMessage
from dotenv import load_dotenv
import requests
import json
import sqlite3

# from database import initialize_database, add_new_task, get_credentials, add_credentials, get_tasks_by_status, update_task_status, update_admin_response, update_task_response, get_auto_reply_setting, update_auto_reply_setting, get_chat_history
from database import initialize_database, add_new_task, get_credentials, add_credentials, get_tasks_by_status, update_task_status, update_admin_response, update_task_response, get_auto_reply_setting, update_auto_reply_setting, get_chat_history, get_chat_threads_by_status
from ai_processor import process_new_tasks,process_new_tasks_using_sql_and_RAG
# from database import initialize_database, add_new_task, get_credentials, add_credentials, get_tasks_by_status, update_task_status, update_admin_response, update_task_response, get_auto_reply_setting, update_auto_reply_setting
# --- 1. Flask App and Database Setup ---
load_dotenv()
app = Flask(__name__)
DB_FILE_NAME = "store_database.db"
initialize_database()

# --- 2. LINE Messaging API Webhook Update Function ---
def update_line_webhook(access_token, webhook_url):
    """
    Updates the webhook URL for a given LINE channel.
    """
    try:
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        data = { "endpoint": webhook_url }
        api_url = "https://api.line.me/v2/bot/channel/webhook/endpoint"
        response = requests.put(api_url, headers=headers, json=data)
        response.raise_for_status()
        print(f"Webhook URL updated successfully to {webhook_url}")
        return True, "Webhook URL updated successfully."
    except requests.exceptions.HTTPError as err:
        error_details = err.response.json()
        print(f"LINE API Error: {error_details}")
        return False, f"LINE API Error: {error_details.get('message', 'Unknown error')}"
    except Exception as e:
        print(f"Error updating webhook URL: {e}")
        return False, "Error updating LINE webhook URL."

# --- 3. Flask Routes ---

@app.route('/')
def setup():
    """
    Serves the setup page (setup.html) for entering LINE Channel credentials.
    """
    return render_template('setup.html')

@app.route('/api/chat_history/<user_id>/<line_id>')
def get_chat_history_api(user_id, line_id):
    """API endpoint to get chat history for a specific LINE user."""
    history = get_chat_history(user_id, line_id)
    return jsonify(history)


@app.route('/dashboard/<user_id>')
def dashboard(user_id):
    """
    Serves the dashboard page (dashboard.html) for a specific store (user).
    """
    credentials_data = get_credentials(user_id)
    if not credentials_data:
        return "Credentials not found. Please set up your channel first.", 404
    return render_template('dashboard.html', user_id=user_id)

@app.route('/save_credentials/<user_id>', methods=['POST'])
def save_credentials(user_id):
    """
    Receives user credentials, saves them to SQLite, and updates the webhook.
    """
    print(f"--- Received POST request for user: {user_id} ---")
    try:
        data = request.json
        channel_secret = data.get('channelSecret')
        channel_access_token = data.get('channelAccessToken')

        print(f"Received data: Channel Secret: {channel_secret}, Channel Access Token: {channel_access_token}")

        if not channel_secret or not channel_access_token:
            print("Missing Channel Secret or Access Token.")
            return jsonify({'message': 'Missing Channel Secret or Access Token.'}), 400

        if not add_credentials(user_id, channel_secret, channel_access_token):
            print("Failed to save credentials to database.")
            return jsonify({'message': 'Failed to save credentials to database.'}), 500

        # Ensure BASE_URL is set in your .env file
        base_url = os.getenv('BASE_URL')
        if not base_url:
            return jsonify({'message': 'BASE_URL environment variable is not set.'}), 500
        
        webhook_url = f"{base_url}/webhook/{user_id}"
        print(f"Generated webhook_url: {webhook_url}")

        success, message = update_line_webhook(channel_access_token, webhook_url)
        response = { 'message': message, 'webhook_url': webhook_url }
        if success:
            return jsonify(response), 200
        else:
            return jsonify(response), 500

    except Exception as e:
        print(f"Error saving credentials: {e}")
        return jsonify({'message': f'Internal Server Error: {e}'}), 500

@app.route('/api/tasks/<user_id>/<status>')
def get_tasks(user_id, status):
    """
    Updated API endpoint to get unique chat threads based on the latest message's status.
    """
    # เปลี่ยนการเรียกใช้ฟังก์ชันจาก get_tasks_by_status เป็น get_chat_threads_by_status
    tasks = get_chat_threads_by_status(user_id, status)
    return jsonify(tasks)

# แก้ไขฟังก์ชัน api_send_admin_reply ให้ใช้ Line ID ของลูกค้า
@app.route('/api/send_admin_reply/<line_id>', methods=['POST'])
def api_send_admin_reply(line_id):
    """
    Handles sending an admin reply using the LINE Push API for reliable delivery.
    """
    data = request.json
    task_id = data.get('taskId')
    reply_message = data.get('replyMessage')
    store_id = data.get('storeId') # รับ storeId เพิ่มเข้ามา

    if not task_id or not reply_message or not store_id:
        return jsonify({'message': 'Missing required fields (taskId, replyMessage, or storeId).'}), 400

    credentials_data = get_credentials(store_id)
    if not credentials_data:
        return jsonify({'message': 'Credentials not found for this store.'}), 404
    
    try:
        line_bot_api = LineBotApi(credentials_data['channel_access_token'])
        
        # ใช้ push_message เพื่อส่งข้อความไปหาลูกค้าโดยตรงด้วย line_id
        line_bot_api.push_message(
            line_id, # <-- ตรงนี้คือ line_id ของลูกค้า
            TextSendMessage(text=f"แอดมิน: {reply_message}")
        )
        
        # อัปเดตสถานะในฐานข้อมูลหลังจากส่งข้อความสำเร็จ
        update_admin_response(task_id, reply_message)
        update_task_status(task_id, 'Responded')
        
        return jsonify({'message': 'Reply sent and task updated successfully.'}), 200
    except LineBotApiError as e:
        print(f"LINE API Error when sending reply: {e}")
        return jsonify({'message': f'Failed to send reply via LINE API: {e.message}'}), 500
    except Exception as e:
        print(f"Error sending admin reply: {e}")
        return jsonify({'message': 'Internal server error.'}), 500

@app.route('/api/update_task_status/<user_id>', methods=['POST'])
def api_update_task_status(user_id):
    data = request.json
    task_id = data.get('taskId')
    new_status = data.get('newStatus')

    if not task_id or not new_status:
        return jsonify({'message': 'Missing task ID or new status.'}), 400

    update_task_status(task_id, new_status)
    return jsonify({'message': 'Task status updated successfully.'}), 200

@app.route('/webhook/<user_id>', methods=['POST'])
def callback(user_id):
    print(f"--- LINE Webhook Request for user: {user_id} ---")
    
    credentials_data = get_credentials(user_id)
    if not credentials_data:
        print(f"Credentials not found for user ID: {user_id}")
        return 'Not Found', 404

    channel_secret_dynamic = credentials_data['channel_secret']
    channel_access_token_dynamic = credentials_data['channel_access_token']
    
    handler_dynamic = WebhookHandler(channel_secret_dynamic)
    line_bot_api_dynamic = LineBotApi(channel_access_token_dynamic)

    body = request.get_data(as_text=True)
    signature = request.headers.get('X-Line-Signature')
    
    try:
        @handler_dynamic.add(MessageEvent, message=TextMessage)
        def handle_message(event):
            user_message = event.message.text
            reply_token = event.reply_token
            line_user_id = event.source.user_id

            # บันทึกข้อความของลูกค้าลงในฐานข้อมูล
            task_id = add_new_task(user_id, line_user_id, reply_token, user_message)
            
            # --- ตรงนี้คือส่วนที่แก้ไข ---
            is_auto_reply_enabled = get_auto_reply_setting(user_id)
            if is_auto_reply_enabled:
                print("Auto-reply is enabled. Generating AI response...")
                
                try:
                    # เรียกใช้ฟังก์ชันจาก ai_processor.py โดยตรง
                    # process_new_tasks(user_id, line_user_id, user_message, task_id)
                    process_new_tasks_using_sql_and_RAG(user_id, line_user_id, user_message, task_id)

                except Exception as e:
                    print(f"Error during AI processing: {e}")
                    line_bot_api_dynamic.reply_message(
                        reply_token,
                        TextSendMessage(text="ขออภัยค่ะ ระบบกำลังมีปัญหา ไม่สามารถตอบกลับได้ในขณะนี้")
                    )
        # 🟢 Handler สำหรับ Sticker Message
        @handler_dynamic.add(MessageEvent, message=StickerMessage)
        def handle_sticker_message(event):
            # ตัวอย่าง: ตอบกลับด้วยข้อความปกติเมื่อได้รับ Sticker
            line_bot_api_dynamic.reply_message(
                event.reply_token,
                TextSendMessage(text="สวัสดีค่ะมีอะไรสอบถามแจ้งได้เลยนะคะ")
            )
            
        # 🟢 Handler สำหรับ Image Message
        @handler_dynamic.add(MessageEvent, message=ImageMessage)
        def handle_image_message(event):
            # ตัวอย่าง: ตอบกลับด้วยข้อความปกติเมื่อได้รับ Image
            line_bot_api_dynamic.reply_message(
                event.reply_token,
                TextSendMessage(text="ขอบคุณสำหรับรูปภาพค่ะ รบกวนพิมพ์คำถาม หรือมีอะไรสอบถามแจ้งได้เลยนะคะ")
            )
        handler_dynamic.handle(body, signature)

    except InvalidSignatureError:
        print("Invalid signature. Please check your channel secret.")
        return 'Invalid signature', 400
    except LineBotApiError as e:
        print(f"LINE API Error: {e}")
        return f'LINE API Error: {e}', 500
    except Exception as e:
        print(f"Error handling webhook: {e}")
        return f'Internal Server Error: {e}', 500
    
    return 'OK', 200

# NEW: API Endpoint for auto-reply setting
@app.route('/api/auto_reply_setting/<user_id>')
def get_auto_reply_status(user_id):
    is_enabled = get_auto_reply_setting(user_id)
    return jsonify({'is_enabled': bool(is_enabled)})

@app.route('/api/update_auto_reply_setting/<user_id>', methods=['POST'])
def update_auto_reply_status(user_id):
    data = request.json
    is_enabled = data.get('is_enabled')
    if is_enabled is None:
        return jsonify({'message': 'Missing is_enabled parameter.'}), 400
    
    status_int = 1 if is_enabled else 0
    update_auto_reply_setting(user_id, status_int)
    return jsonify({'message': 'Auto-reply setting updated successfully.'}), 200

# ... (โค้ดส่วนอื่น ๆ เหมือนเดิม)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 9000))
    app.run(host='0.0.0.0', port=port)