# Smart Inbox Assistant for Healthcare

An intelligent, AI-powered document triage, extraction, and human-in-the-loop review platform designed for healthcare companies to process incoming medical emails, adverse event individual case safety reports (ICSR), product quality complaints (PQC), and medical information requests (MI).

---

## 1. Project Overview

Healthcare safety and regulatory teams receive thousands of incoming emails and attached PDFs daily containing critical clinical safety events, quality defects, and medical questions. **Smart Inbox Assistant** automates the end-to-end processing pipeline:
- **Email & PDF Ingestion**: Captures incoming emails and PDF attachments.
- **Layout-Aware PDF Extraction & OCR**: Extracts digital text, handles scanned/handwritten pages via OCR, preserves multi-column academic journal layouts, and retains non-English text.
- **AI Classification & Fact Extraction**: Categorizes content into **ICSR**, **PQC**, **MI**, or **NOT_RELEVANT** using Google Gemini API (with a deterministic heuristic fallback), extracting structured clinical entity facts.
- **Missing Field Detection**: Flags missing mandatory regulatory items (e.g., patient ID, lot number, reporter details) with zero-confidence markers.
- **Human-in-the-Loop Review Dashboard**: An Angular triage interface allowing safety experts to review, edit, accept, or override AI extractions.
- **Oracle DB Storage & Audit Trail**: Full enterprise persistence with immutable action logging for GxP/regulatory auditability.

---

## 2. Architecture

```text
                               ┌──────────────────────────────────────────────┐
                               │               Angular Dashboard              │
                               │        (Triage Queue, Split Viewer)          │
                               └──────────────────────┬───────────────────────┘
                                                      │ HTTP / REST API
                                                      ▼
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                         FastAPI Backend Service                                        │
├─────────────────────┬───────────────────────┬──────────────────────────┬───────────────────────────────┤
│    Email Ingest     │   PDF / OCR Engine    │      AI Engine           │       Reviewer Router         │
│  (IMAP / Fixtures)  │  (PyMuPDF / Tesseract)│  (Gemini API + Fallback) │   (Accept / Override / Audit) │
└──────────┬──────────┴───────────┬───────────┴────────────┬─────────────┴──────────────┬────────────────┘
           │                      │                        │                            │
           ▼                      ▼                        ▼                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                              Database Layer (SQLAlchemy ORM)                                          │
│                    Supports Oracle 19c/21c (Production) & SQLite (Local Dev)                           │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Tech Stack

- **Frontend**: Angular 18 (Standalone Components, RxJS, TypeScript, Vanilla CSS)
- **Backend**: Python 3.10+, FastAPI, Pydantic v2, SQLAlchemy 2.0
- **Database**: Oracle Database 19c/21c via `oracledb` (or local SQLite fallback)
- **AI / LLM**: Google Gemini API (`google-genai` SDK v2) + Multilingual Rule Classifier
- **PDF & Document Extraction**: PyMuPDF (`fitz`), `pdfplumber`, Tesseract OCR (`pytesseract`), `Pillow`, `langdetect`
- **Testing Framework**: `pytest`, `httpx`, `TestClient`

---

## 4. Folder Structure

```text
Smart Inbox Assistant/
├── ARCHITECTURE.md              # Detailed architecture & flow specification
├── README.md                    # Main project documentation
├── .env.example                 # Environment configuration template
├── smart_inbox.db               # SQLite database file (local dev)
├── backend/
│   ├── app/
│   │   ├── api/                 # FastAPI routes (health, emails, documents, ai)
│   │   ├── core/                # App config & environment settings
│   │   ├── db/                  # Database session, base models, & migrations
│   │   ├── models/              # SQLAlchemy database models
│   │   ├── repositories/        # Database access layer (InboxRepository)
│   │   ├── schemas/             # Pydantic request/response validation schemas
│   │   └── services/            # Core business logic (PDF, AI, Email, Synthetic)
│   ├── scripts/
│   │   └── process_batch.py     # Batch document benchmark script
│   ├── storage/
│   │   └── attachments/         # Storage for extracted PDF attachments
│   ├── tests/
│   │   ├── fixtures/            # Test PDFs, synthetic files & manifest
│   │   ├── test_ai.py           # AI classification & schema tests
│   │   ├── test_batch_processing.py  # Batch process script unit tests
│   │   ├── test_db.py           # Database CRUD & constraint tests
│   │   ├── test_email_parsing.py# Email MIME ingestion tests
│   │   ├── test_health.py       # Health check API tests
│   │   ├── test_integration.py  # End-to-end integration tests
│   │   ├── test_pdf_processing.py # PDF extraction & OCR tests
│   │   ├── test_reviewer_api.py # Accept/Override & audit log tests
│   │   └── test_synthetic_data.py # Synthetic dataset coverage & PII tests
│   └── requirements.txt         # Backend Python dependencies
└── frontend/
    ├── src/
    │   ├── app/
    │   │   ├── components/      # Document queue & review dashboard components
    │   │   ├── models/          # TypeScript interface models
    │   │   └── services/        # Angular HTTP document service
    │   ├── index.html           # Main HTML shell
    │   └── main.ts              # Angular entry point
    ├── angular.json             # Angular CLI configuration
    └── package.json             # Frontend Node.js dependencies
