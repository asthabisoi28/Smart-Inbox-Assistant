"""
Unit and integration tests for Reviewer Dashboard Backend APIs.

Covers:
1. GET  /api/documents                       — List processed documents (with filters & pagination)
2. GET  /api/documents/{id}                  — Get single document details
3. GET  /api/documents/{id}/classifications  — Get classifications for a document
4. GET  /api/documents/{id}/facts            — Get extracted facts for a document
5. GET  /api/documents/{id}/audit            — Get processing and review audit history
6. POST /api/documents/{id}/review/accept    — Reviewer accepts AI classification
7. POST /api/documents/{id}/review/override  — Reviewer overrides AI classification
8. PUT  /api/documents/{id}/facts            — Reviewer updates or adds extracted facts
9. Error handling (404 on missing documents, validation errors)
"""

from datetime import datetime
import pytest
from fastapi.testclient import TestClient

from app.models.enums import ClassificationCategory, ProcessingStatus, ReviewActionType
from app.models.document import Document
from app.models.classification import Classification
from app.models.extracted_fact import ExtractedFact
from app.models.review_action import ReviewAction
from app.models.audit_log import AuditLog
from app.repositories.inbox_repository import InboxRepository


@pytest.fixture
def sample_document(db):
    """Creates a sample email, document, classification, facts, and audit log."""
    email = InboxRepository.create_email(
        db=db,
        sender="dr.smith@hospital.org",
        subject="ICSR Safety Report",
        body="Patient Jane Doe (52 yo female) experienced rash and bronchospasm.",
    )
    doc = InboxRepository.create_document(
        db=db,
        email_id=email.id,
        filename="safety_case_101.pdf",
        extracted_text="Patient Jane Doe, 52 yo female. Developed rash and bronchospasm after Drug Alpha.",
        language="en",
        ocr_confidence=0.98,
        status=ProcessingStatus.COMPLETED,
        processing_time=1.25,
    )
    # Add classification
    InboxRepository.add_classification(
        db=db,
        document_id=doc.id,
        category=ClassificationCategory.ICSR,
        confidence=0.96,
        reason="Patient, reporter, suspect drug and adverse events identified.",
    )
    # Add extracted facts
    InboxRepository.add_extracted_fact(
        db=db,
        document_id=doc.id,
        category=ClassificationCategory.ICSR,
        field_name="patient.age",
        field_value="52",
        confidence=0.95,
        source_type="pdf_text",
        source_reference="PDF Page 1",
    )
    InboxRepository.add_extracted_fact(
        db=db,
        document_id=doc.id,
        category=ClassificationCategory.ICSR,
        field_name="patient.sex",
        field_value="Female",
        confidence=0.95,
        source_type="pdf_text",
        source_reference="PDF Page 1",
    )
    InboxRepository.add_extracted_fact(
        db=db,
        document_id=doc.id,
        category=ClassificationCategory.ICSR,
        field_name="reaction.reaction",
        field_value="Rash and bronchospasm",
        confidence=0.92,
        source_type="pdf_text",
        source_reference="PDF Page 1",
    )
    # Add audit log
    InboxRepository.log_event(
        db=db,
        document_id=doc.id,
        email_id=email.id,
        event="AI_CLASSIFICATION_COMPLETED",
        details="Document classified as ICSR (96% confidence)",
    )
    return doc


# ─────────────────────────────────────────────────────────────────────────────
# 1. GET /api/documents — List processed documents
# ─────────────────────────────────────────────────────────────────────────────

def test_list_documents(client: TestClient, sample_document):
    response = client.get("/api/documents")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1

    item = next(d for d in data if d["id"] == sample_document.id)
    assert item["filename"] == "safety_case_101.pdf"
    assert item["primary_category"] == "ICSR"
    assert item["classifications_count"] >= 1
    assert item["facts_count"] >= 3
    assert item["processing_status"] == "COMPLETED"


