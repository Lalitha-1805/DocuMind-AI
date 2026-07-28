import os
import tempfile
import datetime
import sqlite3
import json
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_groq import ChatGroq
from langchain.prompts import PromptTemplate
import chromadb
import re
import boto3
from botocore.exceptions import ClientError

# Bedrock & Glue Clients
bedrock_runtime = boto3.client('bedrock-runtime')
bedrock_agent_runtime = boto3.client('bedrock-agent-runtime')
glue = boto3.client('glue')

# ==========================================
# Application Setup
# ==========================================
app = FastAPI(title="AI-Powered Document Management System API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files for the frontend
app.mount("/static", StaticFiles(directory="static"), name="static")

# ==========================================
# Database Setup
# ==========================================
def get_db():
    conn = sqlite3.connect('hr_assistant.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            name TEXT,
            profession TEXT,
            password TEXT,
            profile_pic TEXT
        )
    ''')
    # Migration: Ensure all columns exist for users
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN name TEXT")
    except sqlite3.OperationalError: pass
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN profession TEXT")
    except sqlite3.OperationalError: pass
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN profile_pic TEXT")
    except sqlite3.OperationalError: pass
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
            topic TEXT,
            conversation_id TEXT
        )
    ''')
    # Migration: Ensure conversation_id exists for existing tables
    try:
        cursor.execute("ALTER TABLE chat_history ADD COLUMN conversation_id TEXT")
    except sqlite3.OperationalError:
        pass # Already exists
    # Insert default Admin if not exists
    cursor.execute("SELECT email FROM users WHERE email='admin@dms.gov.in'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO users (email, name, profession, password) VALUES (?, ?, ?, ?)",
                        ('admin@dms.gov.in', 'System Admin', 'Administrator', 'admin'))
    conn.commit()
    conn.close()

init_db()

# ==========================================
# Global RAG State
# ==========================================
# In a real production app, you might manage these via a cleaner dependency injection or singleton pattern
# For this migration, we'll keep them in a global dict to simulate session state across the app
global_vector_store = None
global_embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
chroma_client = None

# S3 Configuration
S3_BUCKET_NAME = "tn-dms-document-lake"
s3_client = boto3.client('s3')

# Bedrock Knowledge Base Configuration
BEDROCK_KNOWLEDGE_BASE_ID = os.environ.get("BEDROCK_KB_ID", "LO6Q1TKIYM")
BEDROCK_MODEL_ARN = "arn:aws:bedrock:ap-south-1::foundation-model/anthropic.claude-3-sonnet-20240229-v1:0"
GLUE_DATABASE_NAME = "tn_dms_catalog"
GLUE_CRAWLER_NAME = "tn_dms_pdf_crawler"

# ==========================================
# Models
# ==========================================
class UserResponse(BaseModel):
    email: str
    name: str
    profession: str
    profile_pic: Optional[str] = None

class UpdateProfileRequest(BaseModel):
    email: str
    name: Optional[str] = None
    profession: Optional[str] = None
    profile_pic: Optional[str] = None # Base64 string

class SignupRequest(BaseModel):
    name: str
    email: str
    profession: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class ChatRequest(BaseModel):
    user_email: str
    question: str
    groq_api_key: str
    retrieval_depth: int = 3
    threshold: float = 1.0
    conversation_id: Optional[str] = None

class SummarizeRequest(BaseModel):
    user_email: str
    filename: str
    groq_api_key: str

# ==========================================
# Endpoints: Frontend routing
# ==========================================
@app.get("/")
async def read_index():
    return FileResponse("static/index.html")

@app.get("/signup")
async def read_signup():
    return FileResponse("static/signup.html")

@app.get("/login")
async def read_login():
    return FileResponse("static/login.html")

@app.get("/dashboard")
async def read_dashboard():
    return FileResponse("static/dashboard.html")

@app.get("/upload")
async def read_upload():
    return FileResponse("static/upload.html")

@app.get("/chat")
async def read_chat():
    return FileResponse("static/chat.html")

@app.get("/insights")
async def read_insights():
    return FileResponse("static/insights.html")

@app.get("/settings")
async def read_settings():
    return FileResponse("static/settings.html")

@app.get("/profile")
async def read_profile():
    return FileResponse("static/profile.html")

@app.get("/logout")
async def read_logout():
    return FileResponse("static/logout.html")

@app.get("/leave-calculator")
async def read_leave_calculator():
    return FileResponse("static/leave-calculator.html")

