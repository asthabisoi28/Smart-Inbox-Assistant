import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.enums import (
    ClassificationCategory,
    ProcessingStatus,
    DocumentType,
    ReviewActionType,
    FactSourceType,
)
from app.models.email import Email
from app.models.document import Document
from app.models.classification import Classification
from app.models.extracted_fact import ExtractedFact
from app.models.review_action import ReviewAction
from app.models.audit_log import AuditLog
from app.repositories.inbox_repository import InboxRepository


def test_email_lifecycle(db):
    # 1. Create Email
    email = InboxRepository.create_email(
        db=db,
        sender="physician@clinic.org",
        subject="Adverse Event Report: Rash following Treatment",
        body="Patient experienced severe allergic rash after taking Medication-X batch #89421.",
        received_date=datetime(2026, 9, 1, 10, 30, 0),
        status=ProcessingStatus.PENDING,
    )
    assert email.id is not None
    assert email.sender == "physician@clinic.org"
    assert email.processing_status == "PENDING"

    # 2. Retrieve Email
    fetched = InboxRepository.get_email_by_id(db, email.id)
    assert fetched is not None
    assert fetched.subject == "Adverse Event Report: Rash following Treatment"

    # 3. Update Status
    updated = InboxRepository.update_email_status(db, email.id, ProcessingStatus.COMPLETED)
    assert updated.processing_status == "COMPLETED"


def test_document_and_extracted_facts(db):
    # Create Parent Email
    email = InboxRepository.create_email(
        db=db,
        sender="quality-ctrl@hospital.org",
        subject="Defective Syringe Batch Notice",
    )

    # Create Attachment Document
    document = InboxRepository.create_document(
        db=db,
        email_id=email.id,
        filename="complaint_form_batch77.pdf",
        document_type=DocumentType.PDF_DIGITAL,
        extracted_text="Product Quality Complaint: Cracked barrel on Syringe-10mL Lot #B7712.",
        language="en",
        status=ProcessingStatus.COMPLETED,
        processing_time=1.45,
    )
    assert document.id is not None
    assert document.email_id == email.id
    assert document.processing_time == 1.45

    # Add Extracted Facts
    fact_product = InboxRepository.add_extracted_fact(
        db=db,
        document_id=document.id,
        category=ClassificationCategory.PQC,
        field_name="product",
        field_value="Syringe-10mL",
        confidence=0.98,
        source_type=FactSourceType.PDF_TEXT,
        source_reference="Page 1, Paragraph 1",
    )
    assert fact_product.field_value == "Syringe-10mL"

    # Add Extracted Fact with missing data (must default to 'Not stated')
    fact_missing = InboxRepository.add_extracted_fact(
        db=db,
        document_id=document.id,
        category=ClassificationCategory.PQC,
        field_name="patient_age",
        field_value="Not stated",
        confidence=1.0,
        source_type=FactSourceType.PDF_TEXT,
        source_reference="Page 1",
    )
    assert fact_missing.field_value == "Not stated"

    # Query Facts
    facts = InboxRepository.get_facts_by_document(db, document.id)
    assert len(facts) == 2


def test_classification_and_audit_logging(db):
    email = InboxRepository.create_email(
        db=db,
        sender="patient-inquiry@mail.com",
        subject="Dosage guidelines inquiry for Tablet-Y",
    )

    # Add Classification (Medical Information Request)
    classification = InboxRepository.add_classification(
        db=db,
        email_id=email.id,
        category=ClassificationCategory.MI,
        confidence=0.96,
        reason="Sender is requesting standard dosage instructions for approved product.",
    )
    assert classification.id is not None
    assert classification.category == "MI"
    assert classification.confidence == 0.96

    # Record Audit Log
    log = InboxRepository.log_event(
        db=db,
        email_id=email.id,
        event="AI_CLASSIFICATION_COMPLETED",
        details="Gemini Flash classified as MI with 96% confidence.",
    )
    assert log.id is not None
    assert log.event == "AI_CLASSIFICATION_COMPLETED"

    # Record Reviewer Action (Accept or Override)
    review = InboxRepository.record_review_action(
        db=db,
        email_id=email.id,
        reviewer="safety_officer_sarah",
        action=ReviewActionType.ACCEPT,
        comments="Confirmed medical inquiry; routing to Medical Affairs.",
    )
    assert review.id is not None
    assert review.action == "ACCEPT"
    assert review.reviewer == "safety_officer_sarah"
