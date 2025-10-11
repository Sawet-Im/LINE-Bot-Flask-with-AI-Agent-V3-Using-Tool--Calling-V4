# my_app/agent_setup.py

import os
import nest_asyncio
from dotenv import load_dotenv
import sqlite3 # 🟢 ต้องใช้สำหรับดึงข้อมูล Knowledge Base
from langchain_google_genai import ChatGoogleGenerativeAI
# 🟢 New Imports สำหรับ RAG (ChromaDB)
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import Chroma # 🟢 ใช้ Chroma
from langchain.tools import Tool
from langchain_core.documents import Document
# -----------------------------------------------

from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_community.agent_toolkits.sql.base import create_sql_agent
from langchain.memory import ConversationBufferMemory
from history_utils import load_history_from_db 
from langchain.agents import AgentExecutor
from database import get_store_info_direct 


load_dotenv()

# 🟢 ใส่บรรทัดนี้เพื่อแก้ไขปัญหา AsyncIO/Threading
# มันจะอนุญาตให้โค้ด Async (เช่น Embedding Model) ทำงานใน Thread Synchronous ได้
nest_asyncio.apply()
# =========================================================================
# 🟢 [RAG SECTION] ฟังก์ชันใหม่สำหรับจัดการ Knowledge Base ด้วย ChromaDB
# =========================================================================

# 1. ฟังก์ชันดึงข้อมูลจาก SQLite (ใช้ Logic เดิม)
def fetch_knowledge_from_db(store_id: str):
    """Fetches knowledge from the knowledge_base table filtered by store_id."""
    DB_FILE_NAME = "store_database.db"
    conn = sqlite3.connect(DB_FILE_NAME)
    cursor = conn.cursor()
    
    knowledge_docs = []
    try:
        # ดึงคำถามและคำตอบของร้านค้านั้น
        cursor.execute("""
            SELECT question_or_topic, answer_or_detail 
            FROM knowledge_base 
            WHERE store_id = ?
        """, (store_id,))
        
        results = cursor.fetchall()
        
        for topic, detail in results:
            content = f"หัวข้อ: {topic}\nรายละเอียด: {detail}"
            # ใช้ topic เป็น Metadata สำหรับการกรอง
            knowledge_docs.append(Document(page_content=content, metadata={"store_id": store_id, "topic": topic, "source": "knowledge_base_db"}))
            
    except sqlite3.Error as e:
        print(f"Database error fetching knowledge: {e}")
    finally:
        conn.close()
        
    return knowledge_docs



# 2. ฟังก์ชันสร้าง RAG Retriever (ใช้ ChromaDB)
def initialize_rag_retriever(store_id: str):
    """
    Loads or creates a persistent ChromaDB store for the given store_id.
    If the store is empty, it fetches data from SQLite and indexes it.
    """
    embeddings = GoogleGenerativeAIEmbeddings(model="text-embedding-004")
    
    # กำหนด Directory สำหรับเก็บไฟล์ Vector และ Collection Name
    persist_directory = "./chroma_vector_db/" 
    collection_name = f"store_{store_id}_knowledge"
    
    try:
        # เชื่อมต่อ/สร้าง ChromaDB (Persistent)
        vector_store = Chroma(
            collection_name=collection_name, 
            embedding_function=embeddings, 
            persist_directory=persist_directory
        )
        
        # ตรวจสอบว่า Collection มีข้อมูลหรือไม่
        collection_count = vector_store._collection.count()
        
        # หากไม่มีข้อมูล ให้ดึงจาก SQLite มา Index
        if collection_count == 0:
            print(f"Collection '{collection_name}' is empty. Indexing from SQLite...")
            
            documents = fetch_knowledge_from_db(store_id)
            
            if not documents:
                print(f"WARNING: No knowledge documents found for store {store_id}. RAG will be disabled.")
                return None
            
            # Index ข้อมูลลงใน ChromaDB
            vector_store.add_documents(documents)
            vector_store.persist()
            
            print(f"Indexing completed. {len(documents)} documents added.")
        else:
            print(f"Collection '{collection_name}' loaded from Disk ({collection_count} documents).")

        # คืนค่าเป็น Retriever 
        return vector_store.as_retriever(search_kwargs={"k": 3})

    except Exception as e:
        print(f"ERROR: ChromaDB initialization failed: {e}")
        return None

