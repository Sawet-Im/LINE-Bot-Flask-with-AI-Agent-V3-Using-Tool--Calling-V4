# LINE Bot Flask with AI Agent V4 (Tool Calling)

โปรเจกต์นี้คือการต่อยอดจาก LINE Bot Flask with AI Agent V3(เน้นการพึ่งพา Prompt และ Parsing) สู่ Native Tool Calling Agent การเปลี่ยนแปลงนี้มีวัตถุประสงค์เพื่อเพิ่มความยืดหยุ่นในการขยาย (Flexibility) เพื่อรองรับ Tools ใหม่ ๆ (เช่น การจองโต๊ะ, การชำระเงิน) ในอนาคต การปรับปรุงนี้จะทำให้ Agent สามารถตัดสินใจเลือกใช้ Tool ที่เหมาะสม (SQL หรือ RAG) โดยใช้ JSON Schema เป็นหลัก แทนการพึ่งพากฎที่ซับซ้อนใน Prompt และPrompt ที่สะอาดกว่าเดิม

# คุณสมบัติใหม่ 
| Feature | V3  | Tool Calling Agent |
| --- | --- | --- |
| **Agent Core Function** | create_sql_agent | **create_tool_calling_agent** |
| **Agent Base Type** | **SQL Agent** (Agent Type: openai-tools หรือ zero-shot ที่ปรับมาสำหรับ SQL) | **Native Tool Calling Agent** (ใช้ Native Function/Tool Call ของ LLM เช่น Gemini) |
| **การรวม Tools** | Agent ถูกสร้างโดยใช้ **SQL Toolset เป็นหลัก** แล้วจึงนำ sql_agent_object.agent มาผูกกับ final_tools (รวม RAG) ใน AgentExecutor ❌ | **Agent ถูกสร้างพร้อม Tools ทั้งหมด** (sql_db_query, knowledge_base_search) ตั้งแต่เริ่มต้น ✅ |
| **การตัดสินใจ (Classification)** | พึ่งพา **Prompt** (System Prefix) และ **Parsing Logic** ที่ถูกกำหนดโดย create_sql_agent เป็นหลักในการสลับระหว่าง SQL และ RAG | พึ่งพา **Native Function Calling** ของ LLM โดยตรง LLM จะเลือก Tool ที่เหมาะสมจาก Schema ที่ส่งให้ |
| **การจัดการคำทักทาย (Early Exit)** | ต้องใส่กฎที่ซับซ้อนใน Prompt (**[การทักทาย/Early Exit]**) เพื่อให้ LLM **หลีกเลี่ยง** การเรียก Tool และหวังว่า Agent Executor จะไม่เกิด Parsing Error | LLM ใช้ Native Tool Calling ในการแยกแยะ: ถ้าไม่เรียก Tool จะเป็น **Final Answer** ทันที ไม่เกิด Parsing Error เมื่อตอบข้อความธรรมดา |
| **การจัดการ Tools ใหม่** | ซับซ้อน เพราะ Agent Core ไม่ได้ถูกออกแบบมาให้รองรับ Tools อื่นนอกเหนือจาก SQL | เรียบง่าย: เพียงแค่เพิ่ม Tool ในรายการ final_toolsและอัปเดต Prompt เล็กน้อย |
|  |  |  |


# 1. โครงสร้างโปรเจกต์ (Updated)
```
มีการเพิ่มไฟล์และโฟลเดอร์สำหรับ RAG (Vector DB) เข้ามา:
├── templates/
│   ├── dashboard.html
│   └── setup.html
├── my_app/
│   ├── api_app.py                          # เรียกใช้ ฟังก์ชั่น process_new_tasks_using_tool_callig
│   ├── admin_app.py
│   ├── ai_processor.py                     #เพิ่ม process_new_tasks_using_tool_callig
│   ├── database.py                       
│   ├── agent_setup.py  
│   ├── agent_setup_sql_agent_and_rag.py                  
│   └── agent_setup_create_tool_calling.py  # ไฟล์เพิ่มใหม่
├── chroma_db_data/                         
├── .env                                  
├── requirements.txt                      
└── README.md
```

# 3. การติดตั้งและการตั้งค่า (Configuration)
## 3.1. สิ่งที่ต้องมีก่อนเริ่ม
 * Python 3.13
 * pip (ตัวจัดการแพ็กเกจของ Python)
 * ngrok (สำหรับเปิด Local Server ให้เข้าถึงได้จากภายนอก)
## 3.2. การติดตั้ง Dependencies
```
python3.13 -m venv venv
source venv/bin/activate
pip install flask
pip install -r requirements.txt
```
## 3.3. การตั้งค่า API Key

สร้างไฟล์ชื่อ .env และเพิ่มค่าที่จำเป็น รวมถึงตัวแปรใหม่สำหรับ RAG:
```
GOOGLE_API_KEY="YOUR_GEMINI_API_KEY"    
# สำหรับการตอบกลับด้วย LINE API
LINE_CHANNEL_ACCESS_TOKEN="YOUR_LINE_ACCESS_TOKEN"
LINE_CHANNEL_SECRET="YOUR_LINE_CHANNEL_SECRET"
# ngrok url
BASE_URL="NGROK_URL"     
OLLAMA_HOST="OLLAMA_URL"
```

