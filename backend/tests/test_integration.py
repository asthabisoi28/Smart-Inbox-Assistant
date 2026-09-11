"""
Integration tests for Smart Inbox Assistant.

Covers:
1. Missing-field handling (Not stated defaults, zero confidence)
2. Classification response validation (schema enforcement, edge cases)
3. Database operations (CRUD, cascade, constraint enforcement)
4. Review accept/override full workflow
5. Audit logging completeness
6. Synthetic data generation & idempotency
7. End-to-end document processing pipeline
"""

import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock

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
from app.schemas.ai_schemas import (
    ExtractedField,
    PatientInfo,
    ReporterInfo,
    ProductInfo,
    ReactionInfo,
    SeverityInfo,
    NarrativeInfo,
    ICSRExtraction,
    PQCExtraction,
    MIExtraction,
    ExtractionResult,
    ClassificationItem,
    ClassificationResult,
)
from app.services.ai_service import AIService


# =============================================================================
# 1. Missing-Field Handling Tests
# =============================================================================

class TestMissingFieldHandling:
    """Ensure all fields default to 'Not stated' with confidence 0 when absent."""

    def test_extracted_field_defaults_to_not_stated(self):
        field = ExtractedField()
        assert field.value == "Not stated"
        assert field.confidence == 0.0
        assert field.source_reference == "Not stated"

    def test_patient_info_all_missing(self):
        patient = PatientInfo()
        assert patient.age.value == "Not stated"
        assert patient.sex.value == "Not stated"
        assert patient.weight.value == "Not stated"
        assert patient.height.value == "Not stated"
        assert patient.relevant_history.value == "Not stated"
        for attr in ["age", "sex", "weight", "height", "relevant_history"]:
            assert getattr(patient, attr).confidence == 0.0

    def test_reporter_info_all_missing(self):
        reporter = ReporterInfo()
        assert reporter.name.value == "Not stated"
        assert reporter.role.value == "Not stated"
        assert reporter.country.value == "Not stated"

    def test_product_info_all_missing(self):
        product = ProductInfo()
        assert product.name.value == "Not stated"
        assert product.dose.value == "Not stated"
        assert product.route.value == "Not stated"
        assert product.start_date.value == "Not stated"
        assert product.stop_date.value == "Not stated"

    def test_reaction_info_all_missing(self):
        reaction = ReactionInfo()
        assert reaction.reaction.value == "Not stated"
        assert reaction.start_date.value == "Not stated"
        assert reaction.outcome.value == "Not stated"

    def test_severity_info_all_missing(self):
        severity = SeverityInfo()
        assert severity.serious.value == "Not stated"
        assert severity.death.value == "Not stated"
        assert severity.hospitalization.value == "Not stated"
        assert severity.life_threatening.value == "Not stated"
        assert severity.other_severity.value == "Not stated"

    def test_icsr_all_missing_defaults(self):
        icsr = ICSRExtraction()
        assert icsr.patient.age.value == "Not stated"
        assert icsr.reporter.name.value == "Not stated"
        assert icsr.product.name.value == "Not stated"
        assert icsr.reaction.reaction.value == "Not stated"
        assert icsr.severity.serious.value == "Not stated"
        assert icsr.narrative.case_summary.value == "Not stated"

    def test_pqc_all_missing_defaults(self):
        pqc = PQCExtraction()
        assert pqc.product.value == "Not stated"
        assert pqc.lot_number.value == "Not stated"
        assert pqc.problem.value == "Not stated"
        assert pqc.photo_mentioned.value == "Not stated"

    def test_mi_all_missing_defaults(self):
        mi = MIExtraction()
        assert mi.questions_asked.value == "Not stated"
        assert mi.product_topic.value == "Not stated"

    def test_extraction_result_missing_fields_count(self):
        # facts_count tracks stated facts only; empty ICSR yields 0
        result = ExtractionResult(
            category=ClassificationCategory.ICSR,
            icsr=ICSRExtraction(),
        )
        assert result.facts_count == 0
        for group_name in ["patient", "reporter", "product", "reaction", "severity", "narrative"]:
            group = getattr(result.icsr, group_name)
            for field_name, field_obj in group:
                assert field_obj.value == "Not stated"
                assert field_obj.confidence == 0.0

    def test_fact_stored_as_not_stated_in_db(self, db):
        doc = InboxRepository.create_document(
            db=db,
            filename="missing_fields.pdf",
            status=ProcessingStatus.COMPLETED,
        )
        fact = InboxRepository.add_extracted_fact(
            db=db,
            document_id=doc.id,
            category=ClassificationCategory.ICSR,
            field_name="patient.weight",
            field_value="Not stated",
            confidence=0.0,
            source_type=FactSourceType.PDF_TEXT,
            source_reference="Not available",
        )
        assert fact.field_value == "Not stated"
        assert fact.confidence == 0.0

    def test_none_field_value_defaults_to_not_stated_in_db(self, db):
        doc = InboxRepository.create_document(
            db=db,
            filename="null_field.pdf",
            status=ProcessingStatus.COMPLETED,
        )
        fact = InboxRepository.add_extracted_fact(
            db=db,
            document_id=doc.id,
            category=ClassificationCategory.ICSR,
            field_name="patient.height",
            field_value=None,  # Should default to "Not stated"
            confidence=0.0,
        )
        assert fact.field_value == "Not stated"

    def test_heuristic_marks_unfound_fields_as_not_stated(self):
        service = AIService(api_key="")
        # Minimal text with no patient info
        content = "Some generic text without any medical detail."
        result, model = service._heuristic_fallback_extract(content, ClassificationCategory.ICSR)
        assert result.icsr.patient.age.value == "Not stated"
        assert result.icsr.patient.sex.value == "Not stated"
        assert result.icsr.patient.weight.value == "Not stated"
        assert result.icsr.reporter.name.value == "Not stated"