# 3. ฟังก์ชันสร้าง Tool จาก Retriever (มาตรฐาน RAG Tool)
def get_rag_tool(retriever):
    return Tool(
        name="knowledge_base_search",
        description="""ใช้สำหรับการค้นหาข้อมูลความรู้ทั่วไปของร้านค้า เช่น นโยบายการคืนสินค้า, นโยบายการจัดส่ง, ที่อยู่ร้าน, เบอร์โทร, หรือคำถามที่ไม่เกี่ยวกับเมนูหรือโปรโมชั่น ให้ส่งคำถามของลูกค้าเข้ามาใน tool นี้""",
        func=lambda query: retriever.invoke(query)
    )

# =========================================================================


def create_agent_prefix_with_rag(store_id, store_name, user_id):
    # ปรับ AGENT_PREFIX ให้เป็น f-string เพื่อใส่ค่าตัวแปร
    
    # ⚠️ ข้อความทักทายตอนต้นจะเปลี่ยนไปตามชื่อร้านที่ดึงมา
    return f"""คุณคือ AI ผู้ช่วยขายของร้านอาหาร **"{store_name}"** 🍽️ (Store ID: {store_id}) หน้าที่ของคุณคือต้อนรับลูกค้า แนะนำเมนู เสนอโปรโมชั่น และรับออเดอร์อย่างรวดเร็วเพื่อปิดการขาย

คุณกำลังให้บริการร้านค้าที่ใช้ **Store ID: {store_id}** (User ID: {user_id}) คุณมีความเชี่ยวชาญในการจัดการข้อมูลด้วย SQL และมีเครื่องมือสำหรับค้นหาข้อมูลทั่วไป (knowledge_base_search) และต้องปฏิบัติตามกฎเหล่านี้อย่างเคร่งครัด:

**กฎหลักและตรรกะการทำงาน (Core Logic):**
1.  **[การทักทาย/Early Exit]:** หากข้อความลูกค้าเป็นการทักทาย, ขอบคุณ, หรือ Emoji ล้วน **ให้ตอบกลับทันทีด้วยข้อความที่เป็นมิตรและเสนอความช่วยเหลือ** **ห้ามใช้ SQL, knowledge_base_search, หรือ Tool ใดๆ**
2.  **[การใช้ Memory/กรองเมนู]:** ต้องใช้ **'chat_history'** ในการตัดสินใจเสมอ หากลูกค้าตอบคำถามวัตถุดิบที่เคยถามไปแล้ว ให้ข้ามการถามซ้ำและดำเนินการค้นหาด้วย SQL ทันที
3.  **[การกรองข้อมูล (บังคับ)]:** คำถามใดๆ ที่เกี่ยวข้องกับเมนูหรือโปรโมชั่น **ให้ใช้ Store ID ที่ได้รับ ({store_id}) ในการกรองข้อมูลจากตาราง `menu` และ `promotions` ทันที ห้ามใช้ Subquery เพื่อหา Store ID ซ้ำ**
4.  **[การใช้ Tool ที่เหมาะสม]:**
    * **คำถามเกี่ยวกับเมนู/โปรโมชั่น:** ใช้ **SQL Tool** เท่านั้น
    * **คำถามเกี่ยวกับ นโยบาย/ที่อยู่/เวลาทำการ/เบอร์โทร/ข้อมูลทั่วไป:** ใช้ **knowledge_base_search Tool** เท่านั้น
5.  **[การสร้างคำตอบจาก Tool (ใหม่)]:**
    * หากคุณใช้ **knowledge_base_search Tool** คุณต้องอ่านข้อมูลที่ Tool ส่งกลับมาอย่างละเอียด และใช้เนื้อหาในส่วน **"รายละเอียด:"** หรือ **"answer_or_detail"** เพื่อสร้างคำตอบของลูกค้าอย่างชัดเจนและครบถ้วน **ห้ามตอบด้วยข้อความ Fallback หรือข้อความปฏิเสธ เช่น "ฉันไม่สามารถให้ข้อมูลได้" หาก Tool ส่งข้อมูลกลับมาให้คุณ**
6.  **[ข้อจำกัด SQL]:** ใช้ได้เฉพาะ **`SELECT`, `INSERT`, `UPDATE`** เท่านั้น **ห้ามใช้ `DELETE`/`DROP` เด็ดขาด**
7.  **[ข้อจำกัดคำตอบ]:** ห้ามตอบคำถามเกี่ยวกับโครงสร้างฐานข้อมูล ให้ตอบว่า: "ฉันไม่สามารถให้ข้อมูลเกี่ยวกับโครงสร้างภายในของระบบได้ค่ะ คุณสามารถสอบถามเกี่ยวกับเมนูหรือโปรโมชั่นต่าง ๆ ได้เลยค่ะ"
8.  **[การแสดง Tool/SQL (ปรับปรุง)]:** ต้องแสดง **คำสั่ง SQL ที่ใช้** หรือ **Tool ที่ใช้: knowledge_base_search** ที่ใช้ในการประมวลผลคำตอบทั้งหมดตามลำดับขั้นตอนไว้ในส่วนท้ายของคำตอบเสมอ


**ตัวอย่างการโต้ตอบและแนวทางการใช้ SQL:**

**A. การดึงข้อมูลเมนูทั้งหมด (บังคับกรองตาม Store ID: {store_id}):**
* **เมื่อลูกค้าถาม:** "มีเมนูอะไรบ้าง"
* **แนวทาง:** ใช้ Store ID ที่ได้รับในการกรองข้อมูลเมนู
* **คำสั่ง SQL ที่ใช้ (แบบลดขั้นตอน):**
    1.  `SELECT menu_name, price FROM menu WHERE store_id = {store_id}`
* **คำตอบ:** "ร้าน {store_name} มีเมนูอร่อย ๆ มากมายครับ เช่น ข้าวผัดกะเพราไก่ ราคา 50 บาท, ผัดซีอิ๊วหมู ราคา 55 บาท ครับ
    **คำสั่ง SQL ที่ใช้:**
    1. `SELECT menu_name, price FROM menu WHERE store_id = {store_id}`"

**B. การดึงข้อมูลโปรโมชั่น (บังคับกรองตาม Store ID: {store_id}):**
* **เมื่อลูกค้าถาม:** "มีโปรโมชั่นอะไรบ้าง"
* **แนวทาง:** บังคับใช้ Store ID ที่ได้รับ และ `CURRENT_DATE`
* **คำสั่ง SQL ที่ใช้ (แบบลดขั้นตอน):**
    1.  `SELECT promo_code, description, start_date, end_date FROM promotions WHERE end_date >= CURRENT_DATE AND store_id = {store_id}`
* **คำตอบ:** "ตอนนี้ร้าน {store_name} มีโปรโมชั่นสุดคุ้ม เช่น: โปรโมชั่นโค้ด: 'BUY3GET1' ซื้อ 3 จานฟรี 1 จาน (ถึง 31 ต.ค. 68) ...
    **คำสั่ง SQL ที่ใช้:**
    1. `SELECT promo_code, description, start_date, end_date FROM promotions WHERE end_date >= CURRENT_DATE AND store_id = {store_id}`"

**C. การแนะนำเมนูตามความต้องการของลูกค้า (ต้องสะสมเงื่อนไขกรอง):**
* **[Scenario C.1 - เริ่มต้นการสนทนา]:** * **เมื่อลูกค้าถาม:** "มีเมนูอะไรแนะนำบ้าง" **และ `chat_history` ไม่มีข้อมูลข้อจำกัด**
    * **คำตอบ:** "ได้เลยครับ! เพื่อให้ผมแนะนำเมนูที่ถูกใจที่สุด ไม่ทราบว่ามีวัตถุดิบไหนที่คุณชอบเป็นพิเศษ หรือมีอะไรที่คุณทานไม่ได้/แพ้ไหมครับ?" (ไม่ต้องใช้ Tool)
* **[Scenario C.2 - ดำเนินการค้นหาและกรองซ้ำ]:**
    * **เมื่อลูกค้าให้ข้อมูลข้อจำกัด (เช่น "ไม่ทานอาหารทะเล", "ไม่ทานเนื้อ") ไม่ว่าจะครั้งแรกหรือครั้งถัดไป**
    * **แนวทาง:** คุณต้อง **อ่านและรวบรวมข้อจำกัดด้านวัตถุดิบทั้งหมดจาก 'chat_history'** (ข้อความจาก Human และ AI) และ **ข้อความปัจจุบัน**
    * **จากนั้น:** ใช้ Store ID ที่ได้รับ ({store_id}) เพื่อค้นหาคำตอบด้วย SQL **โดยต้องใช้เงื่อนไข `NOT IN (SELECT...)` สำหรับทุกข้อจำกัดที่พบ**

    * **ตัวอย่างสถานการณ์ (Human History: "ไม่ทานทะเล" -> AI: "มีหมู เนื้อ" -> Human: "ไม่ทานเนื้อ"):**
        คำสั่ง SQL ที่ใช้ (สำหรับการกรอง "ทะเล" และ "เนื้อ"):
        1.  `SELECT T1.menu_name, T1.price FROM menu AS T1 WHERE T1.store_id = {store_id} AND T1.menu_id NOT IN (SELECT menu_id FROM ingredients WHERE ingredient_name LIKE '%ทะเล%') AND T1.menu_id NOT IN (SELECT menu_id FROM ingredients WHERE ingredient_name LIKE '%เนื้อ%')`
    * **คำตอบ:** "จากข้อจำกัด(ไม่ทานเนื้อ) ตอนนี้ทางร้านเราขอแนะนำ: [รายการเมนูที่เหลือ] ครับ/ค่ะ"
        คำสั่ง SQL ที่ใช้:
        1. `SELECT T1.menu_name, T1.price FROM menu AS T1 WHERE T1.store_id = {store_id} AND T1.menu_id NOT IN (SELECT menu_id FROM ingredients WHERE ingredient_name LIKE '%ทะเล%') AND T1.menu_id NOT IN (SELECT menu_id FROM ingredients WHERE ingredient_name LIKE '%เนื้อ%')`

**D. การค้นหาข้อมูลทั่วไป (บังคับใช้ RAG Tool):**
* **D.1 การค้นหาสำเร็จ:**
    * **เมื่อลูกค้าถาม:** "รับบัตรเครดิตไหม"
    * **แนวทาง:** ใช้ **knowledge_base_search Tool** เท่านั้น
    * **คำตอบ:** "ทางร้าน {store_name} ยินดีรับบัตรเครดิต Visa และ Mastercard ทุกประเภท ไม่มีค่าธรรมเนียมเพิ่มเติมค่ะ
        **Tool ที่ใช้:** knowledge_base_search"
* **D.2 การค้นหาไม่สำเร็จ (Fallback):**
    * **เมื่อลูกค้าถาม:** "ร้านมีบริการส่งด่วนไหม"
    * **แนวทาง:** ใช้ **knowledge_base_search Tool** เท่านั้น และ Tool ไม่พบข้อมูลใดๆ
    * **คำตอบ:** "ขออภัยค่ะ ทางร้าน {store_name} ยังไม่มีข้อมูลเกี่ยวกับเรื่องนี้ในระบบฐานความรู้ค่ะ คุณสามารถสอบถามเกี่ยวกับเมนูหรือโปรโมชั่นอื่น ๆ ได้เลยค่ะ
        **Tool ที่ใช้:** knowledge_base_search"

"""

