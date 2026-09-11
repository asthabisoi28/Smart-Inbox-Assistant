# Smart Inbox Assistant — Architecture Documentation

This document provides a detailed architectural breakdown of the **Smart Inbox Assistant for Healthcare**, detailing component responsibilities, data flow, AI extraction flow, database layer, and human-in-the-loop review workflow.

---

## 1. System Architecture Diagram

```text
                               ┌──────────────────────────────────────────────┐
                               │           Angular Triage Dashboard           │
                               │  (Document Queue, Split Viewer, Fact Edit)   │
                               └──────────────────────┬───────────────────────┘
                                                      │ HTTP REST (JSON)
                                                      ▼
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                         FastAPI Backend Service                                        │
├─────────────────────┬───────────────────────┬──────────────────────────┬───────────────────────────────┤
│    Email Ingestion  │   Document Pipeline   │     AI Engine (Gemini)   │     Reviewer API Endpoints    │
│    (IMAP / Fixtures)│   (PyMuPDF / OCR)     │   (Structured Output)    │   (Accept / Override / Audit) │
└──────────┬──────────┴───────────┬───────────┴────────────┬─────────────┴──────────────┬────────────────┘
           │                      │                        │                            │
           ▼                      ▼                        ▼                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                              Database Layer (SQLAlchemy ORM)                                          │
│         [Email] <─── [Document] <─── [Classification] <─── [ExtractedFact] <─── [AuditLog]              │
│                           Supports Oracle 19c/21c & SQLite Development                                 │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Component Responsibilities

| Component | Technology | Primary Responsibilities |
|---|---|---|
| **Angular Frontend** | Angular 18 (Standalone Components, RxJS) | Displays document triage queue, side-by-side original text vs. AI extraction, missing field highlights, manual override controls, and audit log history. |
| **FastAPI Backend Router** | FastAPI, Pydantic v2 | Exposes REST endpoints for health checks, email ingestion, document processing, AI classification, reviewer overrides, and audit trails. |
| **PDF & Layout Processing** | PyMuPDF (`fitz`), Tesseract OCR, `langdetect` | Extracts digital PDF text, detects scanned/handwritten pages for OCR, isolates multi-column academic journal layouts, extracts structured tables, and preserves original languages. |
| **AI Classification & Extraction** | Google Gemini API (fallback to heuristic rules) | Classifies documents into ICSR (Adverse Event), PQC (Quality Complaint), MI (Info Request), or NOT_RELEVANT, extracts structured entity facts with confidence scores, and identifies missing mandatory fields. |
| **Data Persistence & Audit** | SQLAlchemy 2.0 (`oracledb` / SQLite) | Persists emails, documents, classification results, extracted facts, reviewer decisions (`ACCEPT`/`OVERRIDE`), and event audit logs. |

---

## 3. Data Flow

```mermaid
sequenceDiagram
    autonumber
    participant Email as Email / Storage
    participant Backend as FastAPI Backend
    participant Engine as PDF & OCR Engine
    participant AI as Gemini AI Service
    participant DB as Oracle / SQLite DB
    participant UI as Angular Dashboard

    Email->>Backend: Ingest Email (.eml) & PDF Attachments
    Backend->>DB: Store Email & Document metadata (Status: PENDING)
    Backend->>Engine: Run PdfProcessingService.process_pdf_document()
    Engine->>Engine: Detect layout (Digital / Scanned / Article / Language)
    Engine->>DB: Save extracted text, tables, images (Status: COMPLETED)
    Backend->>AI: Send combined email + document text to classify & extract
    AI->>Backend: Return structured JSON (Category, Confidence, Facts, Missing Fields)
    Backend->>DB: Save Classifications, ExtractedFacts, and AuditLog
    UI->>Backend: GET /api/documents (Fetch triage queue)
    Backend-->>UI: Return document list with category & review status
    UI->>Backend: POST /api/documents/{id}/review/accept OR /override
    Backend->>DB: Update ReviewAction & write AuditLog entry
```

---

## 4. AI Classification & Extraction Flow

```text
Incoming Document Text
        │
        ▼
Is GEMINI_API_KEY Configured?
        ├───────── YES ─────────► Google Gemini API (Structured JSON Schema)
        │                             │
        │                             ▼
        │                         Valid Pydantic Output?
        │                             ├────── YES ─────► Final Result
        │                             └────── NO  ─────┐
        ▼                                              ▼
Clinical Heuristic Fallback Engine ◄────────────────────┘
  - Rule-based keyword matching (Multilingual: EN, ES, FR)
  - Default confidence scoring (80% - 85%)
  - Safe fallback: missing fields default to "Not stated" (0.0 confidence)
```

---

## 5. Database Schema & Flow

### Entity Relationships

- **`Email`** (1) ──── (N) **`Document`**
- **`Document`** (1) ──── (N) **`Classification`**
- **`Document`** (1) ──── (N) **`ExtractedFact`**
- **`Document`** (1) ──── (N) **`ReviewAction`**
- **`Document`** (1) ──── (N) **`AuditLog`**

### Database Portability

- **Development/Test**: SQLite (`smart_inbox.db`) with `check_same_thread=False`.
- **Production**: Oracle DB 19c/21c via `oracledb` thin/thick driver using `oracle+oracledb://user:pass@host:1521/?service_name=ORCLPDB1`.

---

## 6. Human-in-the-Loop Review Flow

1. **Queue Inspection**: Triage reviewer views list of incoming processed documents.
2. **Side-by-Side Review**: Reviewer compares raw document text against AI-extracted entity fields and highlighted missing mandatory fields.
3. **Accept**: Reviewer accepts AI findings (`POST /api/documents/{id}/review/accept`).
4. **Override**: Reviewer modifies category or updates/adds specific fact fields (`POST /api/documents/{id}/review/override` / `PUT /api/documents/{id}/facts`).
5. **Audit Logging**: Every action automatically records timestamp, reviewer username, previous state, new state, and review comments in `audit_logs`.
