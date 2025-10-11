#database.py

import sqlite3
import datetime

DB_FILE_NAME = "store_database.db"

def initialize_database():
    """Initializes the database by creating tables if they don't exist."""
    try:
        conn = sqlite3.connect(DB_FILE_NAME)
        cursor = conn.cursor()

        # Create menu table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS menu (
                menu_id INTEGER PRIMARY KEY,
                menu_name TEXT,
                price REAL,
                category TEXT,
                store_id INTEGER,
                FOREIGN KEY(store_id) REFERENCES stores(store_id)
            )
        ''')

        # Create promotions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS promotions (
                id INTEGER PRIMARY KEY,
                promo_code TEXT NOT NULL,
                description TEXT NOT NULL,
                start_date TEXT,
                end_date TEXT,
                menu_id INTEGER,
                store_id INTEGER,
                FOREIGN KEY(menu_id) REFERENCES menu(menu_id),
                FOREIGN KEY(store_id) REFERENCES stores(store_id)
            )
        ''')
        
        # ตาราง stores ถูกปรับเปลี่ยนเพื่อเก็บการตั้งค่าการตอบกลับอัตโนมัติ
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stores (
                store_id INTEGER PRIMARY KEY,
                user_id TEXT,
                store_name TEXT,
                opening_hours TEXT,
                status TEXT,
                location TEXT,
                is_auto_reply_enabled INTEGER DEFAULT 1
            )
        ''')

        # Create tasks table for bot responses and admin actions
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                task_id INTEGER PRIMARY KEY,
                user_id TEXT NOT NULL,
                line_id TEXT NOT NULL,
                user_message TEXT NOT NULL,
                ai_response TEXT,
                using_sql TEXT,
                admin_response TEXT,
                reply_token TEXT NOT NULL,
                status TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                response_timestamp DATETIME
            )
        ''')

        # Create line_channels table to store per-user credentials
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS line_channels (
                user_id TEXT PRIMARY KEY,
                channel_secret TEXT NOT NULL,
                channel_access_token TEXT NOT NULL
            )
        ''')
        
        # เพิ่มตารางวัตถุดิบสำหรับเมนู
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ingredients (
                ingredient_id INTEGER PRIMARY KEY,
                menu_id INTEGER,
                ingredient_name TEXT NOT NULL,
                quantity TEXT,
                ingredient_type TEXT,
                FOREIGN KEY(menu_id) REFERENCES menu(menu_id)
            )
        ''')

        # Add initial data if tables are empty
        seed_data(conn, cursor)

        conn.commit()
        conn.close()
        print(f"Database '{DB_FILE_NAME}' initialized successfully.")
        return f"sqlite:///{DB_FILE_NAME}"

    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return None

