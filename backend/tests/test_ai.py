"""
Unit and integration tests for the AI classification service and endpoints.

Covers:
- Prompt template rendering and constraints
- Pydantic schema validation (ClassificationItem, ClassificationResult, ClassifyRequest, ClassifyResponse)
- AIService with mocked Gemini API (happy path, invalid JSON, Pydantic error, markdown fence stripping)
- AIService heuristic fallback engine (ICSR, PQC, MI, NOT_RELEVANT, multi-label)
- Safe handling of missing API keys (no crash, safe fallback)
- POST /api/ai/classify (inline text, DB reference, DB persistence, status update, audit log)
- POST /api/ai/classify/preview (dry-run, no DB modifications)
- GET /api/ai/status (service health status)
"""

import json
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.main import app
from app.models.enums import ClassificationCategory, ProcessingStatus
from app.models.email import Email
from app.models.document import Document
from app.models.classification import Classification
from app.models.extracted_fact import ExtractedFact
from app.models.audit_log import AuditLog
from app.repositories.inbox_repository import InboxRepository
from app.schemas.ai_schemas import (
    ClassificationItem,
    ClassificationResult,
    ClassifyRequest,
    ClassifyResponse,
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
    ExtractResponse,
)
from app.services.ai_service import AIService, _strip_markdown_fences, _pick_primary
from app.core.prompts import (
    CLASSIFICATION_SYSTEM_PROMPT,
    CLASSIFICATION_USER_PROMPT_TEMPLATE,
    EXTRACTION_SYSTEM_PROMPT,
    ICSR_EXTRACTION_USER_PROMPT_TEMPLATE,
    PQC_EXTRACTION_USER_PROMPT_TEMPLATE,
    MI_EXTRACTION_USER_PROMPT_TEMPLATE,
)


# =============================================================================
# 1. Pydantic Schema Tests
# =============================================================================

def test_classification_item_valid():
    item = ClassificationItem(
        category=ClassificationCategory.ICSR,
        confidence=0.95,
        reason="Patient experienced rash and dyspnea after drug administration.",
    )
    assert item.category == ClassificationCategory.ICSR
    assert item.confidence == 0.95
    assert "rash" in item.reason


def test_classification_item_confidence_clamping():
    # Confidence above 1.0 clamped
    item = ClassificationItem(
        category=ClassificationCategory.PQC,
        confidence=1.5,
        reason="Broken seal reported on packaging.",
    )
    assert item.confidence == 1.0

    # Negative confidence clamped
    item2 = ClassificationItem(
        category=ClassificationCategory.PQC,
        confidence=-0.2,
        reason="Broken seal reported on packaging.",
    )
    assert item2.confidence == 0.0


def test_classification_item_invalid_category():
    with pytest.raises(ValidationError):
        ClassificationItem(
            category="UNKNOWN_CATEGORY",
            confidence=0.9,
            reason="Test reason for invalid category.",
        )


def test_classification_item_empty_reason():
    with pytest.raises(ValidationError):
        ClassificationItem(
            category=ClassificationCategory.ICSR,
            confidence=0.9,
            reason="   ",
        )


def test_classification_result_auto_correct_primary():
    # If primary_category is not in items, auto-pick highest priority
    result = ClassificationResult(
        classifications=[
            ClassificationItem(
                category=ClassificationCategory.PQC,
                confidence=0.9,
                reason="Packaging damaged and counterfeit suspected.",
            ),
        ],
        primary_category=ClassificationCategory.ICSR,  # Not in items
        summary="Test summary with sufficient character length.",
    )
    assert result.primary_category == ClassificationCategory.PQC


def test_classify_request_validation():
    # Empty request fails
    with pytest.raises(ValidationError):
        ClassifyRequest()

    # Valid with email_text
    req = ClassifyRequest(email_text="Patient had severe nausea.")
    assert req.email_text == "Patient had severe nausea."

    # Valid with email_id
    req2 = ClassifyRequest(email_id=1)
    assert req2.email_id == 1


