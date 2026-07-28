# DocuMind AI

DocuMind AI is a cloud-based HR document intelligence platform for enterprise policy search, Q&A, and document understanding. It helps employees and HR teams quickly find answers from policy PDFs using AI, with a modern web interface and AWS-backed document processing.

## 🌩️ Cloud-Based Architecture

This project is designed as a cloud-first solution and uses the following AWS services:

- Amazon S3 for storing uploaded policy documents
- AWS Glue for cataloging and preparing documents for discovery
- Amazon Bedrock for AI-powered document and knowledge workflows
- Python-based FastAPI and Streamlit frontend for the user experience

The application is structured so documents can be uploaded, indexed, and queried from cloud storage rather than relying only on local files.

## ✨ Features

- Secure user authentication and profile management
- Upload and manage HR policy documents
- AI-powered chat over uploaded documents
- Summarization and document Q&A
- Cloud storage integration with AWS S3
- Metadata cataloging with AWS Glue

## 🛠️ Tech Stack

- Python
- FastAPI
- Streamlit
- LangChain
- Chroma
- Hugging Face embeddings
- AWS S3, Glue, and Bedrock

## 📁 Project Structure

- app.py - Streamlit-based frontend experience
- server.py - FastAPI backend API
- setup_s3.py - Creates or validates the S3 document bucket
- setup_glue.py - Creates or validates the Glue database and crawler
- static/ - Frontend HTML/CSS/JS assets
- requirements.txt - Python dependencies

## 🚀 Getting Started

### 1. Prerequisites

- Python 3.10+
- AWS account with access keys configured
- Groq API key for LLM access

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Set the following variables before running the app:

```bash
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key
export AWS_DEFAULT_REGION=ap-south-1
export GROQ_API_KEY=your_groq_key
export BEDROCK_KB_ID=your_bedrock_kb_id
```

### 4. Set up cloud resources

Run the AWS setup scripts:

```bash
python setup_s3.py
python setup_glue.py
```

### 5. Run the application

Start the backend:

```bash
python server.py
```

Start the Streamlit UI:

```bash
streamlit run app.py
```

## ☁️ Cloud Deployment Notes

This project is intended to be deployed in a cloud environment with:

- AWS S3 for document storage
- AWS Glue for document cataloging
- Amazon Bedrock for inference workflows
- Optional deployment on EC2, ECS, or any container platform

For production deployment, store secrets in AWS Secrets Manager or environment configuration rather than hardcoding them.

## 🔐 Security Note

Do not commit real API keys or private AWS credentials to GitHub. Use environment variables or a secure secret store in production.

## 📌 License

This project is intended for educational and enterprise demo purposes.