# =============================================================================
# 2. Classification Response Validation Tests
# =============================================================================

class TestClassificationValidation:
    """Test Pydantic schema enforcement for classification responses."""

    def test_classification_requires_at_least_one_item(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ClassificationResult(
                classifications=[],
                primary_category=ClassificationCategory.ICSR,
                summary="Summary with enough text for validation.",
            )

    def test_classification_summary_minimum_length(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ClassificationResult(
                classifications=[
                    ClassificationItem(
                        category=ClassificationCategory.MI,
                        confidence=0.85,
                        reason="Patient asked about dosage for Drug Z.",
                    )
                ],
                primary_category=ClassificationCategory.MI,
                summary="X",  # Too short
            )

    def test_primary_category_auto_correction(self):
        result = ClassificationResult(
            classifications=[
                ClassificationItem(
                    category=ClassificationCategory.PQC,
                    confidence=0.9,
                    reason="Packaging complaint reported with visible damage.",
                ),
            ],
            primary_category=ClassificationCategory.ICSR,  # Doesn't match items
            summary="Product quality complaint regarding packaging integrity.",
        )
        assert result.primary_category == ClassificationCategory.PQC

    def test_confidence_clamping_upper_bound(self):
        item = ClassificationItem(
            category=ClassificationCategory.ICSR,
            confidence=1.5,
            reason="Adverse reaction reported with extreme confidence.",
        )
        assert item.confidence == 1.0

    def test_confidence_clamping_lower_bound(self):
        item = ClassificationItem(
            category=ClassificationCategory.MI,
            confidence=-0.5,
            reason="Information request with negative confidence scenario.",
        )
        assert item.confidence == 0.0

    def test_multi_category_result(self):
        result = ClassificationResult(
            classifications=[
                ClassificationItem(
                    category=ClassificationCategory.ICSR,
                    confidence=0.95,
                    reason="Patient developed urticaria requiring hospitalization.",
                ),
                ClassificationItem(
                    category=ClassificationCategory.PQC,
                    confidence=0.80,
                    reason="Defective device mechanism caused the injury.",
                ),
            ],
            primary_category=ClassificationCategory.ICSR,
            summary="Dual classification: safety event caused by defective device.",
        )
        assert len(result.classifications) == 2
        assert result.primary_category == ClassificationCategory.ICSR


# =============================================================================
# 3. Database Operations Tests
# =============================================================================

class TestDatabaseOperations:
    """Test database CRUD, cascades, constraints, and edge cases."""

    def test_email_unique_message_id_constraint(self, db):
        InboxRepository.create_email(
            db=db,
            sender="test@example.com",
            message_id="<unique-123@test.com>",
        )
        with pytest.raises(Exception):
            InboxRepository.create_email(
                db=db,
                sender="test@example.com",
                message_id="<unique-123@test.com>",
            )

    def test_email_null_message_id_allowed(self, db):
        e1 = InboxRepository.create_email(db=db, sender="a@b.com")
        e2 = InboxRepository.create_email(db=db, sender="c@d.com")
        assert e1.id != e2.id
        assert e1.message_id is None
        assert e2.message_id is None

    def test_document_cascade_delete(self, db):
        email = InboxRepository.create_email(db=db, sender="cascade@test.com")
        doc = InboxRepository.create_document(
            db=db, email_id=email.id, filename="cascade.pdf"
        )
        InboxRepository.add_extracted_fact(
            db=db,
            document_id=doc.id,
            category=ClassificationCategory.ICSR,
            field_name="test_field",
            field_value="test_value",
        )
        InboxRepository.add_classification(
            db=db,
            document_id=doc.id,
            category=ClassificationCategory.ICSR,
            confidence=0.9,
        )
        # Delete email should cascade to documents, facts, and classifications
        db.delete(email)
        db.commit()
        assert InboxRepository.get_document_by_id(db, doc.id) is None

    def test_facts_upsert_updates_existing(self, db):
        doc = InboxRepository.create_document(db=db, filename="upsert.pdf")
        InboxRepository.add_extracted_fact(
            db=db,
            document_id=doc.id,
            category=ClassificationCategory.PQC,
            field_name="product",
            field_value="Drug A",
            confidence=0.8,
        )
        updated = InboxRepository.upsert_extracted_fact(
            db=db,
            document_id=doc.id,
            field_name="product",
            field_value="Drug B (Corrected)",
            category=ClassificationCategory.PQC,
            confidence=1.0,
        )
        assert updated.field_value == "Drug B (Corrected)"
        assert updated.confidence == 1.0
        # Should still have only 1 fact
        facts = InboxRepository.get_facts_by_document(db, doc.id)
        assert len(facts) == 1

    def test_facts_clear_by_document(self, db):
        doc = InboxRepository.create_document(db=db, filename="clear.pdf")
        for i in range(5):
            InboxRepository.add_extracted_fact(
                db=db,
                document_id=doc.id,
                category=ClassificationCategory.ICSR,
                field_name=f"field_{i}",
                field_value=f"value_{i}",
            )
        deleted = InboxRepository.clear_facts_by_document(db, doc.id)
        assert deleted == 5
        remaining = InboxRepository.get_facts_by_document(db, doc.id)
        assert len(remaining) == 0

    def test_list_documents_with_pagination(self, db):
        for i in range(10):
            InboxRepository.create_document(db=db, filename=f"page_{i}.pdf")
        page1 = InboxRepository.list_documents(db, skip=0, limit=5)
        page2 = InboxRepository.list_documents(db, skip=5, limit=5)
        assert len(page1) == 5
        assert len(page2) == 5
        # No overlap
        ids_1 = {d.id for d in page1}
        ids_2 = {d.id for d in page2}
        assert ids_1.isdisjoint(ids_2)

    def test_list_documents_with_status_filter(self, db):
        InboxRepository.create_document(
            db=db, filename="completed.pdf", status=ProcessingStatus.COMPLETED
        )
        InboxRepository.create_document(
            db=db, filename="pending.pdf", status=ProcessingStatus.PENDING
        )
        completed = InboxRepository.list_documents(db, status=ProcessingStatus.COMPLETED)
        assert all(d.processing_status == "COMPLETED" for d in completed)


# =============================================================================
# 4. Review Accept/Override Workflow Tests
# =============================================================================

class TestReviewWorkflow:
    """Test full review lifecycle: accept, override, and their audit trails."""

    def _create_classified_document(self, db):
        email = InboxRepository.create_email(
            db=db, sender="reviewer-test@hosp.com", subject="Test Case"
        )
        doc = InboxRepository.create_document(
            db=db,
            email_id=email.id,
            filename="review_test.pdf",
            status=ProcessingStatus.COMPLETED,
        )
        InboxRepository.add_classification(
            db=db,
            document_id=doc.id,
            category=ClassificationCategory.ICSR,
            confidence=0.92,
            reason="Patient had adverse reaction after taking drug.",
        )
        return doc

    def test_accept_review_creates_action_and_audit(self, db):
        doc = self._create_classified_document(db)
        action = InboxRepository.record_review_action(
            db=db,
            document_id=doc.id,
            reviewer="reviewer_alice",
            action=ReviewActionType.ACCEPT,
            comments="Verified classification matches source.",
        )
        InboxRepository.log_event(
            db=db,
            document_id=doc.id,
            event="REVIEW_ACCEPTED",
            details="Accepted by reviewer_alice",
        )

        actions = InboxRepository.get_review_history(db, document_id=doc.id)
        assert len(actions) == 1
        assert actions[0].action == "ACCEPT"
        assert actions[0].reviewer == "reviewer_alice"

        logs = InboxRepository.get_audit_logs(db, document_id=doc.id)
        assert any(l.event == "REVIEW_ACCEPTED" for l in logs)

    def test_override_review_updates_classification(self, db):
        doc = self._create_classified_document(db)

        # Record override action
        InboxRepository.record_review_action(
            db=db,
            document_id=doc.id,
            reviewer="senior_reviewer_bob",
            action=ReviewActionType.OVERRIDE,
            comments="Reclassified from ICSR to PQC.",
        )

        # Update classification to reflect override
        InboxRepository.add_classification(
            db=db,
            document_id=doc.id,
            category=ClassificationCategory.PQC,
            confidence=1.0,
            reason="Reviewer override: product defect, not safety event.",
        )

        InboxRepository.log_event(
            db=db,
            document_id=doc.id,
            event="REVIEW_OVERRIDDEN",
            details="Changed from ICSR to PQC by senior_reviewer_bob",
        )

        classifications = InboxRepository.get_classifications(db, document_id=doc.id)
        # Most recent classification should be PQC
        assert classifications[0].category == "PQC"

        actions = InboxRepository.get_review_history(db, document_id=doc.id)
        assert any(a.action == "OVERRIDE" for a in actions)

    def test_multiple_reviews_maintain_history(self, db):
        doc = self._create_classified_document(db)

        for i in range(3):
            InboxRepository.record_review_action(
                db=db,
                document_id=doc.id,
                reviewer=f"reviewer_{i}",
                action=ReviewActionType.ACCEPT,
                comments=f"Review pass #{i + 1}",
            )

        actions = InboxRepository.get_review_history(db, document_id=doc.id)
        assert len(actions) == 3

    def test_accept_via_api_endpoint(self, client, db):
        email = InboxRepository.create_email(db=db, sender="api-test@host.com")
        doc = InboxRepository.create_document(
            db=db, email_id=email.id, filename="api_accept.pdf",
            status=ProcessingStatus.COMPLETED,
        )
        InboxRepository.add_classification(
            db=db, document_id=doc.id,
            category=ClassificationCategory.MI, confidence=0.88,
            reason="Dosage inquiry.",
        )

        response = client.post(
            f"/api/documents/{doc.id}/review/accept",
            json={"reviewer": "api_tester", "comments": "OK"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["action"] == "ACCEPT"

    def test_override_via_api_endpoint(self, client, db):
        email = InboxRepository.create_email(db=db, sender="api-test2@host.com")
        doc = InboxRepository.create_document(
            db=db, email_id=email.id, filename="api_override.pdf",
            status=ProcessingStatus.COMPLETED,
        )
        InboxRepository.add_classification(
            db=db, document_id=doc.id,
            category=ClassificationCategory.MI, confidence=0.7,
            reason="Inquiry detected.",
        )

        response = client.post(
            f"/api/documents/{doc.id}/review/override",
            json={
                "reviewer": "api_tester",
                "new_category": "PQC",
                "reason": "Actually a quality complaint.",
                "comments": "Misclassified by AI.",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["current_category"] == "PQC"


# =============================================================================
# 5. Audit Logging Tests
# =============================================================================

class TestAuditLogging:
    """Test audit log completeness and traceability."""

    def test_audit_log_has_timestamp(self, db):
        email = InboxRepository.create_email(db=db, sender="audit@test.com")
        log = InboxRepository.log_event(
            db=db,
            email_id=email.id,
            event="TEST_EVENT",
            details="Testing timestamp persistence.",
        )
        assert log.timestamp is not None
        assert isinstance(log.timestamp, datetime)

    def test_audit_log_tracks_document_and_email(self, db):
        email = InboxRepository.create_email(db=db, sender="audit2@test.com")
        doc = InboxRepository.create_document(
            db=db, email_id=email.id, filename="audit_doc.pdf"
        )
        log = InboxRepository.log_event(
            db=db,
            email_id=email.id,
            document_id=doc.id,
            event="DOCUMENT_PROCESSED",
            details="PDF processed and classified.",
        )
        assert log.email_id == email.id
        assert log.document_id == doc.id

    def test_audit_log_filtering_by_document(self, db):
        email = InboxRepository.create_email(db=db, sender="audit3@test.com")
        doc1 = InboxRepository.create_document(
            db=db, email_id=email.id, filename="doc1.pdf"
        )
        doc2 = InboxRepository.create_document(
            db=db, email_id=email.id, filename="doc2.pdf"
        )
        InboxRepository.log_event(db=db, document_id=doc1.id, event="EVENT_A")
        InboxRepository.log_event(db=db, document_id=doc2.id, event="EVENT_B")

        logs_doc1 = InboxRepository.get_audit_logs(db, document_id=doc1.id)
        assert all(l.document_id == doc1.id for l in logs_doc1)
        assert len(logs_doc1) == 1

    def test_audit_via_api(self, client, db):
        email = InboxRepository.create_email(db=db, sender="audit-api@test.com")
        doc = InboxRepository.create_document(
            db=db, email_id=email.id, filename="audit_api.pdf"
        )
        InboxRepository.log_event(
            db=db, document_id=doc.id, email_id=email.id,
            event="AI_CLASSIFICATION_COMPLETED",
            details="Classified as ICSR",
        )

        response = client.get(f"/api/documents/{doc.id}/audit")
        assert response.status_code == 200
        data = response.json()
        assert data["document_id"] == doc.id
        assert len(data["audit_logs"]) >= 1
        assert data["audit_logs"][0]["event"] == "AI_CLASSIFICATION_COMPLETED"


# =============================================================================
# 6. End-to-End Heuristic Pipeline Tests
# =============================================================================

class TestEndToEndPipeline:
    """Test end-to-end classification + extraction using heuristic fallback."""

    def test_full_icsr_pipeline(self, db):
        email = InboxRepository.create_email(
            db=db,
            sender="dr.test@clinic.com",
            subject="Safety Report",
            body="Patient 65 yo male developed severe angioedema after Drug Alpha 50mg.",
        )
        doc = InboxRepository.create_document(
            db=db,
            email_id=email.id,
            filename="safety_report.pdf",
            extracted_text=(
                "Patient: 65 years old male, weight 82 kg, history: diabetes. "
                "Reporter: Dr. James Wilson, Physician, USA. "
                "Product: Drug Alpha 50mg oral daily from 2026-01-15 to 2026-01-30. "
                "Reaction: Severe angioedema and respiratory distress. Onset: 2026-01-28. "
                "Outcome: Hospitalized, recovering. "
                "Serious: Yes. Death: No. Hospitalization: Yes. Life-threatening: Yes."
            ),
        )

        service = AIService(api_key="")

        # Classify
        classify_result = service.classify_and_store(db=db, email_id=email.id)
        assert classify_result.success is True
        assert classify_result.primary_category == ClassificationCategory.ICSR

        # Extract
        extract_result = service.extract_and_store(db=db, document_id=doc.id)
        assert extract_result.success is True
        assert extract_result.category == ClassificationCategory.ICSR
        assert extract_result.facts_stored > 5

        # Verify facts in DB
        facts = InboxRepository.get_facts_by_document(db, doc.id)
        fact_map = {f.field_name: f for f in facts}
        assert "patient.age" in fact_map
        assert fact_map["patient.age"].field_value == "65"
        assert fact_map["patient.age"].confidence > 0

        # Every fact should have source_reference
        for f in facts:
            assert f.source_reference is not None

    def test_full_pqc_pipeline(self, db):
        email = InboxRepository.create_email(
            db=db,
            sender="quality@pharm.com",
            subject="Product Defect Report",
            body="Complaint: broken seal on Drug Beta lot LOT-7788.",
        )
        doc = InboxRepository.create_document(
            db=db,
            email_id=email.id,
            filename="pqc_report.pdf",
            extracted_text=(
                "Product: Drug Beta 100mg tablets. "
                "Batch/Lot Number: LOT-7788. "
                "Problem: Broken seal on bottle, tablets exposed to moisture. "
                "Photo attached for reference."
            ),
        )

        service = AIService(api_key="")
        classify_result = service.classify_and_store(db=db, email_id=email.id)
        assert classify_result.primary_category == ClassificationCategory.PQC

        extract_result = service.extract_and_store(db=db, document_id=doc.id)
        assert extract_result.category == ClassificationCategory.PQC

        facts = InboxRepository.get_facts_by_document(db, doc.id)
        fact_map = {f.field_name: f.field_value for f in facts}
        assert "lot_number" in fact_map
        assert "LOT-7788" in fact_map["lot_number"]

    def test_full_mi_pipeline(self, db):
        email = InboxRepository.create_email(
            db=db,
            sender="nurse@hospital.com",
            subject="Dosage Question for Drug Gamma",
            body="What is the recommended dosage of Drug Gamma for elderly patients with renal impairment?",
        )
        doc = InboxRepository.create_document(
            db=db,
            email_id=email.id,
            filename="mi_inquiry.pdf",
            extracted_text="Regarding Drug Gamma: What is the recommended dosage for elderly patients? How does renal impairment affect dosing?",
        )

        service = AIService(api_key="")
        classify_result = service.classify_and_store(db=db, email_id=email.id)
        assert classify_result.primary_category == ClassificationCategory.MI

        extract_result = service.extract_and_store(db=db, document_id=doc.id)
        assert extract_result.category == ClassificationCategory.MI

        facts = InboxRepository.get_facts_by_document(db, doc.id)
        assert len(facts) >= 1


# =============================================================================
# 7. Synthetic Data Generation Tests
# =============================================================================

class TestSyntheticDataGeneration:
    """Test that synthetic data generation works correctly."""

    def test_synthetic_suite_generates_correct_counts(self, db):
        from app.services.synthetic_data_service import SyntheticDataService
        result = SyntheticDataService.generate_full_synthetic_suite(db)
        assert result["success"] is True
        assert result["emails_created"] >= 10
        assert result["documents_created"] >= 12
        coverage = result["coverage"]
        assert coverage["email"] >= 10
        assert coverage["digital_pdf"] >= 5
        assert coverage["scanned_pdf"] >= 2
        assert coverage["article"] >= 5
        assert coverage["non_english"] >= 2
        assert coverage["quality_complaint"] >= 2
        assert coverage["info_request"] >= 2
        assert coverage["marketing"] >= 1

    def test_synthetic_suite_idempotent_rerun(self, db):
        from app.services.synthetic_data_service import SyntheticDataService
        # First run
        res1 = SyntheticDataService.generate_full_synthetic_suite(db)
        assert res1["emails_created"] >= 10
        # Second run - UUID-based IDs should create new entries
        res2 = SyntheticDataService.generate_full_synthetic_suite(db)
        assert res2["emails_created"] >= 10  # New run_id means new message_ids
        assert res2["emails_skipped"] == 0

    def test_synthetic_emails_have_required_fields(self, db):
        from app.services.synthetic_data_service import SyntheticDataService
        SyntheticDataService.generate_full_synthetic_suite(db)

        emails = InboxRepository.list_emails(db, limit=50)
        for email in emails:
            assert email.sender is not None
            assert "@" in email.sender
            assert email.subject is not None
            assert email.body is not None
            assert email.processing_status == "PENDING"

    def test_synthetic_documents_have_valid_types(self, db):
        from app.services.synthetic_data_service import SyntheticDataService
        SyntheticDataService.generate_full_synthetic_suite(db)

        documents = InboxRepository.list_documents(db, limit=50)
        valid_types = {"pdf_digital", "pdf_scanned", "article"}
        for doc in documents:
            assert doc.document_type in valid_types
            assert doc.filename.endswith(".pdf")