# =============================================================================
# 2. Prompt & Utility Tests
# =============================================================================

def test_strip_markdown_fences():
    fenced_json = '```json\n{"primary_category": "ICSR"}\n```'
    assert _strip_markdown_fences(fenced_json) == '{"primary_category": "ICSR"}'

    raw_json = '{"primary_category": "ICSR"}'
    assert _strip_markdown_fences(raw_json) == raw_json


def test_pick_primary():
    items = [
        ClassificationItem(
            category=ClassificationCategory.MI,
            confidence=0.8,
            reason="Dosage inquiry for patient.",
        ),
        ClassificationItem(
            category=ClassificationCategory.ICSR,
            confidence=0.95,
            reason="Patient experienced allergic reaction.",
        ),
    ]
    assert _pick_primary(items) == ClassificationCategory.ICSR


def test_prompt_strict_factuality_instructions():
    assert "NEVER invent" in CLASSIFICATION_SYSTEM_PROMPT
    assert "Not stated" in CLASSIFICATION_SYSTEM_PROMPT
    assert "ICSR" in CLASSIFICATION_SYSTEM_PROMPT
    assert "PQC" in CLASSIFICATION_SYSTEM_PROMPT
    assert "MI" in CLASSIFICATION_SYSTEM_PROMPT
    assert "NOT_RELEVANT" in CLASSIFICATION_SYSTEM_PROMPT


# =============================================================================
# 3. Heuristic Fallback Engine Tests (All Categories & Multi-Label)
# =============================================================================

def test_heuristic_icsr_classification():
    service = AIService(api_key="")
    text = "Patient experienced severe rash, bronchospasm, and hospitalisation following Drug X administration."
    result, model = service._heuristic_fallback_classify(text, "")
    assert result.primary_category == ClassificationCategory.ICSR
    assert any(c.category == ClassificationCategory.ICSR for c in result.classifications)
    assert "heuristic" in model


def test_heuristic_pqc_classification():
    service = AIService(api_key="")
    text = "The received batch has a broken seal and discoloration with wrong color particulate contamination."
    result, model = service._heuristic_fallback_classify(text, "")
    assert result.primary_category == ClassificationCategory.PQC
    assert any(c.category == ClassificationCategory.PQC for c in result.classifications)


def test_heuristic_mi_classification():
    service = AIService(api_key="")
    text = "Could you please provide the recommended dosage and titration guideline for renal impairment?"
    result, model = service._heuristic_fallback_classify(text, "")
    assert result.primary_category == ClassificationCategory.MI
    assert any(c.category == ClassificationCategory.MI for c in result.classifications)


def test_heuristic_not_relevant_classification():
    service = AIService(api_key="")
    text = "Join our annual sales conference and webinar. Early bird tickets available now. Click here to unsubscribe."
    result, model = service._heuristic_fallback_classify(text, "")
    assert result.primary_category == ClassificationCategory.NOT_RELEVANT
    assert any(c.category == ClassificationCategory.NOT_RELEVANT for c in result.classifications)


def test_heuristic_multi_label_classification():
    service = AIService(api_key="")
    # Combined ICSR + PQC
    text = (
        "The patient used a defective autoinjector with a cracked needle and developed "
        "a severe hematoma and nausea requiring emergency room treatment."
    )
    result, _ = service._heuristic_fallback_classify(text, "")
    categories = {c.category for c in result.classifications}
    assert ClassificationCategory.ICSR in categories
    assert ClassificationCategory.PQC in categories
    assert result.primary_category == ClassificationCategory.ICSR


# =============================================================================
# 4. Gemini API Integration Tests (Mocked)
# =============================================================================