def seed_data(conn, cursor):
    """Inserts initial data into tables if they are empty."""
    cursor.execute("SELECT COUNT(*) FROM stores")
    if cursor.fetchone()[0] == 0:
        stores_data = [
            (1, 'user1', 'สาขาพระราม 9', 'Open', 'อาคารฟอร์จูนทาวน์ ชั้น 2', 1),
            (2, 'user2', 'สาขาสุขุมวิท 21', 'Closed', 'อาคาร GMM Grammy Place', 1),
            (3, 'user3', 'สาขาพญาไท', 'Open', 'อาคาร CP Tower', 1)
        ]
        cursor.executemany("INSERT INTO stores (store_id, user_id, store_name, status, location, is_auto_reply_enabled) VALUES (?, ?, ?, ?, ?, ?)", stores_data)
        conn.commit()
    
    cursor.execute("SELECT COUNT(*) FROM menu")
    if cursor.fetchone()[0] == 0:
        menu_data = [
            (1, 'ข้าวผัดกะเพราไก่', 50.00, 'อาหารจานเดียว', 1),
            (2, 'ผัดซีอิ๊วหมู', 55.00, 'อาหารจานเดียว', 1),
            (3, 'ต้มยำกุ้ง', 80.00, 'อาหารไทย', 2),
            (4, 'แกงเขียวหวานเนื้อ', 75.00, 'อาหารไทย', 2),
            (5, 'ชาเย็น', 25.00, 'เครื่องดื่ม', 3),
            (6, 'กาแฟ', 30.00, 'เครื่องดื่ม', 3)
        ]
        cursor.executemany("INSERT INTO menu (menu_id, menu_name, price, category, store_id) VALUES (?, ?, ?, ?, ?)", menu_data)
        conn.commit()
        
    cursor.execute("SELECT COUNT(*) FROM promotions")
    if cursor.fetchone()[0] == 0:
        promotions_data = [
            ('WELCOME10', 'ลด 10% สำหรับลูกค้าใหม่', '2025-01-01', '2025-12-31', None, 1),
            ('BUY3GET1', 'ซื้อ 3 จานฟรี 1 จาน', '2025-09-01', '2025-10-31', 1, 1),
            ('SUMMER_SALE', 'โปรโมชั่นฤดูร้อน ลด 20%', '2025-06-01', '2025-08-31', 3, 2),
            ('COFFEE_DEAL', 'ซื้อกาแฟแก้วที่ 2 ลด 50%', '2025-09-15', '2025-11-15', 6, 3)
        ]
        cursor.executemany("INSERT INTO promotions (promo_code, description, start_date, end_date, menu_id, store_id) VALUES (?, ?, ?, ?, ?, ?)", promotions_data)
        conn.commit()
    
    cursor.execute("SELECT COUNT(*) FROM ingredients")
    if cursor.fetchone()[0] == 0:
        ingredients_data = [
            (1, 'ข้าวสวย', '1 ถ้วย', 'Grain'),        
            (1, 'เนื้อไก่', '100 กรัม', 'Meat'),
            (1, 'ใบกะเพรา', '5 กรัม', 'Vegetable'),  
            (2, 'เส้นใหญ่', '150 กรัม', 'Wheat/Grain'),
            (2, 'เนื้อหมู', '100 กรัม', 'Meat'),
            (3, 'กุ้งสด', '200 กรัม', 'Seafood'),    
            (3, 'พริก', '3 เม็ด', 'Vegetable'),
            (4, 'เนื้อวัว', '150 กรัม', 'Meat'),
            (4, 'มะเขือ', '2 ลูก', 'Vegetable'),
            (5, 'ชาซีลอน', '1 ช้อนชา', 'Spice'),    
            (5, 'นมสด', '30 มล.', 'Dairy'),     
            (6, 'ผงกาแฟ', '1 ช้อนชา', 'Spice')
        ]
        cursor.executemany("INSERT INTO ingredients (menu_id, ingredient_name, quantity,ingredient_type) VALUES (?, ?, ?, ?)", ingredients_data)
        conn.commit()
    
    # อัปเดตข้อมูล stores
    cursor.execute("SELECT COUNT(*) FROM stores")
    if cursor.fetchone()[0] == 0:
        stores_data = [
            ('user1', 'สาขาพระราม 9', 'Open', 'อาคารฟอร์จูนทาวน์ ชั้น 2', 1),
            ('user2', 'สาขาสุขุมวิท 21', 'Closed', 'อาคาร GMM Grammy Place', 1),
            ('user3', 'สาขาพญาไท', 'Open', 'อาคาร CP Tower', 1)
        ]
        cursor.executemany("INSERT INTO stores (user_id, store_name, status, location, is_auto_reply_enabled) VALUES (?, ?, ?, ?, ?)", stores_data)
        conn.commit()

# ในโค้ด seed_data()
    cursor.execute("SELECT COUNT(*) FROM promotions")
    if cursor.fetchone()[0] == 0:
        promotions_data = [
            ('WELCOME10', 'ลด 10% สำหรับลูกค้าใหม่', None, None, '2025-01-01', '2025-12-31'),
            ('BUY3GET1', 'ซื้อ 3 จานฟรี 1 จาน', 1, 1, '2025-09-01', '2025-10-31'),
            ('SUMMER_SALE', 'โปรโมชั่นฤดูร้อน ลด 20%', 3, 2, '2025-06-01', '2025-08-31'),
            ('COFFEE_DEAL', 'ซื้อกาแฟแก้วที่ 2 ลด 50%', 6, 3, '2025-09-15', '2025-11-15')
        ]
        cursor.executemany("INSERT INTO promotions (promo_code, description, menu_id, store_id, start_date, end_date) VALUES (?, ?, ?, ?, ?, ?)", promotions_data)
        conn.commit()
    
def add_credentials(user_id, channel_secret, channel_access_token):
    """Adds or updates a user's LINE channel credentials."""
    conn = sqlite3.connect(DB_FILE_NAME)
    cursor = conn.cursor()
    try:
        # เพิ่มข้อมูลในตาราง line_channels
        cursor.execute('''
            INSERT OR REPLACE INTO line_channels (user_id, channel_secret, channel_access_token)
            VALUES (?, ?, ?)
        ''', (user_id, channel_secret, channel_access_token))
        
        # เพิ่มข้อมูลในตาราง stores ด้วย user_id และตั้งค่าเริ่มต้น is_auto_reply_enabled เป็น 1
        cursor.execute('''
            INSERT OR IGNORE INTO stores (user_id, is_auto_reply_enabled)
            VALUES (?, 1)
        ''', (user_id,))
        
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"Database error adding credentials: {e}")
        return False
    finally:
        conn.close()