```

---

## 5. Installation

### Prerequisites
- **Python**: Version 3.10 or higher
- **Node.js**: Version 20 or higher & `npm`
- **Tesseract OCR** (Optional, for scanned image PDF OCR support)

### Installation Steps

1. **Clone the Repository**:
   ```bash
   git clone <repository-url>
   cd "Smart Inbox Assistant"
   ```

2. **Backend Virtual Environment Setup**:
   ```bash
   cd backend
   python -m venv venv
   # On Windows PowerShell:
   .\venv\Scripts\activate
   # On Linux/macOS:
   source venv/bin/activate

   pip install -r requirements.txt
   ```

3. **Frontend Dependencies Setup**:
   ```bash
   cd ../frontend
   npm install
   ```

---

## 6. Environment Variables

Copy `.env.example` to `.env` in the root directory or backend directory:
```bash
cp .env.example .env
```

| Variable | Default Value | Description |
|---|---|---|
| `APP_NAME` | `Smart Inbox Assistant` | Application display title |
| `APP_ENV` | `development` | Environment mode (`development` / `production`) |
| `APP_PORT` | `8000` | FastAPI server port |
| `APP_HOST` | `0.0.0.0` | Bind host address |
| `CORS_ORIGINS` | `http://localhost:4200` | Allowed CORS origins for Angular frontend |
| `GEMINI_API_KEY` | `""` | Google Gemini API Key |
| `GEMINI_MODEL` | `gemini-1.5-flash` | Gemini model name |
| `DATABASE_URL` | `sqlite:///./smart_inbox.db` | SQLAlchemy database URL |
| `ORACLE_USER` | `""` | Oracle DB username (optional individual param) |
| `ORACLE_PASSWORD` | `""` | Oracle DB password (optional individual param) |
| `ORACLE_HOST` | `localhost` | Oracle DB host address |
| `ORACLE_PORT` | `1521` | Oracle DB port |
| `ORACLE_SERVICE_NAME` | `ORCLPDB1` | Oracle DB service name |

---

## 7. Oracle Setup

To use an **Oracle Database** (e.g. Oracle 19c or 21c):

1. Set `DATABASE_URL` in `.env`:
   ```env
   DATABASE_URL=oracle+oracledb://app_user:your_password@localhost:1521/?service_name=ORCLPDB1
   ```
   *Alternatively, specify `ORACLE_USER`, `ORACLE_PASSWORD`, `ORACLE_HOST`, `ORACLE_PORT`, and `ORACLE_SERVICE_NAME` individually.*

2. Ensure `oracledb` Python driver is installed (included in `requirements.txt`).
3. Upon backend launch, `init_db()` automatically initializes all required tables and indexes using SQLAlchemy.

---

## 8. Gemini API Setup