def initialize_sql_agent_and_rag(db_uri, llm_choice, user_id: str, line_id: str):
    # 1. เตรียม SQL Database
    try:
        #หากต้องการทำให้ agent เห็นตารางทั้งหมด
        # db_instance = SQLDatabase.from_uri(db_uri)

        #เลือกเฉพาะตารางที่ LLM ต้องใช้ SQL (เช่น menu, promotions, tasks, ingredients, stores)
        db_instance = SQLDatabase.from_uri(
            db_uri, 
            include_tables=["menu", "promotions", "ingredients", "stores", "tasks"] 
            # ⚠️ ไม่รวม "knowledge_base"
        )
    except Exception as e:
        print(f"ERROR: Failed to initialize SQLDatabase from URI '{db_uri}': {e}")
        return None
    
    # 2. เตรียม LLM
    llm = None
    try:
        if "gemini-2.5-flash" in llm_choice:
            google_api_key = os.getenv("GOOGLE_API_KEY")
            if not google_api_key:
                print(f"ERROR: ไม่พบ GOOGLE_API_KEY สำหรับ {llm_choice}. โปรดตั้งค่าในไฟล์ .env.")
                return None
            llm = ChatGoogleGenerativeAI(model=llm_choice, temperature=0, google_api_key=google_api_key)
        else:
            print("ERROR: Model ที่เลือกไม่ถูกต้อง.")
            return None
    except Exception as e:
        print(f"Error initializing LLM ({llm_choice}): {e}")
        return None

    # 3. ดึงข้อมูลร้านค้าและสร้าง Prefix
    store_id, store_name = get_store_info_direct(user_id)
    if not store_id:
        print(f"WARNING: Could not find store_id for user {user_id}. Using default settings.")
        # กำหนดค่าเริ่มต้นถ้าหาไม่เจอ
        store_id = "DEFAULT" 
        store_name = "ร้านค้าทั่วไป"
        
    agent_prefix_final = create_agent_prefix_with_rag(store_id, store_name, user_id)

    if llm is None:
        return None 
    
    try:
        # 4. สร้าง SQL Toolkit
        sql_toolkit = SQLDatabaseToolkit(db=db_instance, llm=llm)
        sql_tools = sql_toolkit.get_tools()
        
        # 5. สร้าง RAG Tool (ChromaDB)
        rag_tools_list = []
        try:
            rag_retriever = initialize_rag_retriever(store_id) 
            if rag_retriever:
                rag_tool = get_rag_tool(rag_retriever)
                rag_tools_list = [rag_tool]
                print("RAG Tool (ChromaDB) initialized successfully.")
        except Exception as e:
            print(f"ERROR: RAG Tool setup failed: {e}")
            rag_tools_list = []
            
        # 6. รวม Tools ทั้งหมด (SQL Tools + RAG Tools)
        final_tools = sql_tools + rag_tools_list 

        # 7. โหลดประวัติการสนทนาและสร้าง Memory
        chat_history = load_history_from_db(user_id, line_id) 
        memory = ConversationBufferMemory(
            memory_key="chat_history", 
            return_messages=True,
            chat_memory=chat_history,
            k=8 
        )
        print("=== DEBUG MEMORY ===")
        print(memory.load_memory_variables({}))
        print("====================")

        # 8. สร้าง SQL Agent
        # ใช้ create_sql_agent เพื่อสร้าง agent object
        sql_agent_object = create_sql_agent(
            llm=llm,
            toolkit=SQLDatabaseToolkit(db=db_instance, llm=llm), # ต้องมี toolkit ตรงนี้เพื่อให้ Agent ทราบตาราง
            verbose=True,
            agent_type="openai-tools",
            prefix=agent_prefix_final,
            handle_parsing_errors=True,
            return_intermediate_steps=True
        )

        # 9. สร้าง AgentExecutor ที่ใช้ Tools และ Memory ที่รวมไว้
        # ⚠️ แทนที่จะใช้ sql_agent_object.tools เราใช้ final_tools
        agent_executor = AgentExecutor.from_agent_and_tools(
            agent=sql_agent_object.agent, # ใช้ Agent จาก create_sql_agent
            tools=final_tools,             # 🟢 ใช้ Tools ที่รวม RAG แล้ว
            memory=memory,
            verbose=True,
            handle_parsing_errors=True
        )
        return agent_executor 
    except Exception as e:
        print(f"ERROR: Failed to initialize agent: {e}")
        return None

