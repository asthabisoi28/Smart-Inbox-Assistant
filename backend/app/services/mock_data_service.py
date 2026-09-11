# Mock data service for document endpoints
# Returns a static list of document dicts suitable for Pydantic serialization.

from datetime import datetime
from typing import List

# Sample mock documents (synthetic, no real patient data)
MOCK_DOCUMENTS = [
    {
        "id": 1,
        "email_id": None,
        "filename": "example1.pdf",
        "file_path": "/mock/path/example1.pdf",
        "document_type": "pdf_digital",
        "processing_status": "COMPLETED",
        "language": "en",
        "ocr_confidence": 0.98,
        "processing_time": 1.2,
        "primary_category": "ICSR",
        "confidence": 0.95,
        "subject": "Adverse Event Report",
        "sender": "doctor@example.com",
        "received_date": datetime.now(),
        "review_status": "PENDING_REVIEW",
        "classifications_count": 1,
        "facts_count": 2,
        "created_at": datetime.now(),
    },
    {
        "id": 2,
        "email_id": None,
        "filename": "example2.pdf",
        "file_path": "/mock/path/example2.pdf",
        "document_type": "pdf_scanned",
        "processing_status": "COMPLETED",
        "language": "en",
        "ocr_confidence": 0.88,
        "processing_time": 2.0,
        "primary_category": "PQC",
        "confidence": 0.90,
        "subject": "Product Quality Complaint",
        "sender": "quality@example.com",
        "received_date": datetime.now(),
        "review_status": "PENDING_REVIEW",
        "classifications_count": 1,
        "facts_count": 3,
        "created_at": datetime.now(),
    },
]


def get_all_documents() -> List[dict]:
    """Return the list of mock documents."""
    return MOCK_DOCUMENTS


def get_document_by_id(doc_id: int) -> dict | None:
    """Return a single document dict or None if not found."""
    return next((d for d in MOCK_DOCUMENTS if d["id"] == doc_id), None)
