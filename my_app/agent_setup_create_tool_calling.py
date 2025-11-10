
import os
import nest_asyncio
from dotenv import load_dotenv
import sqlite3 
# 🟢 LangChain Core Imports
from langchain_core.documents import Document
from langchain.tools import Tool
from langchain.memory import ConversationBufferMemory
from langchain.agents import AgentExecutor, create_tool_calling_agent # 🟢 NEW AGENT
from langchain.prompts import ChatPromptTemplate # 🟢 NEW PROMPT
# 🟢 Google GenAI Imports
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import Chroma 
# 🟢 SQL Imports
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import SQLDatabaseToolkit
# 🟢 Utility Imports (Assumed to be in your project)
from history_utils import load_history_from_db 
from database import get_store_info_direct 

load_dotenv()
nest_asyncio.apply()

# =========================================================================
# 🟢 [RAG SECTION] (Functions remain largely the same, but simplified)
# =========================================================================

def fetch_knowledge_from_db(store_id: str):
    """Fetches knowledge from the knowledge_base table filtered by store_id."""
    DB_FILE_NAME = "store_database.db"
    conn = sqlite3.connect(DB_FILE_NAME)
    cursor = conn.cursor()
    
    knowledge_docs = []
    try:
        cursor.execute("""
            SELECT question_or_topic, answer_or_detail 
            FROM knowledge_base 
            WHERE store_id = ?
        """, (store_id,))
        
        results = cursor.fetchall()
        
        for topic, detail in results:
            content = f"หัวข้อ: {topic}\nรายละเอียด: {detail}"
            knowledge_docs.append(Document(page_content=content, metadata={"store_id": store_id, "topic": topic, "source": "knowledge_base_db"}))
            
    except sqlite3.Error as e:
        print(f"Database error fetching knowledge: {e}")
    finally:
        conn.close()
        
    return knowledge_docs

def initialize_rag_retriever(store_id: str):
    """
    Loads or creates a persistent ChromaDB store for the given store_id.
    """
    embeddings = GoogleGenerativeAIEmbeddings(model="text-embedding-004")
    
    persist_directory = "./chroma_vector_db/" 
    collection_name = f"store_{store_id}_knowledge"
    
    try:
        vector_store = Chroma(
            collection_name=collection_name, 
            embedding_function=embeddings, 
            persist_directory=persist_directory
        )
        
        collection_count = vector_store._collection.count()
        
        if collection_count == 0:
            print(f"Collection '{collection_name}' is empty. Indexing from SQLite...")
            documents = fetch_knowledge_from_db(store_id)
            
            if not documents:
                print(f"WARNING: No knowledge documents found for store {store_id}. RAG will be disabled.")
                return None
            
            vector_store.add_documents(documents)
            vector_store.persist()
            print(f"Indexing completed. {len(documents)} documents added.")
        else:
            print(f"Collection '{collection_name}' loaded from Disk ({collection_count} documents).")

        return vector_store.as_retriever(search_kwargs={"k": 3})

    except Exception as e:
        print(f"ERROR: ChromaDB initialization failed: {e}")
        return None

def get_rag_tool(retriever):
    """
    Creates a Tool for RAG search.
    """
    return Tool(
        name="knowledge_base_search",
        description="""ใช้สำหรับการค้นหาข้อมูลความรู้ทั่วไปของร้านค้า เช่น นโยบายการคืนสินค้า, นโยบายการจัดส่ง, ที่อยู่ร้าน, เบอร์โทร, หรือคำถามที่ไม่เกี่ยวกับเมนูหรือโปรโมชั่น ให้ส่งคำถามของลูกค้าเข้ามาใน tool นี้""",
        func=lambda query: retriever.invoke(query)
    )

# =========================================================================
# 🟢 [AGENT PREFIX/SYSTEM INSTRUCTION] - ปรับปรุงเพื่อ Native Tool Calling
# =========================================================================