def test_list_documents_filtering(client: TestClient, sample_document, db):
    # Add another document with PQC classification
    pqc_doc = InboxRepository.create_document(
        db=db,
        filename="pqc_defect.pdf",
        status=ProcessingStatus.PENDING,
    )
    InboxRepository.add_classification(
        db=db,
        document_id=pqc_doc.id,
        category=ClassificationCategory.PQC,
        confidence=0.9,
    )

    # Filter by category ICSR
    res_icsr = client.get("/api/documents?category=ICSR")
    assert res_icsr.status_code == 200
    data_icsr = res_icsr.json()
    assert any(d["id"] == sample_document.id for d in data_icsr)
    assert not any(d["id"] == pqc_doc.id for d in data_icsr)

    # Filter by status PENDING
    res_pending = client.get("/api/documents?status=PENDING")
    assert res_pending.status_code == 200
    data_pending = res_pending.json()
    assert any(d["id"] == pqc_doc.id for d in data_pending)
    assert not any(d["id"] == sample_document.id for d in data_pending)


# ─────────────────────────────────────────────────────────────────────────────
# 2. GET /api/documents/{id} — Get single document details
# ─────────────────────────────────────────────────────────────────────────────

def test_get_document_details(client: TestClient, sample_document):
    response = client.get(f"/api/documents/{sample_document.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == sample_document.id
    assert data["filename"] == "safety_case_101.pdf"
    assert data["primary_category"] == "ICSR"
    assert "rash and bronchospasm" in data["extracted_text"]
    assert data["ocr_confidence"] == 0.98


def test_get_document_details_not_found(client: TestClient):
    response = client.get("/api/documents/999999")
    assert response.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# 3. GET /api/documents/{id}/classifications — Get classifications
# ─────────────────────────────────────────────────────────────────────────────

def test_get_document_classifications(client: TestClient, sample_document):
    response = client.get(f"/api/documents/{sample_document.id}/classifications")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["category"] == "ICSR"
    assert data[0]["confidence"] == 0.96
    assert "reason" in data[0]


def test_get_document_classifications_not_found(client: TestClient):
    response = client.get("/api/documents/999999/classifications")
    assert response.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# 4. GET /api/documents/{id}/facts — Get extracted facts
# ─────────────────────────────────────────────────────────────────────────────

def test_get_document_facts(client: TestClient, sample_document):
    response = client.get(f"/api/documents/{sample_document.id}/facts")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 3

    fact_map = {f["field_name"]: f["field_value"] for f in data}
    assert fact_map["patient.age"] == "52"
    assert fact_map["patient.sex"] == "Female"
    assert fact_map["reaction.reaction"] == "Rash and bronchospasm"
    for f in data:
        assert f["confidence"] is not None
        assert f["source_reference"] == "PDF Page 1"


def test_get_document_facts_filtered(client: TestClient, sample_document):
    response = client.get(f"/api/documents/{sample_document.id}/facts?category=ICSR")
    assert response.status_code == 200
    assert len(response.json()) == 3

    response_pqc = client.get(f"/api/documents/{sample_document.id}/facts?category=PQC")
    assert response_pqc.status_code == 200
    assert len(response_pqc.json()) == 0


# ─────────────────────────────────────────────────────────────────────────────
# 5. GET /api/documents/{id}/audit — Get audit history
# ─────────────────────────────────────────────────────────────────────────────

def test_get_document_audit_history(client: TestClient, sample_document, db):
    # Record a review action
    InboxRepository.record_review_action(
        db=db,
        document_id=sample_document.id,
        reviewer="auditor_jane",
        action=ReviewActionType.ACCEPT,
        comments="Initial quality audit passed.",
    )

    response = client.get(f"/api/documents/{sample_document.id}/audit")
    assert response.status_code == 200
    data = response.json()
    assert data["document_id"] == sample_document.id
    assert "audit_logs" in data
    assert "review_actions" in data
    assert len(data["audit_logs"]) >= 1
    assert any(log["event"] == "AI_CLASSIFICATION_COMPLETED" for log in data["audit_logs"])
    assert len(data["review_actions"]) >= 1
    assert data["review_actions"][0]["reviewer"] == "auditor_jane"
    assert data["review_actions"][0]["action"] == "ACCEPT"


# ─────────────────────────────────────────────────────────────────────────────
# 6. POST /api/documents/{id}/review/accept — Accept AI result
# ─────────────────────────────────────────────────────────────────────────────

def test_accept_document_review(client: TestClient, sample_document, db):
    payload = {
        "reviewer": "qc_officer_mark",
        "comments": "Classification verified against source document.",
    }
    response = client.post(f"/api/documents/{sample_document.id}/review/accept", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["document_id"] == sample_document.id
    assert data["action"] == "ACCEPT"
    assert data["reviewer"] == "qc_officer_mark"
    assert data["current_category"] == "ICSR"
    assert "timestamp" in data

    # Verify review action saved in DB
    actions = InboxRepository.get_review_history(db, document_id=sample_document.id)
    assert any(a.reviewer == "qc_officer_mark" and a.action == "ACCEPT" for a in actions)

    # Verify audit log saved in DB
    logs = InboxRepository.get_audit_logs(db, document_id=sample_document.id)
    assert any(l.event == "REVIEW_ACCEPTED" for l in logs)


# ─────────────────────────────────────────────────────────────────────────────
# 7. POST /api/documents/{id}/review/override — Override AI result
# ─────────────────────────────────────────────────────────────────────────────

def test_override_document_review(client: TestClient, sample_document, db):
    payload = {
        "reviewer": "senior_auditor_pat",
        "new_category": "PQC",
        "reason": "Primary defect is cracked autoinjector mechanism; adverse event was secondary.",
        "comments": "Re-routed to Quality Engineering team.",
    }
    response = client.post(f"/api/documents/{sample_document.id}/review/override", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["document_id"] == sample_document.id
    assert data["action"] == "OVERRIDE"
    assert data["reviewer"] == "senior_auditor_pat"
    assert data["current_category"] == "PQC"

    # Verify classification in DB was updated with new category
    classifications = InboxRepository.get_classifications(db, document_id=sample_document.id)
    assert classifications[0].category == "PQC"
    assert classifications[0].confidence == 1.0

    # Verify review action saved in DB
    actions = InboxRepository.get_review_history(db, document_id=sample_document.id)
    assert any(a.reviewer == "senior_auditor_pat" and a.action == "OVERRIDE" for a in actions)

    # Verify audit log saved in DB
    logs = InboxRepository.get_audit_logs(db, document_id=sample_document.id)
    assert any(l.event == "REVIEW_OVERRIDDEN" for l in logs)


# ─────────────────────────────────────────────────────────────────────────────
# 8. PUT /api/documents/{id}/facts — Update extracted fields
# ─────────────────────────────────────────────────────────────────────────────

def test_update_document_facts(client: TestClient, sample_document, db):
    payload = {
        "reviewer": "clinical_data_specialist",
        "comments": "Corrected patient age and added missing patient weight.",
        "facts": [
            {
                "field_name": "patient.age",
                "field_value": "53",  # Corrected from 52
                "confidence": 1.0,
                "source_reference": "Verified on Medical Records Page 2",
            },
            {
                "field_name": "patient.weight",
                "field_value": "68 kg",  # New field
                "confidence": 1.0,
                "source_reference": "Vital Signs Table Page 1",
            },
        ],
    }
    response = client.put(f"/api/documents/{sample_document.id}/facts", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["document_id"] == sample_document.id
    assert data["updated_count"] == 2
    assert "timestamp" in data

    # Verify facts in DB
    facts = InboxRepository.get_facts_by_document(db, document_id=sample_document.id)
    fact_map = {f.field_name: f.field_value for f in facts}
    assert fact_map["patient.age"] == "53"
    assert fact_map["patient.weight"] == "68 kg"

    # Verify review action and audit log
    actions = InboxRepository.get_review_history(db, document_id=sample_document.id)
    assert any(a.reviewer == "clinical_data_specialist" for a in actions)

    logs = InboxRepository.get_audit_logs(db, document_id=sample_document.id)
    assert any(l.event == "FACTS_UPDATED" for l in logs)