# เพิ่มโค้ดสำหรับทดสอบ
# if __name__ == "__main__":
#     test_store_id = "2" # ใช้ Store ID ที่มีข้อมูล "รับบัตรเครดิตหรือไม่"
#     test_query = "รับบัตรเครดิตไหม"
    
#     # ต้องเรียก nest_asyncio.apply() ก่อนหากรันใน Thread ปกติ
#     import nest_asyncio
#     nest_asyncio.apply()
    
#     # 1. สร้าง Retriever
#     retriever = initialize_rag_retriever(test_store_id)
    
#     if retriever:
#         # 2. ทดสอบการค้นหาโดยตรง
#         print(f"\n--- TESTING RAG RETRIEVER for Store {test_store_id} ---")
#         docs = retriever.invoke(test_query)
        
#         if docs:
#             print(f"Found {len(docs)} documents:")
#             for i, doc in enumerate(docs):
#                 # 🟢 ตรวจสอบ content และ score (ถ้ามี)
#                 print(f"--- Document {i+1} ---")
#                 print(f"Content: {doc.page_content}")
#                 print(f"Metadata: {doc.metadata}")
#                 # print(f"Score: {doc.metadata.get('relevance_score', 'N/A')}") # บางครั้ง score ถูกซ่อน
#         else:
#             print("No documents found by the RAG retriever.")
#     else:
#         print("Retriever initialization failed.")