def test_classify_with_gemini_success():
    mock_gemini_response = {
        "primary_category": "ICSR",
        "classifications": [
            {
                "category": "ICSR",
                "confidence": 0.98,
                "reason": "Female patient developed anaphylaxis after Drug Y injection.",
            },
            {
                "category": "PQC",
                "confidence": 0.85,
                "reason": "Syringe plunger was broken prior to use.",
            },
        ],
        "summary": "Dual ICSR and PQC event reported with anaphylaxis and broken syringe plunger.",
    }

    mock_client = MagicMock()
    mock_model_res = MagicMock()
    mock_model_res.text = json.dumps(mock_gemini_response)
    mock_client.models.generate_content.return_value = mock_model_res

    service = AIService(api_key="test-mock-api-key")
    with patch("google.genai.Client", return_value=mock_client):
        result, model_used = service._classify_with_gemini("email body", "pdf text")

    assert result.primary_category == ClassificationCategory.ICSR
    assert len(result.classifications) == 2
    assert result.classifications[0].confidence == 0.98
    assert model_used == service.model_name


def test_classify_with_gemini_invalid_json_fallback():
    mock_client = MagicMock()
    mock_model_res = MagicMock()
    mock_model_res.text = "NOT A JSON STRING <xml>error</xml>"
    mock_client.models.generate_content.return_value = mock_model_res

    service = AIService(api_key="test-mock-api-key")
    with patch("google.genai.Client", return_value=mock_client):
        # Should catch JSONDecodeError and safely fallback to heuristic
        result, model_used = service.classify(
            email_text="Patient had adverse reaction and fever."
        )

    assert result.primary_category == ClassificationCategory.ICSR
    assert "heuristic" in model_used


def test_classify_with_gemini_pydantic_validation_error_fallback():
    mock_client = MagicMock()
    mock_model_res = MagicMock()
    # Missing required keys like classifications
    mock_model_res.text = json.dumps({"primary_category": "INVALID"})
    mock_client.models.generate_content.return_value = mock_model_res

    service = AIService(api_key="test-mock-api-key")
    with patch("google.genai.Client", return_value=mock_client):
        result, model_used = service.classify(
            email_text="Damaged packaging and broken seal reported."
        )

    assert result.primary_category == ClassificationCategory.PQC
    assert "heuristic" in model_used


# =============================================================================
# 5. Database Storage & Endpoints Tests
# =============================================================================

def test_classify_and_store(db):
    # Create email in DB
    email = InboxRepository.create_email(
        db=db,
        sender="dr.watson@hospital.org",
        subject="Adverse Reaction Case",
        body="Patient John Doe reported hives and swelling after taking Med-A.",
    )

    service = AIService(api_key="")
    response = service.classify_and_store(
        db=db,
        email_id=email.id,
    )

    assert response.success is True
    assert response.primary_category == ClassificationCategory.ICSR
    assert len(response.classifications) >= 1

    # Verify classifications stored in DB
    db_classifications = db.query(Classification).filter(
        Classification.email_id == email.id
    ).all()
    assert len(db_classifications) >= 1
    assert db_classifications[0].category == "ICSR"
    assert db_classifications[0].confidence is not None
    assert db_classifications[0].reason is not None

    # Verify email status updated
    db.refresh(email)
    assert email.processing_status == ProcessingStatus.COMPLETED.value

    # Verify audit log created
    logs = db.query(AuditLog).filter(AuditLog.email_id == email.id).all()
    assert len(logs) >= 1
    assert logs[0].event == "AI_CLASSIFICATION_COMPLETED"