def create_agent_prefix_with_rag(store_id, store_name, user_id):
    """
    Creates the system instruction for the Native Tool Calling Agent.
    """
    # ⚠️ ลบกฎที่ขัดแย้ง (เช่น Early Exit และการบังคับใส่ Prefix ในคำตอบสุดท้าย)
    # ⚠️ ปรับชื่อ Tool ให้ตรงกับ LangChain SQL Toolkit (sql_db_query, sql_db_schema)
    
    return f"""คุณคือ AI ผู้ช่วยขายของร้านอาหาร **"{store_name}"** 🍽️ (Store ID: {store_id}) หน้าที่ของคุณคือต้อนรับลูกค้า แนะนำเมนู เสนอโปรโมชั่น และรับออเดอร์อย่างรวดเร็วเพื่อปิดการขาย

คุณมีความเชี่ยวชาญในการใช้ Tools ที่คุณมีอยู่เพื่อจัดการข้อมูลของร้าน **{store_name}** คุณต้องปฏิบัติตามกฎเหล่านี้อย่างเคร่งครัด:

**กฎหลักและตรรกะการทำงาน (Core Logic):**
1.  **[การกรองข้อมูล (บังคับ)]:** คำถามใดๆ ที่เกี่ยวข้องกับเมนูหรือโปรโมชั่น **ให้ใช้ Store ID ที่ได้รับ ({store_id}) ในการกรองข้อมูลจากตาราง `menu` และ `promotions` ทันที ห้ามใช้ Subquery เพื่อหา Store ID ซ้ำ**
2.  **[การใช้ Tool ที่เหมาะสม]:**
    * **คำถามเกี่ยวกับเมนู/โปรโมชั่น/วัตถุดิบ:** ใช้ **sql_db_query Tool** เท่านั้น เพื่อดึงข้อมูลจากตาราง menu, promotions, และ **ingredients**
    * **คำถามเกี่ยวกับโครงสร้างฐานข้อมูล:** ใช้ **sql_db_schema Tool** เท่านั้น เพื่อดู Schema ของตารางที่เกี่ยวข้องก่อนเขียน Query ที่ซับซ้อน
    * **คำถามเกี่ยวกับ นโยบาย/ที่อยู่/เวลาทำการ/เบอร์โทร/ข้อมูลทั่วไป:** ใช้ **knowledge_base_search Tool** เท่านั้น
3.  **[ข้อจำกัด SQL]:** ใช้ได้เฉพาะ **`SELECT`** เท่านั้น **ห้ามใช้ `INSERT`, `UPDATE`, `DELETE`, `DROP` เด็ดขาด**
4.  **[ข้อจำกัดคำตอบ]:** ห้ามตอบคำถามเกี่ยวกับโครงสร้างฐานข้อมูล ให้ตอบว่า: "ฉันไม่สามารถให้ข้อมูลเกี่ยวกับโครงสร้างภายในของระบบได้ค่ะ คุณสามารถสอบถามเกี่ยวกับเมนูหรือโปรโมชั่นต่าง ๆ ได้เลยค่ะ"

5.  **[การใช้ Memory/กรองเมนูตามวัตถุดิบ - **ตรรกะการกรองที่หายไป**]:**
    * คุณต้องใช้ **'chat_history'** เพื่อรวบรวมข้อจำกัดด้านวัตถุดิบทั้งหมดที่ลูกค้าเคยระบุ (เช่น 'กุ้ง', 'ทะเล', 'เนื้อวัว')
    * เมื่อมีการแนะนำเมนู **คุณต้องเขียน SQL Query โดยใช้การ JOIN ตาราง `menu` และ `ingredients`** และใช้เงื่อนไข **`NOT IN`** เพื่อยกเว้นเมนูที่มีวัตถุดิบต้องห้ามของลูกค้าเหล่านั้น

6.  **[Sales & Output Focus - กฎควบคุมการตอบกลับ]:**
    * **ความกระชับ:** คำตอบต้องกระชับ มุ่งเน้นการให้ข้อมูลที่จำเป็น (ชื่อเมนู, ราคา, จุดเด่น, ที่อยู่) เพื่อให้ลูกค้าตัดสินใจสั่งซื้อทันที
    * **กฎบังคับการจัดรูปแบบลิสต์:** **คุณคือผู้เชี่ยวชาญการจัดรูปแบบการนำเสนอข้อมูล** เมื่อคุณนำเสนอรายการ (เช่น เมนู, โปรโมชั่น, ข้อมูลจาก RAG) ที่มีมากกว่า 2 รายการ **คุณต้องใช้เครื่องหมายยัติภังค์ (`-`) ในการขึ้นรายการเท่านั้น** ห้ามใช้เครื่องหมายดอกจัน (\`*\`), ตัวเลข หรือเครื่องหมายจุดกลม (`•`) ในการจัดรูปแบบลิสต์โดยเด็ดขาด การใช้ยัติภังค์ (`-`) เป็นรูปแบบมาตรฐานที่บังคับใช้เสมอ
    * **ห้ามเปิดเผย Tool/SQL:** **ห้ามใส่ SQL Query, Tool Command, หรือรายละเอียดการทำงานของ Agent ลงในคำตอบสุดท้ายที่ส่งถึงลูกค้าเด็ดขาด** (ข้อมูลนี้ใช้สำหรับการบันทึกหลังบ้านเท่านั้น)

7.  **[Early Exit Logic - ตรรกะการตัดสินใจ]:**
    * หากคุณไม่จำเป็นต้องใช้ Tool ใดๆ (เช่น การทักทาย การขอบคุณ) ให้ตอบกลับเป็นข้อความที่เป็นมิตรทันที โดยใช้รูปแบบแนะนำการสอบถามดังนี้:
      ยินดีต้อนรับค่ะ! คุณสามารถสอบถามเกี่ยวกับ:
      - เมนูอาหาร: มีเมนูอะไรบ้าง, ราคาเท่าไหร่, แนะนำเมนู (พร้อมแจ้งข้อจำกัด)
      - โปรโมชั่น: มีโปรโมชั่นอะไรบ้าง
      - ข้อมูลร้าน: ที่อยู่, เบอร์โทรศัพท์, เวลาทำการ, หรือนโยบายต่างๆ ของร้าน
      พร้อมให้บริการค่ะ!
    * **[Pre-Tool-Call Logic สำหรับเมนูแนะนำ]:** หากลูกค้าถามคำถามที่เกี่ยวข้องกับการ "แนะนำเมนู" และคุณตรวจสอบ **'chat_history' แล้วพบว่ายังไม่มีข้อจำกัด** (เช่น ไม่ทาน/แพ้) ที่ลูกค้าเคยระบุ **คุณต้องตอบกลับทันทีด้วยการสอบถามข้อจำกัด (เช่น วัตถุดิบที่ไม่ทานหรือไม่ชอบ) โดยไม่ต้องเรียก Tool ใดๆ เลย**

**ตัวอย่างการใช้ SQL (สำหรับการอ้างอิงและกรองวัตถุดิบ):**
* **เมนูที่ไม่มีกุ้ง (แนะนำให้ใช้โครงสร้างนี้เพื่อการกรองวัตถุดิบ):** `SELECT T1.menu_name, T1.price FROM menu AS T1 WHERE T1.store_id = {store_id} AND T1.menu_id NOT IN (SELECT menu_id FROM ingredients WHERE ingredient_name LIKE '%กุ้ง%' OR ingredient_name LIKE '%ทะเล%')`
* **โปรโมชั่น:** `SELECT * FROM promotions WHERE end_date >= CURRENT_DATE AND store_id = {store_id}`
"""

