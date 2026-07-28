import streamlit as st
import os
import tempfile
import datetime
import sqlite3
import json
import pandas as pd
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_groq import ChatGroq
from langchain.prompts import PromptTemplate

# ==========================================
# Configuration & Setup
# ==========================================
st.set_page_config(page_title="Tamil Nadu HR Smart Assistant", page_icon="🏢", layout="wide")

DEFAULT_GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# ==========================================
# Database Setup Setup
# ==========================================
def get_db():
    if 'db_conn' not in st.session_state:
        conn = sqlite3.connect('hr_assistant.db', check_same_thread=False)
        conn.row_factory = sqlite3.Row
        st.session_state.db_conn = conn
        
        # Initialize tables
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                email TEXT PRIMARY KEY,
                name TEXT,
                emp_id TEXT,
                dept TEXT,
                role TEXT,
                password TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                user_email TEXT,
                question TEXT,
                answer TEXT,
                status TEXT,
                confidence REAL,
                distance REAL,
                depth INTEGER,
                chunks TEXT,
                topic TEXT
            )
        ''')
        # Insert default Admin if not exists
        cursor.execute("SELECT email FROM users WHERE email='admin@tn.gov.in'")
        if not cursor.fetchone():
            cursor.execute("INSERT INTO users (email, name, emp_id, dept, role, password) VALUES (?, ?, ?, ?, ?, ?)",
                           ('admin@tn.gov.in', 'System Admin', 'EMP001', 'IT', 'Admin', 'admin'))
        conn.commit()
    return st.session_state.db_conn


# ==========================================
# Caching Local Embeddings Model
# ==========================================
@st.cache_resource(show_spinner="Loading Embeddings Model...")
def get_embeddings():
    """ Load HuggingFace sentence transformer embeddings """
    return HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

# ==========================================
# Session State Initialization & Mock DB
# ==========================================
def init_session_state():
    get_db() # Ensure DB is initialized
    
    # Routing
    if 'page' not in st.session_state:
        st.session_state.page = 'welcome'
    if 'current_user' not in st.session_state:
        st.session_state.current_user = None
        
    # RAG State
    if 'vector_store' not in st.session_state:
        st.session_state.vector_store = None
    if 'processed_filename' not in st.session_state:
        st.session_state.processed_filename = None

    # App Settings
    if 'groq_api_key' not in st.session_state:
        st.session_state.groq_api_key = DEFAULT_GROQ_API_KEY
    if 'retrieval_depth' not in st.session_state:
        st.session_state.retrieval_depth = 3
    if 'threshold' not in st.session_state:
        st.session_state.threshold = 1.0

init_session_state()

# Helper for Navigation
def navigate_to(page_name):
    st.session_state.page = page_name

def logout():
    st.session_state.current_user = None
    navigate_to('welcome')

# ==========================================
# UI Modules (Pages)
# ==========================================

def render_welcome():
    st.markdown("<h1 style='text-align: center;'>🏢 Tamil Nadu HR Smart Assistant</h1>", unsafe_allow_html=True)
    st.markdown("<h4 style='text-align: center; color: gray;'>Enterprise HR Policy Intelligence Platform</h4>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center;'>1. Upload Policy &rarr; 2. Ask Questions &rarr; 3. Get Instant Answers</p>", unsafe_allow_html=True)
    
    st.write("")
    st.write("")
    col1, col2, col3, col4 = st.columns(4)
    with col2:
        if st.button("🔑 Login", use_container_width=True, type="primary"):
            navigate_to('login')
    with col3:
        if st.button("🆕 Sign Up", use_container_width=True):
            navigate_to('signup')

def render_signup():
    st.title("🆕 Sign Up")
    st.markdown("Create a new account to access the enterprise HR assistant.")
    
    with st.form("signup_form"):
        name = st.text_input("Full Name")
        emp_id = st.text_input("Employee ID")
        email = st.text_input("Email")
        dept = st.text_input("Department")
        role = st.selectbox("Role", ["Employee", "HR Manager", "Admin"])
        password = st.text_input("Password", type="password")
        confirm_password = st.text_input("Confirm Password", type="password")
        
        submitted = st.form_submit_button("Register")
        if submitted:
            if password != confirm_password:
                st.error("Passwords do not match!")
            elif not email or not password or not name:
                st.error("Please fill all required fields.")
            else:
                conn = get_db()
                cursor = conn.cursor()
                cursor.execute("SELECT email FROM users WHERE email=?", (email,))
                if cursor.fetchone():
                    st.error("Email already registered!")
                else:
                    cursor.execute("INSERT INTO users (email, name, emp_id, dept, role, password) VALUES (?, ?, ?, ?, ?, ?)", 
                                   (email, name, emp_id, dept, role, password))
                    conn.commit()
                    st.success("Account created successfully! Please login.")
                    navigate_to('login')
                    st.rerun()

    if st.button("Already have an account? → Login"):
        navigate_to('login')

def render_login():
    st.title("🔑 Login")
    
    with st.form("login_form"):
        email = st.text_input("Email / Employee ID")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")
        
        if submitted:
            conn = get_db()
            cursor = conn.cursor()
            # simple check since emp_id might be used as email in UI fallback
            cursor.execute("SELECT * FROM users WHERE (email=? OR emp_id=?) AND password=?", (email, email, password))
            user_row = cursor.fetchone()
            if user_row:
                st.session_state.current_user = dict(user_row)
                st.success(f"Welcome back, {user_row['name']}!")
                navigate_to('dashboard')
                st.rerun()
            else:
                st.error("Invalid email/Employee ID or password.")
                
    st.markdown("---")
    st.write("*(Hint: Use `admin@tn.gov.in` / `admin` for testing Admin access)*")
    if st.button("← Back to Welcome"):
        navigate_to('welcome')

def render_sidebar():
    user = st.session_state.current_user
    st.sidebar.title("🏢 Navigation")
    st.sidebar.markdown(f"**User:** {user['name']}")
    st.sidebar.markdown(f"**Role:** `{user['role']}`")
    st.sidebar.markdown("---")
    
    if st.sidebar.button("🏠 Dashboard", use_container_width=True):
        navigate_to('dashboard')
        
    if user['role'] in ["HR Manager", "Admin"]:
        if st.sidebar.button("📄 Upload Policy", use_container_width=True):
            navigate_to('upload')
    
    if st.sidebar.button("💬 Chat / Ask Question", use_container_width=True):
        navigate_to('chat')
        
    if user['role'] in ["HR Manager", "Admin"]:
        if st.sidebar.button("📈 Insights Dashboard", use_container_width=True):
            navigate_to('insights')
            
    st.sidebar.markdown("---")
    st.sidebar.subheader("⚙️ Settings")
    
    st.session_state.groq_api_key = st.sidebar.text_input("Groq API Key", type="password", value=st.session_state.groq_api_key)
    st.session_state.retrieval_depth = st.sidebar.selectbox("Retrieval Depth (k)", options=[1, 3, 5], index=[1,3,5].index(st.session_state.retrieval_depth))
    st.session_state.threshold = st.sidebar.slider("Threshold Tuning", min_value=0.0, max_value=2.0, value=st.session_state.threshold, step=0.05)
    
    with st.sidebar.expander("Chat History Preview"):
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT question, status FROM chat_history WHERE user_email=? ORDER BY id DESC LIMIT 5", (user['email'],))
        recent_chats = cursor.fetchall()
        if not recent_chats:
            st.write("No questions asked yet.")
        for row in recent_chats:
            st.markdown(f"**Q:** {row['question']}")
            st.caption(f"Status: {row['status']}")
            st.markdown("---")
            
    st.sidebar.markdown("---")
    if st.sidebar.button("Logout", type="primary", use_container_width=True):
        logout()

def render_dashboard():
    user = st.session_state.current_user
    st.title("🏠 Main Dashboard")
    st.markdown(f"### Welcome back, {user['name']} 👋")
    st.info(f"You are logged in as **{user['role']}** from the **{user['dept']}** department.")
    
    st.markdown("---")
    st.markdown("### Quick Actions")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("#### Ask a Question")
        st.write("Query the AI about the latest HR policies.")
        if st.button("Go to Chat", use_container_width=True):
            navigate_to('chat')
            st.rerun()
            
    if user['role'] in ["HR Manager", "Admin"]:
        with col2:
            st.markdown("#### Update Policies")
            st.write("Upload a new or updated HR Policy PDF.")
            if st.button("Upload Document", use_container_width=True):
                navigate_to('upload')
                st.rerun()
                
        with col3:
            st.markdown("#### View Analytics")
            st.write("Monitor organizational HR queries.")
            if st.button("Insights Dashboard", use_container_width=True):
                navigate_to('insights')
                st.rerun()
    else:
        with col2:
            st.markdown("#### Your History")
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM chat_history WHERE user_email=?", (user['email'],))
            count = cursor.fetchone()[0]
            st.write(f"You have asked {count} questions so far.")

def render_upload():
    st.title("📄 Upload HR Policy")
    st.markdown("Upload and index a new HR Policy PDF document to serve as the ground truth for AI answers.")
    
    if st.session_state.processed_filename:
        st.info(f"Currently Active Policy: **{st.session_state.processed_filename}**")
        
    uploaded_file = st.file_uploader("Drag & Drop PDF uploader", type="pdf")

    if uploaded_file is not None:
        if st.button("Process Document", type="primary"):
            st.session_state.vector_store = None
            st.session_state.processed_filename = uploaded_file.name
            
            with st.spinner("Extracting → Embedding → Indexing..."):
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                    tmp_file.write(uploaded_file.getvalue())
                    tmp_file_path = tmp_file.name

                try:
                    loader = PyPDFLoader(tmp_file_path)
                    documents = loader.load()

                    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=100)
                    chunks = text_splitter.split_documents(documents)

                    embeddings = get_embeddings()

                    import chromadb
                    # Use a persistent client with a fixed temp dir so Streamlit doesn't lose the DB connection
                    if 'chroma_store_dir' not in st.session_state:
                         st.session_state.chroma_store_dir = tempfile.mkdtemp(prefix="chroma_hr_")
                         
                    client = chromadb.PersistentClient(path=st.session_state.chroma_store_dir)
                    
                    vector_store = Chroma.from_documents(
                        documents=chunks,
                        embedding=embeddings,
                        client=client,
                        collection_name="hr_policy_collection",
                        collection_metadata={"hnsw:space": "cosine"}
                    )
                    
                    st.session_state.vector_store = vector_store
                    st.success(f"✅ Policy Indexed Successfully: {uploaded_file.name}")
                    
                    with st.expander("Document Summary Preview"):
                        st.write(f"Total Pages Processed: {len(documents)}")
                        st.write(f"Total Text Chunks Created: {len(chunks)}")
                        
                except Exception as e:
                    st.error(f"Error processing the PDF: {str(e)}")
                finally:
                    os.unlink(tmp_file_path)
                    
            if st.button("Proceed to Q&A"):
                navigate_to('chat')
                st.rerun()

def render_chat():
    st.title("💬 Ask HR Question")
    st.markdown("Chat with the AI HR Assistant strictly based on the uploaded HR policy.")
    
    if not st.session_state.vector_store:
        st.warning("⚠️ No HR Policy indexed. Please contact HR/Admin to upload a policy document.")
        return
        
    # Suggested quick questions
    st.markdown("**Suggested quick questions:**")
    colA, colB, colC = st.columns(3)
    preset_q = ""
    if colA.button("What is the leave policy?"): preset_q = "What is the leave policy?"
    if colB.button("Is remote work allowed?"): preset_q = "Is remote work allowed?"
    if colC.button("What is maternity leave duration?"): preset_q = "What is maternity leave duration?"
    
    question = st.chat_input("Ask your HR question...") or preset_q
    
    # Display Chat
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM chat_history WHERE user_email=? ORDER BY id ASC", (st.session_state.current_user['email'],))
    user_chat_history = cursor.fetchall()
    
    for msg in user_chat_history:
        with st.chat_message("user"):
            st.write(msg['question'])
        with st.chat_message("assistant"):
            if msg['status'] == "Not Answered":
                st.warning(f"⚠️ **Policy Gap Alert:** {msg['answer']}")
            else:
                st.write(msg['answer'])
                
            with st.expander("Answer Details & Analytics"):
                st.markdown(f"**Confidence:** {msg['confidence']:.2f}% | **Retrieval Distance:** {msg['distance']:.4f} | **Depth:** k={msg['depth']}")
                chunks = json.loads(msg['chunks']) if msg['chunks'] else []
                if chunks:
                    st.markdown("**Retrieved Chunks:**")
                    for i, chunk in enumerate(chunks):
                        st.info(f"Chunk {i+1}: {chunk}")
                        
            st.download_button("Download Answer", data=msg['answer'], file_name="hr_answer.txt", mime="text/plain", key=f"dl_{msg['id']}")

    if question:
        with st.chat_message("user"):
            st.write(question)
            
        with st.chat_message("assistant"):
            if not st.session_state.groq_api_key.strip():
                st.error("Please enter your Groq API Key in the sidebar.")
                return

            with st.spinner("Searching and Reasoning..."):
                try:
                    # Retrieve
                    k_depth = st.session_state.retrieval_depth
                    results = st.session_state.vector_store.similarity_search_with_score(question, k=k_depth)
                    
                    if not results:
                        st.error("No context found in the database.")
                    else:
                        best_doc, best_score = results[0]
                        confidence = max(0.0, min(100.0, (1 - (best_score / 2.0)) * 100))
                        
                        # Set default text
                        answer_text = ""
                        status = "Answered"
                        
                        if best_score > st.session_state.threshold:
                            status = "Not Answered"
                            answer_text = "Information not found in policy document."
                        else:
                            # Generate Answer
                            context_texts = [doc.page_content for doc, _ in results]
                            context = "\n\n---\n\n".join(context_texts)
                            
                            llm = ChatGroq(
                                temperature=0, 
                                groq_api_key=st.session_state.groq_api_key, 
                                model_name="llama-3.1-8b-instant"
                            )
                            
                            prompt_template = """
You are a professional enterprise HR assistant named 'Tamil Nadu HR Smart Assistant'. 
You must answer the user's question STRICTLY using only the provided context below.

Rules:
1. Do not use any outside knowledge or hallucinate.
2. If the answer cannot be explicitly found in or logically deduced from the provided context, you must respond EXACTLY with: "Information not found in policy document."
3. Keep your tone professional, polite, and crystal clear. Format nicely.

Context:
{context}

Question: {question}

Answer:"""
                            prompt = PromptTemplate(template=prompt_template, input_variables=["context", "question"])
                            chain = prompt | llm
                            response = chain.invoke({"context": context, "question": question})
                            
                            answer_text = response.content
                            if "Information not found in policy document" in answer_text:
                                status = "Not Answered"
                                
                        # Topic detection mock (simple keyword matching)
                        topic = "Others"
                        q_lower = question.lower()
                        if "leave" in q_lower: topic = "Leave"
                        elif "remote" in q_lower or "work from home" in q_lower: topic = "Remote Work"
                        elif "salary" in q_lower or "pay" in q_lower: topic = "Salary"
                        
                        chunks_json = json.dumps([doc.page_content for doc, _ in results]) if status == "Answered" else "[]"
                        
                        # Store in DB
                        cursor.execute('''
                            INSERT INTO chat_history (timestamp, user_email, question, answer, status, confidence, distance, depth, chunks, topic)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (datetime.datetime.now().isoformat(), st.session_state.current_user["email"], 
                              question, answer_text, status, confidence, best_score, k_depth, chunks_json, topic))
                        conn.commit()
                        
                        # Rerun to show display loop
                        st.rerun()

                except Exception as e:
                    st.error(f"Error during Q&A: {str(e)}")