def get_credentials(user_id):
    """Retrieves a user's LINE channel credentials."""
    conn = sqlite3.connect(DB_FILE_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        # ดึงข้อมูล channel_secret และ channel_access_token จากตาราง line_channels
        cursor.execute("SELECT * FROM line_channels WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    except sqlite3.Error as e:
        print(f"Database error getting credentials: {e}")
        return None
    finally:
        conn.close()

def get_auto_reply_setting(user_id):
    """Retrieves the auto-reply status for a specific user from the stores table."""
    conn = sqlite3.connect(DB_FILE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT is_auto_reply_enabled FROM stores WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        # หากไม่พบข้อมูล ให้คืนค่าเริ่มต้น (เปิดใช้งาน)
        return result[0] if result else 1
    except sqlite3.Error as e:
        print(f"Database error getting auto-reply setting: {e}")
        return 1 # คืนค่าเริ่มต้นในกรณีเกิดข้อผิดพลาด
    finally:
        conn.close()

def update_auto_reply_setting(user_id, status):
    """Updates the auto-reply status for a specific user in the stores table."""
    conn = sqlite3.connect(DB_FILE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE stores SET is_auto_reply_enabled = ? WHERE user_id = ?", (status, user_id))
        conn.commit()
    except sqlite3.Error as e:
        print(f"Database error updating auto-reply setting: {e}")
    finally:
        conn.close()
        

def add_new_task(user_id, line_id, reply_token, user_message):
    """Adds a new message task from a LINE user to the database."""
    conn = sqlite3.connect(DB_FILE_NAME)
    cursor = conn.cursor()
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    try:
        cursor.execute("""
            INSERT INTO tasks (user_id, line_id, reply_token, user_message, status,timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, line_id, reply_token, user_message, "Pending",timestamp))
        conn.commit()
        return cursor.lastrowid  # คืนค่า ID ที่สร้างขึ้นมา
    except sqlite3.Error as e:
        print(f"Database error adding new task: {e}")
        return None
    finally:
        conn.close()

# อัปเดตฟังก์ชันให้ใช้ 'user_id'
def get_tasks_by_status(user_id, status):
    """Fetches tasks from the tasks table based on their status and store user ID."""
    conn = sqlite3.connect(DB_FILE_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM tasks WHERE user_id = ? AND status = ? ORDER BY timestamp DESC", (user_id, status))
        tasks = cursor.fetchall()
        return [dict(task) for task in tasks]
    except sqlite3.Error as e:
        print(f"Database error fetching tasks: {e}")
        return []
    finally:
        conn.close()

def update_task_status(task_id, new_status):
    """Updates the status of a specific task."""
    conn = sqlite3.connect(DB_FILE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE tasks SET status = ? WHERE task_id = ?", (new_status, task_id))
        conn.commit()
    except sqlite3.Error as e:
        print(f"Database error updating task status: {e}")
    finally:
        conn.close()

def update_task_response(task_id, response,sql_text):
    """
    Updates the AI's response, status, and records a dedicated response timestamp.
    """
    conn = sqlite3.connect(DB_FILE_NAME)
    cursor = conn.cursor()
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    try:
        cursor.execute("""
            UPDATE tasks
            SET
                ai_response = ?,
                status = 'Responded',
                response_timestamp = ?,
                using_sql = ?
            WHERE
                task_id = ?
        """, (response, timestamp, sql_text, task_id))
        conn.commit()
    except sqlite3.Error as e:
        print(f"Database error updating AI response: {e}")
    finally:
        conn.close()

def update_admin_response(task_id, response):
    """
    Updates the admin's response, status, and records a dedicated response timestamp.
    """
    conn = sqlite3.connect(DB_FILE_NAME)
    cursor = conn.cursor()
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    try:
        cursor.execute("""
            UPDATE tasks
            SET
                admin_response = ?,
                status = 'Responded',
                response_timestamp = ?
            WHERE
                task_id = ?
        """, (response, task_id,timestamp))
        conn.commit()
    except sqlite3.Error as e:
        print(f"Database error updating admin response: {e}")
    finally:
        conn.close()


def get_chat_history(user_id, line_id, limit=20):
    """
    Fetches the entire chat history for a specific LINE user.
    Args:
        user_id (str): The ID of the store.
        line_id (str): The ID of the LINE user.
    Returns:
        list: A list of dictionaries, each representing a message/task.
    """
    conn = sqlite3.connect(DB_FILE_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM tasks WHERE user_id = ? AND line_id = ? ORDER BY timestamp ASC", (user_id, line_id))
        tasks = cursor.fetchall()
        return [dict(task) for task in tasks]
    except sqlite3.Error as e:
        print(f"Database error fetching chat history: {e}")
        return []
    finally:
        conn.close()



def get_chat_history_for_memory(user_id, line_id, limit=20):  # <--- MUST include 'limit' here
    """Fetches the chat history for a specific LINE user, limited by the last N messages."""
    conn = sqlite3.connect(DB_FILE_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        # Use LIMIT in the SQL query
        cursor.execute("""
            SELECT user_message, ai_response
            FROM tasks 
            WHERE user_id = ? AND line_id = ? AND status IN ('Responded')
            ORDER BY timestamp DESC
            LIMIT ?
        """, (user_id, line_id, limit)) # <--- MUST pass 'limit' here
        
        # ... (rest of the code to reverse and return tasks) ...
        tasks = cursor.fetchall()
        return [dict(task) for task in reversed(tasks)]
        
    except sqlite3.Error as e:
        print(f"Database error fetching chat history: {e}")
        return []
    finally:
        conn.close()

# def get_chat_threads_by_status(user_id, status):
#     """
#     Fetches a list of unique line_ids where the latest task has the specified status.
#     This is used to group chats by the status of their most recent message.
#     """
#     conn = sqlite3.connect(DB_FILE_NAME)
#     conn.row_factory = sqlite3.Row
#     cursor = conn.cursor()
#     try:
#         cursor.execute("""
#             SELECT
#                 t1.*
#             FROM
#                 tasks t1
#             JOIN
#                 (
#                     SELECT
#                         line_id,
#                         MAX(timestamp) AS max_timestamp
#                     FROM
#                         tasks
#                     WHERE
#                         user_id = ?
#                     GROUP BY
#                         line_id
#                 ) AS t2 ON t1.line_id = t2.line_id AND t1.timestamp = t2.max_timestamp
#             WHERE
#                 t1.user_id = ? AND t1.status = ?
#             ORDER BY
#                 t1.timestamp DESC
#         """, (user_id, user_id, status))
        
#         threads = cursor.fetchall()
#         return [dict(thread) for thread in threads]
#     except sqlite3.Error as e:
#         print(f"Database error fetching chat threads: {e}")
#         return []
#     finally:
#         conn.close()

# database.py

def get_chat_threads_by_status(user_id, status):
    """
    Fetches a list of unique line_ids where the latest task has the specified status.
    This is used to group chats by the status of their most recent message.
    """
    conn = sqlite3.connect(DB_FILE_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        # ใช้ CTE (Common Table Expression) เพื่อหา task_id ล่าสุดของแต่ละ Line ID
        # และใช้ Subquery เพื่อกรองผลลัพธ์
        cursor.execute("""
            WITH LatestTasks AS (
                SELECT
                    line_id,
                    MAX(timestamp) AS max_timestamp
                FROM
                    tasks
                WHERE
                    user_id = ?
                GROUP BY
                    line_id
            )
            SELECT
                t1.*
            FROM
                tasks t1
            INNER JOIN
                LatestTasks t2 ON t1.line_id = t2.line_id AND t1.timestamp = t2.max_timestamp
            WHERE
                t1.user_id = ? AND t1.status = ?
            ORDER BY
                t1.timestamp DESC
        """, (user_id, user_id, status))
        
        threads = cursor.fetchall()
        return [dict(thread) for thread in threads]
    except sqlite3.Error as e:
        print(f"Database error fetching chat threads: {e}")
        return []
    finally:
        conn.close()

# 🟢 ฟังก์ชันใหม่: ดึงข้อมูล Store ID และ Store Name
def get_store_info_direct(user_id: str):
    """Retrieves store_id and store_name for a given user_id using direct SQLite connection."""
    conn = sqlite3.connect(DB_FILE_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT store_id, store_name
            FROM stores 
            WHERE user_id = ?
        """, (user_id,))
        
        result = cursor.fetchone()
        
        if result:
            # 🟢 ดึงค่าจาก Row Object
            store_id = str(result['store_id']) # ให้อยู่ในรูป string เพื่อส่งเข้า Prompt
            store_name = result['store_name']
            return store_id, store_name
        
    except sqlite3.Error as e:
        print(f"Database error fetching store info for {user_id}: {e}")
        
    finally:
        conn.close()

    # กรณีหาไม่เจอหรือเกิด Error
    return None, "ร้านอร่อยทุกวัน (ไม่ระบุ)"