1. Obtain an API key from [Google AI Studio](https://aistudio.google.com/).
2. Add your key to `.env`:
   ```env
   GEMINI_API_KEY=AIzaSyYourActualKeyHere
   GEMINI_MODEL=gemini-1.5-flash
   ```
3. *Note*: If `GEMINI_API_KEY` is not provided or offline, the system seamlessly uses its built-in rule-based heuristic classifier.

---

## 9. How to Run Backend

```bash
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
- **API URL**: `http://localhost:8000`
- **Interactive Swagger Docs**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

---

## 10. How to Run Frontend

```bash
cd frontend
npm start
```
- Open browser at `http://localhost:4200`.

---

## 11. How to Run Tests

Execute the complete `pytest` test suite:
```bash
cd backend
python -m pytest
```

Run specific test modules:
```bash
# Synthetic Data Coverage & PII Check
python -m pytest tests/test_synthetic_data.py

# End-to-End Integration Tests
python -m pytest tests/test_integration.py

# Reviewer Accept/Override API Tests
python -m pytest tests/test_reviewer_api.py
```

---

## 12. How to Process Synthetic Data

To generate synthetic test cases and process a batch of documents through extraction and classification:

```bash
cd backend
python scripts/process_batch.py --force
```

This generates 15 synthetic cases and displays a benchmark table:
```text
| #   | Document                                 | Time     | Classification | Confidence |
|-----|------------------------------------------|----------|----------------|------------|
| 1   | Quality_Complaint_PulmoMist_PM5049.pdf   | 1.29s    | PQC            | 83%        |
| 2   | Rapport_Pharmacovigilance_NeuroCalm_FR   | 0.25s    | ICSR           | 85%        |
| 3   | Informe_Caso_Clinico_CardioVax_ES.pdf    | 0.31s    | ICSR           | 85%        |
...
```

---

## 13. Example API Requests

### Health Check
```bash
curl -X GET http://localhost:8000/api/health
```

### List Processed Documents (Reviewer Queue)
```bash
curl -X GET "http://localhost:8000/api/documents?limit=10&status=COMPLETED"
```

### Accept AI Review Result
```bash
curl -X POST http://localhost:8000/api/documents/1/review/accept \
  -H "Content-Type: application/json" \
  -d '{
    "reviewer_username": "dr_smith",
    "comments": "Confirmed ICSR details match source PDF."
  }'
```

### Override AI Classification Result
```bash
curl -X POST http://localhost:8000/api/documents/1/review/override \
  -H "Content-Type: application/json" \
  -d '{
    "reviewer_username": "qa_lead",
    "override_category": "PQC",
    "comments": "Reclassified as PQC due to cracked syringe packaging.",
    "new_facts": [
      {
        "fact_key": "product_name",
        "fact_value": "HepaGuard 5000 IU",
        "confidence": 1.0,
        "source_reference": "Manual reviewer verification"
      }
    ]
  }'
```

---

## 14. Known Limitations

1. **OCR Dependency**: Scanned/handwritten PDF text quality depends on local system installation of Tesseract OCR binary. When Tesseract is missing, fallback text extraction is used.
2. **Gemini Rate Limits**: Direct Gemini API calls are subject to standard Google GenAI quota limits.
3. **IMAP Live Polling**: Current email ingestion supports synthetic file loading and on-demand IMAP sync; continuous real-time daemon polling requires background scheduler setup.

---

## 15. Production Improvement Roadmap

1. **Asynchronous Task Queue**: Integrate Celery / Redis / RabbitMQ for async background document processing and OCR rendering.
2. **Enterprise Authentication**: Add OAuth2 / OIDC Single Sign-On (SSO) and Role-Based Access Control (RBAC) for reviewer personas (Pharmacovigilance Lead, QA Officer, Medical Info Specialist).
3. **Vector Database / RAG**: Integrate Pgvector or Qdrant for semantic searching across historical medical inquiries and safety case archives.
4. **Active Learning Feedback Loop**: Store reviewer overrides to fine-tune future LLM prompts and classification accuracy.