def render_insights():
    st.title("📈 Insights Dashboard")
    st.markdown("Analytics overview of HR queries across the organization.")
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM chat_history")
    total = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM chat_history WHERE status='Answered'")
    ans = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM chat_history WHERE status='Not Answered'")
    not_ans = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT AVG(confidence) FROM chat_history WHERE status='Answered'")
    avg_conf_row = cursor.fetchone()
    avg_conf = avg_conf_row[0] if avg_conf_row and avg_conf_row[0] is not None else 0.0
    
    ans_ratio = (ans / total * 100) if total > 0 else 0.0
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Questions Asked", total)
    with col2:
        st.metric("Answered vs Not Answered", f"{ans} / {not_ans}")
    with col3:
        st.metric("Average Confidence", f"{avg_conf:.1f}%")
    with col4:
        st.metric("Policy Coverage", f"{ans_ratio:.1f}%", help="Percentage of questions successfully answered")

    st.markdown("---")
    
    colA, colB = st.columns(2)
    with colA:
        st.subheader("Most Asked HR Topics")
        cursor.execute("SELECT topic, COUNT(*) as count FROM chat_history GROUP BY topic")
        topics_data = cursor.fetchall()
        
        if topics_data:
            # fill missing topics for consistent display
            topic_dict = {"Leave": 0, "Remote Work": 0, "Salary": 0, "Others": 0}
            for row in topics_data:
                topic_dict[row['topic']] = row['count']
                
            topics_df = pd.DataFrame(list(topic_dict.items()), columns=['Topic', 'Count'])
            st.bar_chart(topics_df.set_index('Topic'))
        else:
            st.info("No topic data available yet.")
        
    with colB:
        st.subheader("Risk Alert Indicator")
        if not_ans > ans and total > 5:
            st.error("🚨 **High Risk**: Too many unanswered questions. Consider updating the HR Policy document to cover missing topics.")
        elif not_ans > 0:
            st.warning("⚠️ **Moderate Risk**: Some questions were unanswerable. Check recent chat history to identify policy gaps.")
        elif total > 0:
            st.success("✅ **Healthy**: High policy coverage based on recent queries.")
        else:
            st.info("Awaiting queries to generate risk score.")
            
        st.markdown("### Recent Unanswered Queries")
        cursor.execute("SELECT question FROM chat_history WHERE status='Not Answered' ORDER BY id DESC LIMIT 5")
        unanswered = cursor.fetchall()
        if not unanswered:
            st.write("No unanswered queries recently.")
        for u in unanswered:
            st.markdown(f"- {u['question']}")


# ==========================================
# Main Router
# ==========================================
def main():
    if not st.session_state.current_user and st.session_state.page not in ['welcome', 'login', 'signup']:
        st.session_state.page = 'welcome'
        
    if st.session_state.current_user:
        render_sidebar()
        
    page = st.session_state.page
    
    if page == 'welcome':
        render_welcome()
    elif page == 'login':
        render_login()
    elif page == 'signup':
        render_signup()
    elif page == 'dashboard':
        render_dashboard()
    elif page == 'upload':
        if st.session_state.current_user['role'] in ["HR Manager", "Admin"]:
            render_upload()
        else:
            st.error("Access Denied.")
    elif page == 'chat':
        render_chat()
    elif page == 'insights':
        if st.session_state.current_user['role'] in ["HR Manager", "Admin"]:
            render_insights()
        else:
            st.error("Access Denied.")

if __name__ == "__main__":
    main()
