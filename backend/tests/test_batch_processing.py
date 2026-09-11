"""
Tests for the batch document processing script logic.

Tests the core functions from scripts/process_batch.py
without running the full script (which requires file I/O).
"""

import pytest
from datetime import datetime

from app.models.enums import ProcessingStatus, DocumentType, ClassificationCategory
from app.repositories.inbox_repository import InboxRepository
from app.services.ai_service import AIService
from app.services.synthetic_data_service import SyntheticDataService


class TestBatchProcessingLogic:
    """Test the batch processing pipeline components."""

    def test_synthetic_suite_produces_classifiable_documents(self, db):
        result = SyntheticDataService.generate_full_synthetic_suite(db)
        assert result["success"] is True
        docs = InboxRepository.list_documents(db, limit=50)
        assert len(docs) >= 12

        service = AIService(api_key="")
        classified = 0
        for doc in docs:
            if doc.extracted_text:
                continue
            classify_res, _ = service.classify(
                email_text="",
                extracted_text=f"Subject: test\n\n{doc.filename}",
            )
            assert classify_res.primary_category in [
                ClassificationCategory.ICSR,
                ClassificationCategory.PQC,
                ClassificationCategory.MI,
                ClassificationCategory.NOT_RELEVANT,
            ]
            classified += 1
        assert classified >= 10

    def test_classify_and_store_with_document_id(self, db):
        email = InboxRepository.create_email(
            db=db, sender="batch@synthetic.local", subject="Batch test",
            body="Patient experienced rash after Drug Alpha.",
        )
        doc = InboxRepository.create_document(
            db=db, email_id=email.id, filename="batch_test.pdf",
            extracted_text="Patient experienced rash after Drug Alpha.",
        )

        service = AIService(api_key="")
        result = service.classify_and_store(db, document_id=doc.id)
        assert result.success is True
        assert result.document_id == doc.id
        assert result.primary_category in [
            ClassificationCategory.ICSR,
            ClassificationCategory.PQC,
            ClassificationCategory.MI,
            ClassificationCategory.NOT_RELEVANT,
        ]
        assert result.classifications is not None
        assert len(result.classifications) >= 1

    def test_extract_and_store_with_document_id(self, db):
        email = InboxRepository.create_email(
            db=db, sender="batch-ext@synthetic.local", subject="Extraction test",
            body="Patient 45 yo male with Drug Beta.",
        )
        doc = InboxRepository.create_document(
            db=db, email_id=email.id, filename="ext_test.pdf",
            extracted_text="Patient 45 yo male. Developed urticaria. Reporter: Dr. Smith, USA. Drug Beta 50mg.",
        )
        InboxRepository.add_classification(
            db=db, document_id=doc.id, category="ICSR", confidence=0.9,
            reason="Adverse reaction reported.",
        )

        service = AIService(api_key="")
        result = service.extract_and_store(db, document_id=doc.id)
        assert result.success is True
        assert result.document_id == doc.id
        assert result.facts_stored >= 1

    def test_classify_confidence_from_primary_item(self, db):
        email = InboxRepository.create_email(
            db=db, sender="conf@synthetic.local", subject="Confidence test",
            body="Patient developed severe nausea after taking Med-X.",
        )
        doc = InboxRepository.create_document(
            db=db, email_id=email.id, filename="conf_test.pdf",
            extracted_text="Patient developed severe nausea after taking Med-X.",
        )

        service = AIService(api_key="")
        result = service.classify_and_store(db, document_id=doc.id)
        assert result.classifications is not None
        assert len(result.classifications) >= 1
        primary = result.classifications[0]
        assert 0.0 <= primary.confidence <= 1.0

    def test_batch_documents_all_have_pdf_type(self, db):
        SyntheticDataService.generate_full_synthetic_suite(db)
        docs = InboxRepository.list_documents(db, limit=50)
        valid_types = {
            DocumentType.PDF_DIGITAL.value,
            DocumentType.PDF_SCANNED.value,
            DocumentType.ARTICLE.value,
        }
        for doc in docs:
            assert doc.document_type in valid_types, (
                f"Doc {doc.filename} has invalid type: {doc.document_type}"
            )

    def test_batch_documents_all_pending_initially(self, db):
        SyntheticDataService.generate_full_synthetic_suite(db)
        docs = InboxRepository.list_documents(db, limit=50)
        for doc in docs:
            assert doc.processing_status == ProcessingStatus.PENDING.value

    def test_batch_email_body_text_available(self, db):
        SyntheticDataService.generate_full_synthetic_suite(db)
        emails = InboxRepository.list_emails(db, limit=50)
        for e in emails:
            assert e.body is not None
            assert len(e.body) > 0

    def test_classify_and_store_updates_email_status(self, db):
        email = InboxRepository.create_email(
            db=db, sender="status@synthetic.local", subject="Status update test",
            body="Quality complaint about cracked vial, lot LOT-1234.",
        )

        service = AIService(api_key="")
        result = service.classify_and_store(db, email_id=email.id)
        assert result.success is True

        db.refresh(email)
        assert email.processing_status == ProcessingStatus.COMPLETED.value

    def test_classify_and_store_creates_audit_log(self, db):
        email = InboxRepository.create_email(
            db=db, sender="audit@synthetic.local", subject="Audit test",
            body="Adverse event: patient developed rash after Drug Y.",
        )

        service = AIService(api_key="")
        service.classify_and_store(db, email_id=email.id)

        from app.models.audit_log import AuditLog
        logs = db.query(AuditLog).filter(AuditLog.email_id == email.id).all()
        assert len(logs) >= 1
        assert any(l.event == "AI_CLASSIFICATION_COMPLETED" for l in logs)