# ==========================================
# Endpoints: Auth
# ==========================================
@app.post("/api/signup")
async def signup(req: SignupRequest):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT email FROM users WHERE email=?", (req.email,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Email already registered!")
    
    cursor.execute("INSERT INTO users (email, name, profession, password) VALUES (?, ?, ?, ?)", 
                    (req.email, req.name, req.profession, req.password))
    conn.commit()
    conn.close()
    return {"message": "Account created successfully"}

@app.post("/api/login")
async def login(req: LoginRequest):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT email, name, profession, profile_pic, password FROM users WHERE email=?", (req.email,))
    user = cursor.fetchone()
    conn.close()
    
    if not user or user['password'] != req.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    return {
        "user": {
            "email": user["email"], 
            "name": user["name"], 
            "profession": user["profession"],
            "profile_pic": user["profile_pic"]
        }
    }

@app.put("/api/user/profile")
async def update_profile(req: UpdateProfileRequest):
    conn = get_db()
    cursor = conn.cursor()
    
    updates = []
    params = []
    if req.name:
        updates.append("name = ?")
        params.append(req.name)
    if req.profession:
        updates.append("profession = ?")
        params.append(req.profession)
    if req.profile_pic:
        updates.append("profile_pic = ?")
        params.append(req.profile_pic)
        
    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")
        
    params.append(req.email)
    query = f"UPDATE users SET {', '.join(updates)} WHERE email = ?"
    cursor.execute(query, params)
    conn.commit()
    
    # Get updated user data
    cursor.execute("SELECT email, name, profession, profile_pic FROM users WHERE email=?", (req.email,))
    user = cursor.fetchone()
    conn.close()
    
    return {
        "email": user["email"],
        "name": user["name"],
        "profession": user["profession"],
        "profile_pic": user["profile_pic"]
    }
# ==========================================
# Endpoints: Document Process
# ==========================================
UPLOAD_DIR = "uploaded_pdfs"
os.makedirs(UPLOAD_DIR, exist_ok=True)
global_active_filenames = set()

def get_user_upload_dir(user_email: str):
    user_dir = os.path.join(UPLOAD_DIR, user_email)
    os.makedirs(user_dir, exist_ok=True)
    return user_dir

def get_chroma_client():
    global chroma_client
    if chroma_client is None:
        db_dir = os.path.join(os.getcwd(), "chroma_db")
        os.makedirs(db_dir, exist_ok=True)
        chroma_client = chromadb.PersistentClient(path=db_dir)
    return chroma_client

def get_collection():
    client = get_chroma_client()
    return client.get_or_create_collection(
        name="dms_collection",
        metadata={"hnsw:space": "cosine"}
    )

def index_document(file_path: str, filename: str, user_email: str):
    """
    Index a single document with user metadata.
    """
    try:
        loader = PyPDFLoader(file_path)
        documents = loader.load()
        
        for doc in documents:
            doc.metadata["source"] = filename
            doc.metadata["owner_email"] = user_email
            doc.metadata["active"] = True

        text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=100)
        chunks = text_splitter.split_documents(documents)
        
        # Generate deterministic IDs: user_filename_index
        ids = [f"{user_email}_{filename}_{i}" for i in range(len(chunks))]

        vector_store = Chroma(
            client=get_chroma_client(),
            collection_name="dms_collection",
            embedding_function=global_embeddings
        )
        
        # Upsert: overwrite if IDs already exist
        vector_store.add_documents(chunks, ids=ids)
        
        return len(documents), len(chunks)
    except Exception as e:
        print(f"Error indexing {filename}: {e}")
        return 0, 0

def delete_user_document_from_index(filename: str, user_email: str):
    """
    Delete a document's chunks from Chroma for a specific user.
    """
    vector_store = Chroma(
        client=get_chroma_client(),
        collection_name="dms_collection",
        embedding_function=global_embeddings
    )
    # Using metadata filter to delete
    # Note: Chroma's langchain wrapper doesn't provide a direct 'delete by metadata' easily in older versions
    # but we can use the underlying collection.
    collection = get_collection()
    collection.delete(where={"$and": [{"source": filename}, {"owner_email": user_email}]})