def test_post_classify_endpoint_inline_text(client: TestClient, db):
    payload = {
        "email_text": "What is the recommended pediatric dosage for Solution X?",
        "extracted_text": "",
    }
    response = client.post("/api/ai/classify", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["primary_category"] == "MI"
    assert len(data["classifications"]) >= 1
    assert data["classifications"][0]["category"] == "MI"
    assert "confidence" in data["classifications"][0]
    assert "reason" in data["classifications"][0]
    assert "summary" in data
    assert "processing_time" in data


def test_post_classify_preview_endpoint(client: TestClient):
    payload = {
        "email_text": "Product packaging was damaged and counterfeit seal was broken.",
        "extracted_text": "",
    }
    response = client.post("/api/ai/classify/preview", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["primary_category"] == "PQC"
    assert data["email_id"] is None
    assert any(c["category"] == "PQC" for c in data["classifications"])


def test_get_ai_status_endpoint(client: TestClient):
    response = client.get("/api/ai/status")
    assert response.status_code == 200
    data = response.json()

    assert data["service"] == "smart-inbox-ai-classifier"
    assert "gemini_available" in data
    assert "api_key_configured" in data
    assert "fallback_available" in data
    assert data["fallback_available"] is True


# =============================================================================
# 6. Extraction Tests (Schemas, Heuristic Fallbacks, Gemini Mocks, API Endpoints)
# =============================================================================

def test_extracted_field_defaults():
    field = ExtractedField()
    assert field.value == "Not stated"
    assert field.confidence == 0.0
    assert field.source_reference == "Not stated"

    # With non-empty text
    field2 = ExtractedField(value="54 years old", confidence=0.95, source_reference="PDF Page 1")
    assert field2.value == "54 years old"
    assert field2.confidence == 0.95
    assert field2.source_reference == "PDF Page 1"


def test_icsr_extraction_schemas():
    icsr = ICSRExtraction(
        patient=PatientInfo(
            age=ExtractedField(value="45", confidence=0.9, source_reference="PDF Page 1"),
            sex=ExtractedField(value="Female", confidence=0.9, source_reference="PDF Page 1"),
        ),
        reporter=ReporterInfo(
            name=ExtractedField(value="Dr. Emily Rose", confidence=0.95, source_reference="PDF Page 1"),
            role=ExtractedField(value="Physician", confidence=0.9, source_reference="PDF Page 1"),
        ),
        product=ProductInfo(
            name=ExtractedField(value="Drug X", confidence=0.95, source_reference="PDF Page 1"),
            dose=ExtractedField(value="50mg daily", confidence=0.9, source_reference="PDF Page 1"),
        ),
        reaction=ReactionInfo(
            reaction=ExtractedField(value="Anaphylaxis", confidence=0.98, source_reference="PDF Page 1"),
            outcome=ExtractedField(value="Recovered", confidence=0.85, source_reference="PDF Page 1"),
        ),
        severity=SeverityInfo(
            serious=ExtractedField(value="Yes", confidence=0.95, source_reference="PDF Page 1"),
            hospitalization=ExtractedField(value="Yes", confidence=0.9, source_reference="PDF Page 1"),
        ),
        narrative=NarrativeInfo(
            case_summary=ExtractedField(value="Patient experienced anaphylaxis after receiving Drug X.", confidence=0.9, source_reference="PDF Page 1"),
        ),
    )
    assert icsr.patient.age.value == "45"
    assert icsr.reporter.name.value == "Dr. Emily Rose"
    assert icsr.product.name.value == "Drug X"
    assert icsr.reaction.reaction.value == "Anaphylaxis"
    assert icsr.severity.serious.value == "Yes"
    # Unset fields default to Not stated
    assert icsr.patient.weight.value == "Not stated"
    assert icsr.patient.weight.confidence == 0.0


def test_pqc_and_mi_extraction_schemas():
    pqc = PQCExtraction(
        product=ExtractedField(value="Solution A", confidence=0.9, source_reference="Email body"),
        lot_number=ExtractedField(value="LOT-9921", confidence=0.95, source_reference="Email body"),
        problem=ExtractedField(value="Broken seal on vial", confidence=0.9, source_reference="Email body"),
        photo_mentioned=ExtractedField(value="Yes", confidence=0.85, source_reference="Email body"),
    )
    assert pqc.lot_number.value == "LOT-9921"
    assert pqc.problem.value == "Broken seal on vial"

    mi = MIExtraction(
        questions_asked=ExtractedField(value="What is the recommended titration for elderly patients?", confidence=0.9, source_reference="Email body"),
        product_topic=ExtractedField(value="Med-B", confidence=0.85, source_reference="Email body"),
    )
    assert "titration" in mi.questions_asked.value
    assert mi.product_topic.value == "Med-B"


def test_heuristic_icsr_extraction():
    service = AIService(api_key="")
    content = (
        "Patient is a 58 years old female, weight 65 kg, history: hypertension. "
        "Reported by Dr. Alan Grant, Physician in USA. "
        "Patient was taking Drug X 25mg daily orally started on 2026-01-10. "
        "Developed severe urticaria and bronchospasm. "
        "Hospitalization was required. Patient is recovering."
    )
    result, model = service._heuristic_fallback_extract(content, ClassificationCategory.ICSR)
    assert result.category == ClassificationCategory.ICSR
    assert result.icsr is not None
    assert result.icsr.patient.age.value == "58"
    assert result.icsr.patient.sex.value == "Female"
    assert "65 kg" in result.icsr.patient.weight.value
    assert "Alan Grant" in result.icsr.reporter.name.value
    assert result.icsr.reporter.role.value == "Physician"
    assert result.icsr.reporter.country.value == "USA"
    assert "Drug X" in result.icsr.product.name.value
    assert "25mg" in result.icsr.product.dose.value
    assert result.icsr.severity.serious.value == "Yes"
    assert result.icsr.severity.hospitalization.value == "Yes"
    assert result.facts_count > 5


def test_heuristic_pqc_extraction():
    service = AIService(api_key="")
    content = (
        "Complaint regarding Solution Z, lot number BATCH-8842. "
        "Observed broken seal and particulate contamination in vial. "
        "Attached image of the defective vial for review."
    )
    result, model = service._heuristic_fallback_extract(content, ClassificationCategory.PQC)
    assert result.category == ClassificationCategory.PQC
    assert result.pqc is not None
    assert result.pqc.lot_number.value == "BATCH-8842"
    assert "broken seal" in result.pqc.problem.value.lower() or "particulate" in result.pqc.problem.value.lower()
    assert result.pqc.photo_mentioned.value == "Yes"
    assert result.facts_count >= 3


def test_heuristic_mi_extraction():
    service = AIService(api_key="")
    content = (
        "Regarding product Med-Q: What is the recommended pediatric dosage and how to take it with food?"
    )
    result, model = service._heuristic_fallback_extract(content, ClassificationCategory.MI)
    assert result.category == ClassificationCategory.MI
    assert result.mi is not None
    assert "dosage" in result.mi.questions_asked.value.lower() or "how to take" in result.mi.questions_asked.value.lower()
    assert result.facts_count >= 1


def test_extract_with_gemini_mock_success():
    mock_gemini_response = {
        "category": "ICSR",
        "patient": {
            "age": {"value": "62", "confidence": 0.95, "source_reference": "PDF Page 1"},
            "sex": {"value": "Male", "confidence": 0.95, "source_reference": "PDF Page 1"},
            "weight": {"value": "80 kg", "confidence": 0.9, "source_reference": "PDF Page 1"},
            "height": {"value": "178 cm", "confidence": 0.9, "source_reference": "PDF Page 1"},
            "relevant_history": {"value": "Type 2 Diabetes", "confidence": 0.85, "source_reference": "PDF Page 1"},
        },
        "reporter": {
            "name": {"value": "Dr. Sarah Connor", "confidence": 0.98, "source_reference": "PDF Page 1"},
            "role": {"value": "Physician", "confidence": 0.95, "source_reference": "PDF Page 1"},
            "country": {"value": "USA", "confidence": 0.9, "source_reference": "PDF Page 1"},
        },
        "product": {
            "name": {"value": "CardioFix", "confidence": 0.98, "source_reference": "PDF Page 1"},
            "dose": {"value": "10mg once daily", "confidence": 0.95, "source_reference": "PDF Page 1"},
            "route": {"value": "Oral", "confidence": 0.9, "source_reference": "PDF Page 1"},
            "start_date": {"value": "2026-02-01", "confidence": 0.9, "source_reference": "PDF Page 1"},
            "stop_date": {"value": "2026-02-15", "confidence": 0.9, "source_reference": "PDF Page 1"},
        },
        "reaction": {
            "reaction": {"value": "Severe Angioedema and Dyspnea", "confidence": 0.98, "source_reference": "PDF Page 1"},
            "start_date": {"value": "2026-02-14", "confidence": 0.9, "source_reference": "PDF Page 1"},
            "outcome": {"value": "Recovered", "confidence": 0.9, "source_reference": "PDF Page 1"},
        },
        "severity": {
            "serious": {"value": "Yes", "confidence": 0.99, "source_reference": "PDF Page 1"},
            "death": {"value": "No", "confidence": 0.99, "source_reference": "PDF Page 1"},
            "hospitalization": {"value": "Yes", "confidence": 0.99, "source_reference": "PDF Page 1"},
            "life_threatening": {"value": "Yes", "confidence": 0.95, "source_reference": "PDF Page 1"},
            "other_severity": {"value": "ICU admission for airway monitoring", "confidence": 0.9, "source_reference": "PDF Page 1"},
        },
        "narrative": {
            "case_summary": {"value": "62-year-old male developed life-threatening angioedema after taking CardioFix requiring ICU admission.", "confidence": 0.95, "source_reference": "PDF Page 1"},
        },
        "summary": "Serious ICSR case with angioedema and hospitalization after CardioFix.",
    }

    mock_client = MagicMock()
    mock_model_res = MagicMock()
    mock_model_res.text = json.dumps(mock_gemini_response)
    mock_client.models.generate_content.return_value = mock_model_res

    service = AIService(api_key="mock-key")
    with patch("google.genai.Client", return_value=mock_client):
        result, model_used = service._extract_with_gemini("document text", ClassificationCategory.ICSR)

    assert result.category == ClassificationCategory.ICSR
    assert result.icsr.patient.age.value == "62"
    assert result.icsr.reporter.name.value == "Dr. Sarah Connor"
    assert result.icsr.product.name.value == "CardioFix"
    assert result.icsr.severity.hospitalization.value == "Yes"
    assert result.facts_count == 22


def test_extract_and_store_db_persistence(db):
    # 1. Create email and document
    email = InboxRepository.create_email(
        db=db,
        sender="clinic@health.net",
        subject="PQC Report",
        body="Complaint regarding broken seal on Drug Alpha, lot LOT-7731.",
    )
    doc = InboxRepository.create_document(
        db=db,
        email_id=email.id,
        filename="pqc_report.pdf",
        extracted_text="Defect report for Drug Alpha, lot LOT-7731. Observed cracked vial and broken seal. Photo attached.",
    )
    # Add classification
    InboxRepository.add_classification(
        db=db,
        document_id=doc.id,
        category="PQC",
        confidence=0.92,
        reason="Broken seal and cracked vial reported.",
    )

    service = AIService(api_key="")
    response = service.extract_and_store(
        db=db,
        document_id=doc.id,
    )

    assert response.success is True
    assert response.category == ClassificationCategory.PQC
    assert response.document_id == doc.id
    assert response.facts_stored >= 3

    # Check extracted facts in database
    facts = db.query(ExtractedFact).filter(ExtractedFact.document_id == doc.id).all()
    assert len(facts) >= 3
    fact_dict = {f.field_name: f.field_value for f in facts}
    assert "lot_number" in fact_dict
    assert "LOT-7731" in fact_dict["lot_number"]
    assert "photo_mentioned" in fact_dict

    # Check each fact has confidence and source_reference
    for f in facts:
        assert f.confidence is not None
        assert f.source_reference is not None


def test_post_extract_endpoint_success(client: TestClient, db):
    # Setup document in DB
    email = InboxRepository.create_email(
        db=db,
        sender="dr.smith@hospital.org",
        subject="Adverse Reaction Note",
        body="Patient Jane Doe, 45 years old female, experienced urticaria after receiving Vaccine X.",
    )
    doc = InboxRepository.create_document(
        db=db,
        email_id=email.id,
        filename="discharge_summary.pdf",
        extracted_text="Patient Jane Doe, 45 years old female. Developed severe urticaria and fever. Reported by Dr. Smith, Physician in USA.",
    )
    InboxRepository.add_classification(
        db=db,
        document_id=doc.id,
        category="ICSR",
        confidence=0.95,
        reason="Patient developed urticaria after medication.",
    )

    response = client.post(f"/api/ai/extract/{doc.id}")
    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["document_id"] == doc.id
    assert data["category"] == "ICSR"
    assert "extraction" in data
    assert "facts_stored" in data
    assert data["facts_stored"] > 0
    assert data["extraction"]["icsr"]["patient"]["age"]["value"] == "45"
    assert data["extraction"]["icsr"]["patient"]["sex"]["value"] == "Female"


def test_post_extract_endpoint_not_found(client: TestClient):
    response = client.post("/api/ai/extract/999999")
    assert response.status_code == 404


def test_get_extract_endpoint_success(client: TestClient, db: Session):
    email = InboxRepository.create_email(
        db=db,
        sender="dr.smith@hospital.org",
        subject="Adverse Event Case",
        body="Patient John Doe, 60 years old male. Developed severe headache after Drug Z.",
    )
    doc = InboxRepository.create_document(
        db=db,
        email_id=email.id,
        filename="case_report.pdf",
        extracted_text="Patient John Doe, 60 years old male. Developed severe headache after Drug Z.",
    )
    InboxRepository.add_classification(
        db=db,
        document_id=doc.id,
        category="ICSR",
        confidence=0.95,
        reason="Patient developed headache after drug.",
    )
    # First run extraction via POST
    post_res = client.post(f"/api/ai/extract/{doc.id}")
    assert post_res.status_code == 200

    # Now read facts back via GET
    get_res = client.get(f"/api/ai/extract/{doc.id}")
    assert get_res.status_code == 200
    data = get_res.json()

    assert "facts" in data
    assert "structured" in data
    assert data["facts_count"] > 0
    assert len(data["facts"]) >= data["facts_count"]

    # Verify structured reconstruction
    assert data["structured"] is not None
    assert "icsr" in data["structured"]
    icsr = data["structured"]["icsr"]
    assert icsr["patient"]["age"]["value"] == "60"
    assert icsr["patient"]["sex"]["value"] == "Male"


def test_get_extract_endpoint_with_category_filter(client: TestClient, db: Session):
    email = InboxRepository.create_email(
        db=db,
        sender="quality@pharma.com",
        subject="Product Complaint",
        body="Product: Aspirin 500mg. Lot Number: LOT12345. Broken seal observed.",
    )
    doc = InboxRepository.create_document(
        db=db,
        email_id=email.id,
        filename="pqc_complaint.pdf",
        extracted_text="Product: Aspirin 500mg. Lot Number: LOT12345. Broken seal observed.",
    )
    InboxRepository.add_classification(
        db=db,
        document_id=doc.id,
        category="PQC",
        confidence=0.92,
        reason="Product quality complaint.",
    )
    client.post(f"/api/ai/extract/{doc.id}")

    res = client.get(f"/api/ai/extract/{doc.id}?category=PQC")
    assert res.status_code == 200
    data = res.json()
    assert data["facts_count"] > 0
    assert all(f["category"] == "PQC" for f in data["facts"])


def test_get_extract_endpoint_not_found(client: TestClient):
    res = client.get("/api/ai/extract/999999")
    assert res.status_code == 404


def test_get_extract_endpoint_empty_facts(client: TestClient, db: Session):
    email = InboxRepository.create_email(
        db=db,
        sender="test@example.com",
        subject="Empty Doc",
        body="Empty test email",
    )
    doc = InboxRepository.create_document(
        db=db,
        email_id=email.id,
        filename="empty.pdf",
        extracted_text="",
    )
    res = client.get(f"/api/ai/extract/{doc.id}")
    assert res.status_code == 200
    data = res.json()
    assert data["facts_count"] == 0
    assert data["facts"] == []