## 3.3. โครงสร้าง Agent
| ส่วนประกอบ | ชื่อฟังก์ชัน/คลาส | หน้าที่หลักโดยละเอียด |
| --- | --- | --- |
| **LLM (สมอง)** | `ChatGoogleGenerativeAI` | ทำการ **Classification** (ตัดสินใจว่าจะใช้ Tool ไหนจาก Schema ที่ได้รับ) และ **Reasoning** (สร้างคำตอบสุดท้ายที่สละสลวย) |
| **Tools (แขนขา)** | `sql_db_query`, `knowledge_base_search`, (`booking_tool`) | เป็น **Interface** สำหรับการเข้าถึงระบบภายนอก Tool จะถูกห่อหุ้มด้วย `langchain.tools.Tool` เพื่อส่ง **Schema** ให้ LLM ใช้ในการตัดสินใจเลือก |
| **Agent Core** | `create_tool_calling_agent` | **ผูก LLM, Tools, และ Prompt** เข้าด้วยกัน ใช้ **Native Tool Calling** ของ Gemini ในการสื่อสารผ่าน **JSON Function Call** ทำให้ Agent มีความเสถียรสูง |
| **Executor** | `AgentExecutor` | จัดการ **Agent Loop** (วงจรการทำงานซ้ำ: สั่งการ > รับผลลัพธ์ > สั่งการต่อ), บันทึก `chat_history` และดึงข้อมูลการทำงานภายใน (**`intermediate_steps`**) |
| **Memory** | `ConversationBufferMemory` | บันทึกประวัติการสนทนา เพื่อให้ Agent มีบริบทต่อเนื่อง เช่น ข้อจำกัดวัตถุดิบ (Non-Contextual Memory) และประวัติคำถาม/คำตอบ (Contextual Memory) |
| **Prompt** | `ChatPromptTemplate` | กำหนด **System Instruction** (กฎและตรรกะทางธุรกิจ) โดยเน้นไปที่ **ตรรกะทางธุรกิจ (Business Logic)** และ **พฤติกรรมการตอบกลับ (Behavior)**โดยลดรายละเอียดด้านเทคนิคลง |


# 4. การไหลของข้อมูล

การไหลของข้อมูลในฟังก์ชัน initialize_native_tool_calling_agent
| ขั้นตอน | ฟังก์ชัน/ตัวแปร | Input | Output / ผลลัพธ์ |
| --- | --- | --- | --- |
| **1. Tool Preparation** | `SQLDatabaseToolkit.get_tools()` และ `get_rag_tool()` | `db_instance`, `llm`, `rag_retriever` | `final_tools` (List of Tools พร้อม Schema) |
| **2. Prompt Setup** | `create_agent_prefix_with_rag()` | `store_id`, `store_name` | `agent_prefix_final` (System Instruction) |
| **3. Agent Creation** | `create_tool_calling_agent()` | `llm`, `final_tools`, `prompt_template` | `agent` (Agent Object) |
| **4. Executor Creation** | `AgentExecutor()` | `agent`, `final_tools`, `memory` | **`agent_executor`** (Agent ที่พร้อมใช้งาน) |


## 5. ตัวอย่างการไหลข้อมูลการเรียก SQL Tool (เมนู)
| ขั้นตอน | ข้อมูล Input/Action | การไหลของข้อมูลใน `response['intermediate_steps']` | ผลลัพธ์สุดท้ายที่บันทึก |
| --- | --- | --- | --- |
| **Input** | `"มีเมนูผัดไทยราคาเท่าไหร่"` | - | - |
| **Agent Run** | LLM ตัดสินใจเรียก `sql_db_query` | **ToolCall:** `name='sql_db_query', input={'query': 'SELECT price FROM menu WHERE menu_name LIKE "%ผัดไทย%"'}` | - |
| **Observation** | SQL Tool รันและคืนค่า `[{'price': 65.0}]` | **Observation:** `[('sql_db_query', 'Result: [{'price': 65.0}]')]` | - |
| **Final Result** | LLM สร้างคำตอบสุดท้าย | `response['output'] = 'เมนูผัดไทยราคา 65 บาทค่ะ'` | `final_response_message` = 'เมนูผัดไทยราคา 65 บาทค่ะ' **`tool_or_sql_command`** = **'SQL: SELECT price FROM menu WHERE menu_name LIKE "%ผัดไทย%"'** |

## 6. ตัวอย่างการไหลข้อมูลการเรียก RAG Tool
| ขั้นตอน | ข้อมูล Input/Action | การไหลของข้อมูลใน `response['intermediate_steps']` | ผลลัพธ์สุดท้ายที่บันทึก |
| --- | --- | --- | --- |
| **Input** | `"ร้านอยู่ที่ไหน"` | - | - |
| **Agent Run** | LLM ตัดสินใจเรียก `knowledge_base_search` | **ToolCall:**`name='knowledge_base_search', input={'query': 'ที่อยู่ร้าน'}` | - |
| **Observation** | RAG Tool รันและคืนค่า Document | **Observation:**`[('knowledge_base_search', 'Document(page_content="รายละเอียด: ร้านตั้งอยู่ ถ.สีลม ซ.5")')]` | - |
| **Final Result** | LLM สร้างคำตอบสุดท้าย | `response['output'] = 'ร้านของเราตั้งอยู่ที่ถนนสีลม ซอย 5 ค่ะ'` | `final_response_message` = 'ร้านของเราตั้งอยู่ที่ถนนสีลม ซอย 5 ค่ะ' **`tool_or_sql_command`** = **'Tool: knowledge_base_search (Query: ที่อยู่ร้าน)'** |
# LINE-Bot-Flask-with-AI-Agent-V3-Using-Tool--Calling-V4