# =========================================================================
# 🟢 [AGENT INITIALIZATION] - เปลี่ยนเป็น Native Tool Calling Agent
# =========================================================================

def initialize_native_tool_calling_agent(db_uri, llm_choice, user_id: str, line_id: str):
    
    # 1. เตรียม SQL Database
    try:
        db_instance = SQLDatabase.from_uri(
            db_uri, 
            include_tables=["menu", "promotions", "ingredients", "stores", "tasks"] 
        )
    except Exception as e:
        print(f"ERROR: Failed to initialize SQLDatabase from URI '{db_uri}': {e}")
        return None
    
    # 2. เตรียม LLM
    google_api_key = os.getenv("GOOGLE_API_KEY")
    if not google_api_key:
        print(f"ERROR: ไม่พบ GOOGLE_API_KEY สำหรับ {llm_choice}. โปรดตั้งค่าในไฟล์ .env.")
        return None
        
    llm = ChatGoogleGenerativeAI(model=llm_choice, temperature=0, google_api_key=google_api_key)

    # 3. ดึงข้อมูลร้านค้าและสร้าง Prefix
    store_id, store_name = get_store_info_direct(user_id)
    if not store_id:
        store_id = "DEFAULT" 
        store_name = "ร้านค้าทั่วไป"
        
    agent_prefix_final = create_agent_prefix_with_rag(store_id, store_name, user_id)

    # 4. สร้าง SQL Tools และกรอง
    sql_toolkit = SQLDatabaseToolkit(db=db_instance, llm=llm)
    all_sql_tools = sql_toolkit.get_tools()
    
    # 🟢 เลือกเฉพาะ Tools ที่จำเป็น
    sql_tools = [
        t for t in all_sql_tools 
        if t.name in ["sql_db_query", "sql_db_schema"] 
    ]
    # **Rename Tools (Optional):** หากต้องการให้ชื่อ Tool ใน Description ดูเป็นมิตรกับ Gemini มากขึ้น

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
        
    # 6. รวม Tools ทั้งหมด
    final_tools = sql_tools + rag_tools_list 

    # 7. โหลดประวัติการสนทนาและสร้าง Memory
    chat_history = load_history_from_db(user_id, line_id) 
    memory = ConversationBufferMemory(
        memory_key="chat_history", 
        return_messages=True,
        chat_memory=chat_history,
        k=8 
    )

    # 8. สร้าง Prompt Template สำหรับ Tool Calling Agent
    # ChatPromptTemplate นี้จะใส่ System Instruction, History, User Input และ Scratchpad
    prompt_template = ChatPromptTemplate.from_messages(
        [
            ("system", agent_prefix_final),
            ("placeholder", "{chat_history}"), 
            ("human", "{input}"),
            ("placeholder", "{agent_scratchpad}"), 
        ]
    )

    # 9. สร้าง Native Tool Calling Agent
    agent = create_tool_calling_agent( 
        llm=llm,
        tools=final_tools,
        prompt=prompt_template
    )

    # 10. สร้าง Agent Executor
    agent_executor = AgentExecutor(
        agent=agent,
        tools=final_tools,             
        memory=memory,
        verbose=True,
        handle_parsing_errors=True, # ให้ Agent พยายามกู้คืนจากข้อผิดพลาด
        return_intermediate_steps=True,
        output_key="output" 
    )
    
    return agent_executor 

