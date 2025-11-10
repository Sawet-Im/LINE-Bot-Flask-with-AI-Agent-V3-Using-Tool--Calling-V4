# my_app/app.py

import streamlit as st
import re
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.agents import AgentFinish, AgentAction

# Import functions from other files
# from database import initialize_database, get_open_stores, DB_FILE_NAME, log_to_database
from database import initialize_database, DB_FILE_NAME
from agent_setup import initialize_sql_agent

# --- Page Setup ---
st.set_page_config(page_title="AI ผู้ช่วยจัดการฐานข้อมูล", layout="wide")
st.title("🤖 AI ผู้ช่วยจัดการฐานข้อมูล (SQL Agent)")
st.write("สวัสดีครับ! ผมคือ AIผู้ช่วย ที่สามารถ **ค้นหา, เพิ่ม, และแก้ไข** ข้อมูลในฐานข้อมูลของเราได้แล้วนะครับ ถามมาได้เลย!")

# --- 1. Database & AI Agent Setup ---
db_uri_to_use = initialize_database(DB_FILE_NAME)

st.sidebar.header("การตั้งค่า AI Model")
selected_llm_model = st.sidebar.radio(
    "เลือก AI Model ที่ต้องการ:",
    ("gemini-2.5-pro","gemini-2.5-flash", "llama3.2","gpt-oss:20b")
)

sql_agent_executor = initialize_sql_agent(db_uri_to_use, selected_llm_model)

# --- 2. Chat Interface ---
if "messages" not in st.session_state:
    st.session_state.messages = [
        AIMessage(content="สวัสดีครับ! ผมคือ AI ผู้ช่วยขายอาหาร มีอะไรให้ช่วยไหมครับ?")
    ]

for message in st.session_state.messages:
    with st.chat_message(message.type):
        st.markdown(message.content)

prompt_input = st.chat_input("พิมพ์คำถามหรือคำสั่งของคุณที่นี่...")

if prompt_input:
    st.session_state.messages.append(HumanMessage(content=prompt_input))
    with st.chat_message("user"):
        st.markdown(prompt_input)

    if "ตอนนี้ร้านไหนเปิดบ้าง" in prompt_input or "ร้านไหนเปิดอยู่" in prompt_input or "ร้านเปิดไหม" in prompt_input:
        open_stores = get_open_stores()
        if open_stores:
            response_text = f"ตอนนี้ร้านสาขาที่เปิดอยู่ได้แก่: {', '.join(open_stores)} ครับ"
        else:
            response_text = "ขออภัยครับ ตอนนี้ไม่มีร้านสาขาไหนเปิดให้บริการเลย"
            
        # NEW: Call the database logging function
        log_to_database(prompt_input, response_text, "N/A")
        st.session_state.messages.append(AIMessage(content=response_text))
        with st.chat_message("ai"):
            st.markdown(response_text)
    else:
        with st.spinner("AI กำลังคิด..."):
            try:
                response = sql_agent_executor.invoke({"input": prompt_input})
                ai_response = response.get("output", "ขออภัยครับ เกิดข้อผิดพลาดในการประมวลผลคำตอบ")
                sql_command = "N/A"
                if response.get("intermediate_steps"):
                    for step in response["intermediate_steps"]:
                        action, _ = step
                        if isinstance(action, AgentAction) and action.tool == "sql_db_query":
                            sql_command = action.tool_input
                            break
                if sql_command != "N/A":
                    ai_response += f"\n\nคำสั่ง SQL ที่ใช้: `{sql_command}`"
                
                # NEW: Call the database logging function
                log_to_database(prompt_input, ai_response, sql_command)

                st.session_state.messages.append(AIMessage(content=ai_response))
                with st.chat_message("ai"):
                    st.markdown(ai_response)
                # ... ส่วนแสดงขั้นตอนการทำงานของ AI เหมือนเดิม
                if response.get("intermediate_steps"):
                    with st.expander("ดูขั้นตอนการทำงานของ AI"):
                        for i, step in enumerate(response["intermediate_steps"]):
                            action, observation = step
                            col1, col2 = st.columns([0.5, 0.5])
                            with col1:
                                st.markdown(f"**ขั้นตอนที่ {i+1}**")
                                if isinstance(action, AgentAction):
                                    thought_match = re.search(r'Thought:\s*(.*?)(?=\nAction:|$)', action.log, re.DOTALL)
                                    thought = thought_match.group(1).strip() if thought_match else "AI กำลังคิด..."
                                    st.markdown(f"**🧠 ความคิดของ AI:** {thought}")
                                    st.markdown(f"**⚙️ การดำเนินการ:** `{action.tool}`")
                                    st.markdown(f"**🔧 ข้อมูลนำเข้า (SQL Query):** ```\n{action.tool_input}\n```")
                                elif isinstance(action, AgentFinish):
                                    st.markdown(f"**🧠 ความคิดของ AI:** AI ได้ข้อมูลครบถ้วนและพร้อมให้คำตอบสุดท้ายแล้วครับ")
                                    st.markdown(f"**⚙️ การดำเนินการ:** `สรุปคำตอบ`")
                                else:
                                    st.markdown(f"**💡 ความคิดของ AI:** ไม่ใช่ AgentAction หรือ AgentFinish ที่รู้จัก")
                                    st.markdown(f"**⚙️ การดำเนินการ:** `{type(action)}`")
                                    st.markdown(f"**🔧 ข้อมูลนำเข้า:** `ไม่มี`")
                            with col2:
                                st.markdown("**📋 ผลลัพธ์**")
                                if isinstance(action, AgentAction):
                                    st.markdown(f"```\n{str(observation)}\n```")
                                elif isinstance(action, AgentFinish):
                                    st.markdown(f"```\n{action.return_values.get('output', 'N/A')}\n```")
                            st.markdown("---")
            except Exception as e:
                st.error("เกิดข้อผิดพลาดในการทำงานของ AI", icon="🚨")
                st.markdown("กรุณาลองใหม่อีกครั้ง หรือพิมพ์คำถามให้ชัดเจนขึ้น")
                st.exception(e)
                st.session_state.messages.append(AIMessage(content="ขออภัยครับ เกิดข้อผิดพลาดในการประมวลผล กรุณาลองใหม่"))
                with st.chat_message("ai"):
                    st.markdown("ขออภัยครับ เกิดข้อผิดพลาดในการประมวลผล กรุณาลองใหม่")