from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
from pathlib import Path
from app.db.session import get_db
from app.repositories.inbox_repository import InboxRepository
from app.services.email_service import EmailService
from app.models.enums import DocumentType, ProcessingStatus
from app.services.ai_service import ai_service


import logging
from email.utils import parsedate_to_datetime

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/emails", tags=["Emails"])


# ==========================================
# Pydantic Schemas
# ==========================================
class DocumentSummaryResponse(BaseModel):
    id: int
    filename: str
    document_type: str
    processing_status: str
    file_path: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EmailResponse(BaseModel):
    id: int
    message_id: Optional[str] = None
    sender: str
    subject: Optional[str] = None
    received_date: Optional[datetime] = None
    body: Optional[str] = None
    processing_status: str
    created_at: datetime
    documents: List[DocumentSummaryResponse] = []

    model_config = ConfigDict(from_attributes=True)


class SyncResponse(BaseModel):
    success: bool
    message: Optional[str] = None
    synced_count: Optional[int] = 0
    skipped_count: Optional[int] = 0
    ingested_count: Optional[int] = 0
    error: Optional[str] = None


# ==========================================
# Endpoints
# ==========================================
@router.post("/sync", response_model=SyncResponse)
def sync_emails(
    use_mock: bool = Query(
        False,
        description="If True, generates synthetic healthcare test emails instead of connecting to a live IMAP server."
    ),
    max_emails: int = Query(20, ge=1, le=100, description="Maximum emails to fetch from IMAP mailbox."),
    db: Session = Depends(get_db),
):
    """
    Synchronizes emails into the system.
    Connects to IMAP mailbox or runs synthetic generation if use_mock=true.
    """
    if use_mock:
        result = EmailService.ingest_synthetic_test_emails(db)
        return SyncResponse(
            success=result["success"],
            message=result["message"],
            ingested_count=result.get("ingested_count", 0),
            skipped_count=result.get("skipped_count", 0),
        )

    result = EmailService.sync_from_imap(db, max_emails=max_emails)
    return SyncResponse(
        success=result["success"],
        message=result.get("message", "IMAP synchronization complete."),
        synced_count=result.get("synced_count", 0),
        skipped_count=result.get("skipped_count", 0),
        error=result.get("error"),
    )


@router.post("/mock-ingest", response_model=SyncResponse)
def ingest_mock_emails(db: Session = Depends(get_db)):
    """
    Generates realistic synthetic healthcare emails (ICSR, PQC, MI, Spam) with attachments.
    Allows testing full workflow without requiring an active IMAP mailbox.
    """
    result = EmailService.ingest_synthetic_test_emails(db)
    return SyncResponse(
        success=result["success"],
        message=result["message"],
        ingested_count=result.get("ingested_count", 0),
        skipped_count=result.get("skipped_count", 0),
    )
@router.post("/import-test-data", response_model=SyncResponse)
def import_test_data(db: Session = Depends(get_db)):
    """Import synthetic email files from the test data directory.

    The function scans the directory defined by the ``TEST_EMAIL_DIR`` environment
    variable (defaults to ``E:/Smart Inbox Assistant/test_data/emails``). It parses
    synthetic email files, creates Email and Document records in the database,
    classifies each document, and prevents duplicate imports.
    """
    import os
    test_emails_dir = Path(os.getenv("TEST_EMAIL_DIR", "E:/Smart Inbox Assistant/test_data/emails"))
    if not test_emails_dir.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Test email directory not found: {test_emails_dir}",
        )

    ingested = 0
    skipped = 0
    for file_path in sorted(test_emails_dir.iterdir()):
        if not file_path.is_file():
            continue
        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                content = file_path.read_text(encoding="utf-16")
            except Exception:
                content = file_path.read_text(encoding="latin-1", errors="replace")
        except Exception as e:
            logger.error(f"Failed to read test email {file_path}: {e}")
            continue

        lines = content.splitlines()
        subject = ""
        sender = ""
        date_str = ""
        body_lines: List[str] = []
        header_done = False
        for line in lines:
            if not header_done and ":" in line:
                key, val = line.split(":", 1)
                key = key.strip().lower()
                val = val.strip()
                if key == "subject":
                    subject = val
                elif key == "from":
                    sender = val
                elif key == "date":
                    date_str = val
            else:
                header_done = True
                body_lines.append(line)
        body = "\n".join(body_lines).strip()
        try:
            if date_str:
                received_date = datetime.fromisoformat(date_str)
            else:
                received_date = datetime.utcnow()
        except Exception:
            received_date = datetime.utcnow()

        email_record, is_new, _ = EmailService.ingest_single_email(
            db=db,
            sender=sender or "unknown@example.com",
            subject=subject or "(No Subject)",
            received_date=received_date,
            body=body,
        )

        if not email_record:
            continue

        # Prevent duplicate document records for the same email
        existing_docs = InboxRepository.list_documents_by_email(db, email_record.id)
        if existing_docs:
            skipped += 1
            continue

        # Create Document record so GET /api/documents returns it
        doc = InboxRepository.create_document(
            db=db,
            email_id=email_record.id,
            filename=file_path.name,
            file_path=str(file_path),
            document_type=DocumentType.EMAIL_BODY,
            extracted_text=body,
            status=ProcessingStatus.PENDING,
        )

        # Run classification and fact extraction using existing AI service
        try:
            email_text = f"Subject: {subject}\n\n{body}"
            ai_service.classify_and_store(
                db=db,
                email_id=email_record.id,
                document_id=doc.id,
                email_text=email_text,
                extracted_text=body,
            )
            ai_service.extract_and_store(
                db=db,
                document_id=doc.id,
            )
        except Exception as ai_err:
            logger.warning(f"AI processing failed for imported document {doc.id}: {ai_err}")

        ingested += 1

    return SyncResponse(
        success=True,
        message="Test data import completed.",
        ingested_count=ingested,
        skipped_count=skipped,
    )

@router.get("", response_model=List[EmailResponse])
def get_emails(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    status: Optional[str] = Query(None, description="Filter by processing status (PENDING, PROCESSING, COMPLETED, FAILED)"),
    db: Session = Depends(get_db),
):
    """Lists ingested emails ordered by newest first."""
    emails = InboxRepository.list_emails(db, skip=skip, limit=limit, status=status)
    return emails


@router.get("/{email_id}", response_model=EmailResponse)
def get_email_details(
    email_id: int,
    db: Session = Depends(get_db),
):
    """Retrieves single email with its attached documents."""
    email_record = InboxRepository.get_email_by_id(db, email_id)
    if not email_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Email with ID {email_id} not found."
        )
    return email_record