# ------------------------------------------------------------------
# 💡 [USAGE EXAMPLE]
# ------------------------------------------------------------------

# if __name__ == "__main__":
#     # ⚠️ ต้องแน่ใจว่าได้ตั้งค่า .env และไฟล์ 'store_database.db', 'history_utils.py', 'database.py' ถูกต้อง
    
#     # กำหนดค่าทดสอบ
#     TEST_USER_ID = "test_user_1"
#     TEST_LINE_ID = "test_line_1"
#     TEST_DB_URI = "sqlite:///store_database.db" # ⚠️ เปลี่ยนตาม Path จริงของคุณ
#     TEST_MODEL = "gemini-2.5-flash"
    
#     print(f"Initializing Native Tool Calling Agent with model: {TEST_MODEL}...")
    
#     try:
#         agent_executor = initialize_native_tool_calling_agent(
#             db_uri=TEST_DB_URI, 
#             llm_choice=TEST_MODEL, 
#             user_id=TEST_USER_ID, 
#             line_id=TEST_LINE_ID
#         )

#         if agent_executor:
#             print("\n--- AGENT INITIALIZED. TESTING ---")
            
#             # 1. ทดสอบการทักทาย (ควรตอบกลับโดยตรงโดยไม่เรียก Tool)
#             print("\n>> User: สวัสดีครับ")
#             response = agent_executor.invoke({"input": "สวัสดีครับ"})
#             print(f"<< Agent: {response['output']}")
            
#             # 2. ทดสอบ RAG Tool (ควรเรียก knowledge_base_search)
#             print("\n>> User: ร้านเปิดกี่โมงครับ")
#             response = agent_executor.invoke({"input": "ร้านเปิดกี่โมงครับ"})
#             print(f"<< Agent: {response['output']}")

#             # 3. ทดสอบ SQL Tool (ควรเรียก sql_db_query)
#             print("\n>> User: มีโปรโมชั่นอะไรบ้าง")
#             response = agent_executor.invoke({"input": "มีโปรโมชั่นอะไรบ้าง"})
#             print(f"<< Agent: {response['output']}")
            
#         else:
#             print("Failed to initialize Agent Executor.")

#     except Exception as e:
#         print(f"\nFATAL ERROR during testing: {e}")