@app.post("/api/upload")
async def upload_policy(user_email: str, file: UploadFile = File(...)):
    try:
        # Save locally temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        # Upload to S3
        s3_key = f"{user_email}/{file.filename}"
        s3_client.upload_file(tmp_path, S3_BUCKET_NAME, s3_key)

        # Trigger Glue Crawler to update metadata catalog
        try:
            glue.start_crawler(Name=GLUE_CRAWLER_NAME)
        except glue.exceptions.CrawlerRunningException:
            pass # Already running
        except Exception as ge:
            print(f"Glue Crawler Error: {ge}")

        # Index into ChromaDB for Semantic Search
        num_docs, num_chunks = index_document(tmp_path, file.filename, user_email)

        # Clean up temp file
        os.unlink(tmp_path)

        return {
            "message": "Document Uploaded to S3 & Glue Crawler Triggered",
            "filename": file.filename,
            "s3_key": s3_key
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/policies")
async def list_policies(email: str):
    try:
        # List from S3
        prefix = f"{email}/"
        response = s3_client.list_objects_v2(Bucket=S3_BUCKET_NAME, Prefix=prefix)
        
        policies = []
        if 'Contents' in response:
            for obj in response['Contents']:
                filename = obj['Key'].split('/')[-1]
                if filename:
                    policies.append({
                        "filename": filename,
                        "active": True
                    })
        return {"policies": policies}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/policies/{filename}/activate")
async def activate_policy(filename: str, email: str):
    # Already active by default in this version
    return {"message": "Policy active", "filename": filename}

@app.post("/api/policies/{filename}/deactivate")
async def deactivate_policy(filename: str, email: str):
    # Simplified: deletion is the primary deactivation
    return {"message": "Policy deactivation not implemented in this flow", "filename": filename}

@app.delete("/api/policies/{filename}")
async def delete_policy(filename: str, email: str):
    try:
        s3_key = f"{email}/{filename}"
        s3_client.delete_object(Bucket=S3_BUCKET_NAME, Key=s3_key)
        
        delete_user_document_from_index(filename, email)
        return {"message": "Document deleted from S3 and index successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/policies/{filename}/download")
async def download_policy(filename: str, email: str):
    try:
        s3_key = f"{email}/{filename}"
        # Generate presigned URL for download
        url = s3_client.generate_presigned_url('get_object',
                                            Params={'Bucket': S3_BUCKET_NAME,
                                                    'Key': s3_key},
                                            ExpiresIn=3600)
        return JSONResponse(content={"url": url})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# Endpoints: Chat
# ==========================================
import uuid
@app.post("/api/chat")
async def chat(req: ChatRequest):
    """
    RAG using local ChromaDB and Groq API.
    """
    try:
        # Fetch vector store
        vector_store = Chroma(
            client=get_chroma_client(),
            collection_name="dms_collection",
            embedding_function=global_embeddings
        )
        
        # Use similarity_search_with_score to get distances
        docs_and_scores = vector_store.similarity_search_with_score(
            req.question,
            k=req.retrieval_depth,
            filter={"owner_email": req.user_email}
        )
        
        docs = [doc for doc, score in docs_and_scores]
        
        if docs_and_scores:
            # We use the minimum distance (best match)
            distances = [score for doc, score in docs_and_scores]
            distance_val = round(min(distances), 3)
            # For cosine distance, similarity is roughly 1 - distance. Convert to percentage.
            confidence_val = max(0.0, min(100.0, round((1.0 - distance_val) * 100, 2)))
            chunks_list = [doc.page_content for doc in docs]
        else:
            distance_val = 0.0
            confidence_val = 0.0
            chunks_list = []
            
        # Extract sources from documents
        sources = set([doc.metadata.get("source", "Unknown") for doc in docs])
        source_list_str = ", ".join(list(sources))
        
        context = "\n\n".join([doc.page_content for doc in docs])
        
        llm = ChatGroq(
            temperature=0, 
            groq_api_key=req.groq_api_key, 
            model_name="llama-3.1-8b-instant"
        )
        
        system_prompt = (
            "You are a helpful HR and Document assistant. Use the following related documents "
            "to answer the question. If you don't know the answer, just say you don't know. "
            "Context: {context}"
        )
        
        prompt = PromptTemplate.from_template(system_prompt + "\n\nQuestion: {question}")
        formatted_prompt = prompt.format(context=context, question=req.question)
        
        response = llm.invoke(formatted_prompt)
        answer_text = response.content
        
        status = "Answered"
        if not docs:
            answer_text = "I couldn't find any relevant information in your uploaded documents."
            status = "No Context"
            
        conn = get_db()
        cursor = conn.cursor()
        conv_id = req.conversation_id or str(uuid.uuid4())
        
        cursor.execute('''
            INSERT INTO chat_history (timestamp, user_email, question, answer, status, confidence, distance, depth, chunks, topic, conversation_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (datetime.datetime.now().isoformat(), req.user_email, 
              req.question, answer_text, status, confidence_val, distance_val, req.retrieval_depth, json.dumps(chunks_list), "Others", conv_id))
        chat_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return {
            "id": chat_id,
            "conversation_id": conv_id,
            "answer": answer_text,
            "status": status,
            "confidence": confidence_val,
            "distance": distance_val,
            "chunks": chunks_list,
            "source_list": source_list_str
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/summarize")
async def summarize_document(req: SummarizeRequest):
    """
    Generate a summary for a specific document using Groq.
    """
    try:
        # We fetch the document content from S3
        s3_key = f"{req.user_email}/{req.filename}"
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp_path = tmp.name
            
        try:
            s3_client.download_file(S3_BUCKET_NAME, s3_key, tmp_path)
            loader = PyPDFLoader(tmp_path)
            documents = loader.load()
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        
        # Combine text from up to first 10 pages for summary
        text = "\n".join([doc.page_content for doc in documents[:10]])
        
        # Summarization Call using Groq
        prompt = f"Provide a concise, high-level summary of the following document content. Focus on the main purpose and key points. Respond in plain text.\n\nDocument Content:\n{text}\n\nSummary:"
        
        llm = ChatGroq(
            temperature=0, 
            groq_api_key=req.groq_api_key, 
            model_name="llama-3.1-8b-instant"
        )
        
        response = llm.invoke(prompt)
        summary_text = response.content.strip()
        
        return {"summary": summary_text}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating summary: {str(e)}")

@app.get("/api/chat/history")
async def get_history(email: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM chat_history WHERE user_email=? ORDER BY id ASC", (email,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.delete("/api/chat/history/all")
async def clear_chat_history(email: str):
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM chat_history WHERE user_email=?", (email,))
        conn.commit()
        conn.close()
        return {"message": "Chat history cleared successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/chat/history/{chat_id}")
async def delete_chat_message(chat_id: int, email: str):
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM chat_history WHERE id=? AND user_email=?", (chat_id, email))
        conn.commit()
        conn.close()
        return {"message": "Message deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# Endpoints: Insights
# ==========================================
@app.get("/api/insights")
async def get_insights(email: str):
    conn = get_db()
    cursor = conn.cursor()
    
    # KPIs
    cursor.execute("SELECT COUNT(*) FROM chat_history WHERE user_email=?", (email,))
    total = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM chat_history WHERE status='Answered' AND user_email=?", (email,))
    ans = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT AVG(confidence) FROM chat_history WHERE status='Answered' AND user_email=?", (email,))
    avg_conf_row = cursor.fetchone()
    avg_conf = avg_conf_row[0] if avg_conf_row and avg_conf_row[0] is not None else 0.0
    
    # Daily Activity (Last 14 days)
    daily_activity = []
    for i in range(13, -1, -1):
        date = (datetime.datetime.now() - datetime.timedelta(days=i)).strftime('%Y-%m-%d')
        cursor.execute("SELECT COUNT(*) FROM chat_history WHERE user_email=? AND timestamp LIKE ?", (email, f"{date}%"))
        count = cursor.fetchone()[0] or 0
        daily_activity.append({"date": date, "count": count})

    # Confidence Distribution
    conf_dist = {"0-20": 0, "20-40": 0, "40-60": 0, "60-80": 0, "80-100": 0}
    cursor.execute("SELECT confidence FROM chat_history WHERE status='Answered' AND user_email=?", (email,))
    for row in cursor.fetchall():
        c = row['confidence']
        if c <= 20: conf_dist["0-20"] += 1
        elif c <= 40: conf_dist["20-40"] += 1
        elif c <= 60: conf_dist["40-60"] += 1
        elif c <= 80: conf_dist["60-80"] += 1
        else: conf_dist["80-100"] += 1

    # Topics
    cursor.execute("SELECT topic, COUNT(*) as count FROM chat_history WHERE user_email=? GROUP BY topic", (email,))
    topics_data = [{"topic": r['topic'], "count": r['count']} for r in cursor.fetchall()]
    
    # Recent Unanswered
    cursor.execute("SELECT question FROM chat_history WHERE status='Not Answered' AND user_email=? ORDER BY id DESC LIMIT 5", (email,))
    recent_unanswered = [r["question"] for r in cursor.fetchall()]
    
    conn.close()
    
    return {
        "total": total,
        "answered": ans,
        "not_answered": total - ans,
        "average_confidence": avg_conf,
        "coverage_percentage": (ans / total * 100) if total > 0 else 0.0,
        "daily_activity": daily_activity,
        "confidence_distribution": conf_dist,
        "topics": topics_data,
        "recent_unanswered": recent_unanswered
    }

# ==========================================
# Endpoints: Leave Calculator (Add-On Feature)
# ==========================================
@app.get("/api/extract-leave-policies")
async def extract_leave_policies():
    """
    Extract leave entitlement rules from the uploaded HR Leave Policy PDF.
    Uses RAG to dynamically retrieve policy information.
    """
    global global_vector_store
    
    # Default fallback policies
    DEFAULT_POLICIES = {
        'annual_lt_1': 12,
        'annual_1_5': 18,
        'annual_gt_5': 24,
        'sick': 10,
        'maternity': 180
    }

    if global_vector_store is None:
        return DEFAULT_POLICIES

    try:
        # Query the vector store for leave-related policies
        leave_queries = {
            'annual': "annual leave entitlement years of service",
            'sick': "sick leave days per year",
            'maternity': "maternity leave duration"
        }
        
        extracted_policies = {}
        
        # Initialize LLM for policy extraction
        llm = ChatGroq(
            temperature=0,
            groq_api_key=os.getenv("GROQ_API_KEY"),
            model_name="llama-3.1-8b-instant"
        )

        for leave_category, query in leave_queries.items():
            results = global_vector_store.similarity_search(query, k=3)
            if results:
                context = "\n".join([doc.page_content for doc in results])
                
                extraction_prompt = PromptTemplate(
                    template="""Extract the numerical leave entitlements from the following policy text.
Return values ONLY as JSON with the following structure:
If annual leave: {{"lt_1": number, "1_5": number, "gt_5": number}}
If sick or maternity: {{"days": number}}

If the information is not explicitly found, return null for those values.
Do not include any explanation, only valid JSON.

Policy Text:
{context}

For the category: {leave_category}

Response (JSON only):""",
                    input_variables=["context", "leave_category"]
                )
                
                chain = extraction_prompt | llm
                response = chain.invoke({"context": context, "leave_category": leave_category})
                
                try:
                    response_text = response.content.strip()
                    if response_text.startswith('```'):
                        response_text = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response_text).group(1)
                    
                    parsed = json.loads(response_text)
                    if leave_category == 'annual':
                        if parsed.get('lt_1'): extracted_policies['annual_lt_1'] = parsed['lt_1']
                        if parsed.get('1_5'): extracted_policies['annual_1_5'] = parsed['1_5']
                        if parsed.get('gt_5'): extracted_policies['annual_gt_5'] = parsed['gt_5']
                    else:
                        if parsed.get('days'): extracted_policies[leave_category] = parsed['days']
                except:
                    continue
        
        # Merge with defaults
        final_policies = {**DEFAULT_POLICIES, **extracted_policies}
        return final_policies

    except Exception as e:
        # Silently fail to defaults if something goes wrong during extraction
        print(f"Extraction error: {e}")
        return DEFAULT_POLICIES


class LeaveCalculationRequest(BaseModel):
    years_of_service: float
    leave_type: str  # 'annual', 'sick', 'maternity'
    leave_taken: float


@app.post("/api/calculate-leave")
async def calculate_leave(req: LeaveCalculationRequest):
    """
    Calculate leave entitlement based on years of service and leave type.
    Uses dynamically extracted policies from the PDF.
    """
    try:
        # Get policies (either dynamic or default)
        policies = await extract_leave_policies()
        
        entitlement = 0
        if req.leave_type == 'annual':
            if req.years_of_service < 1:
                entitlement = policies['annual_lt_1']
            elif req.years_of_service <= 5:
                entitlement = policies['annual_1_5']
            else:
                entitlement = policies['annual_gt_5']
        elif req.leave_type == 'sick':
            entitlement = policies['sick']
        elif req.leave_type == 'maternity':
            entitlement = policies['maternity']
        else:
            raise HTTPException(status_code=400, detail="Invalid leave type")
        
        leave_taken = max(0, req.leave_taken)
        remaining = max(0, entitlement - leave_taken)
        
        return {
            "total_entitlement": entitlement,
            "leave_taken": leave_taken,
            "remaining_leave": remaining,
            "leave_type": req.leave_type,
            "years_of_service": req.years_of_service,
            "percentage_used": round((leave_taken / entitlement * 100) if entitlement > 0 else 0, 2),
            "policies_used": policies # Send back for UI info
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error calculating leave: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
