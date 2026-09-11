import os
import json
import pytest
import fitz
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from PIL import Image, ImageDraw

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.repositories.inbox_repository import InboxRepository
from app.services.pdf_processing_service import PdfProcessingService
from app.models.enums import DocumentType, ProcessingStatus

TEST_STORAGE_DIR = Path(__file__).resolve().parent / "fixtures"
TEST_STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def create_digital_pdf(file_path: str) -> str:
    """Creates a standard digital PDF with plain text."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    text = (
        "INDIVIDUAL CASE SAFETY REPORT\n"
        "Patient ID: SYN-9021\n"
        "Age: 54 | Gender: Male\n"
        "Suspect Drug: CardioVax 20mg (Lot #CV-88219)\n"
        "Adverse Reaction: Acute bronchospasm and severe urticaria.\n"
        "Outcome: Recovered after emergency epinephrine administration."
    )
    page.insert_text((50, 72), text, fontsize=12)
    doc.save(file_path)
    doc.close()
    return file_path


def create_scanned_pdf(file_path: str) -> str:
    """Creates a scanned-like PDF containing a raster image with text."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)

    # Create an image containing text to simulate a scanned page
    img = Image.new("RGB", (600, 400), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((50, 50), "SCANNED CLINICAL NOTE: Patient experienced headache and nausea.", fill=(0, 0, 0))

    img_bytes_io = fitz.io.BytesIO()
    img.save(img_bytes_io, format="PNG")
    img_bytes = img_bytes_io.getvalue()

    page.insert_image(fitz.Rect(50, 50, 550, 450), stream=img_bytes)
    doc.save(file_path)
    doc.close()
    return file_path


def create_article_pdf(file_path: str) -> str:
    """Creates a multi-column published journal article PDF."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)

    header = "JOURNAL OF CLINICAL PHARMACOLOGY | DOI: 10.1002/jcph.2026 | Vol. 44\nAbstract: Evaluation of Adverse Drug Reactions."
    page.insert_text((50, 50), header, fontsize=11)

    left_col = (
        "Introduction\n"
        "Post-marketing surveillance is critical for detecting rare adverse events. "
        "We evaluated 500 patient cohorts receiving novel biologics."
    )
    page.insert_text((50, 120), left_col, fontsize=10)

    right_col = (
        "Results & Discussion\n"
        "Incidence of hypersensitivity was 0.04%. Early detection through automated "
        "triage algorithms significantly reduced reporting latency."
    )
    page.insert_text((320, 120), right_col, fontsize=10)

    doc.save(file_path)
    doc.close()
    return file_path


def create_non_english_pdf(file_path: str) -> str:
    """Creates a non-English (Spanish) medical report PDF."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    spanish_text = (
        "INFORME DE SEGURIDAD DEL PACIENTE\n"
        "El paciente de 45 anos presento una erupcion cutanea severa y fiebre alta "
        "despues de recibir la segunda dosis del medicamento. Se suspendio el tratamiento "
        "inmediatamente y se administro antihistaminico con recuperacion satisfactoria."
    )
    page.insert_text((50, 72), spanish_text, fontsize=12)
    doc.save(file_path)
    doc.close()
    return file_path


def test_digital_pdf_processing(db):
    pdf_path = str(TEST_STORAGE_DIR / "test_digital.pdf")
    create_digital_pdf(pdf_path)

    doc = InboxRepository.create_document(
        db=db,
        filename="test_digital.pdf",
        file_path=pdf_path,
        document_type=DocumentType.PDF_DIGITAL,
    )

    result = PdfProcessingService.process_pdf_document(db, doc.id)
    assert result["success"] is True
    assert result["document_type"] == "pdf_digital"
    assert "CardioVax" in result["extracted_text_preview"]

    # Verify DB state
    db.refresh(doc)
    assert doc.processing_status == "COMPLETED"
    assert doc.language == "en"
    assert doc.processing_time is not None


def test_scanned_pdf_detection_and_ocr(db):
    pdf_path = str(TEST_STORAGE_DIR / "test_scanned.pdf")
    create_scanned_pdf(pdf_path)

    doc = InboxRepository.create_document(
        db=db,
        filename="test_scanned.pdf",
        file_path=pdf_path,
        document_type=DocumentType.PDF_DIGITAL,
    )

    result = PdfProcessingService.process_pdf_document(db, doc.id)
    assert result["success"] is True
    assert result["document_type"] == "pdf_scanned"

    db.refresh(doc)
    assert doc.document_type == "pdf_scanned"
    assert doc.ocr_confidence is not None
    assert doc.ocr_confidence > 0.0


def test_published_article_layout(db):
    pdf_path = str(TEST_STORAGE_DIR / "test_article.pdf")
    create_article_pdf(pdf_path)

    doc = InboxRepository.create_document(
        db=db,
        filename="test_article.pdf",
        file_path=pdf_path,
        document_type=DocumentType.PDF_DIGITAL,
    )

    result = PdfProcessingService.process_pdf_document(db, doc.id)
    assert result["success"] is True
    assert result["document_type"] == "article"

    db.refresh(doc)
    assert doc.document_type == "article"
    assert "Introduction" in doc.extracted_text
    assert "Results & Discussion" in doc.extracted_text


def test_non_english_pdf_detection_and_preservation(db):
    pdf_path = str(TEST_STORAGE_DIR / "test_spanish.pdf")
    create_non_english_pdf(pdf_path)

    doc = InboxRepository.create_document(
        db=db,
        filename="test_spanish.pdf",
        file_path=pdf_path,
        document_type=DocumentType.PDF_DIGITAL,
    )

    result = PdfProcessingService.process_pdf_document(db, doc.id)
    assert result["success"] is True

    db.refresh(doc)
    assert doc.language == "es"
    assert doc.original_text is not None
    assert "erupcion cutanea" in doc.original_text
    assert "ES" in doc.extracted_text  # Contains original language marker reference


def create_multipage_pdf(file_path: str) -> str:
    """Creates a multi-page PDF with different content on each page."""
    doc = fitz.open()
    for i in range(3):
        page = doc.new_page(width=612, height=792)
        page.insert_text((50, 72), f"Page {i + 1} Content", fontsize=14)
        page.insert_text((50, 120), f"This is detailed content for page {i + 1} of the report.", fontsize=10)
    doc.save(file_path)
    doc.close()
    return file_path


def create_empty_text_pdf(file_path: str) -> str:
    """Creates a PDF with no extractable text (blank pages)."""
    doc = fitz.open()
    doc.new_page(width=612, height=792)
    doc.save(file_path)
    doc.close()
    return file_path


def create_french_pdf(file_path: str) -> str:
    """Creates a French medical report PDF."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    french_text = (
        "RAPPORT DE PHARMACOVIGILANCE\n"
        "Le patient a presente une reaction cutanee severe apres la prise du medicament. "
        "Le traitement a ete interrompu immediatement et un antihistaminique a ete administre."
    )
    page.insert_text((50, 72), french_text, fontsize=12)
    doc.save(file_path)
    doc.close()
    return file_path


def test_api_document_endpoints(db, client):
    pdf_path = str(TEST_STORAGE_DIR / "test_api_doc.pdf")
    create_digital_pdf(pdf_path)

    doc = InboxRepository.create_document(
        db=db,
        filename="test_api_doc.pdf",
        file_path=pdf_path,
        document_type=DocumentType.PDF_DIGITAL,
    )
    doc_id = doc.id

    # Process via API
    proc_res = client.post(f"/api/documents/{doc_id}/process")
    assert proc_res.status_code == 200
    data = proc_res.json()
    assert data["success"] is True
    assert data["document_id"] == doc_id

    # Retrieve Details via API
    get_res = client.get(f"/api/documents/{doc_id}")
    assert get_res.status_code == 200
    detail = get_res.json()
    assert detail["id"] == doc_id
    assert detail["processing_status"] == "COMPLETED"
    assert "CardioVax" in detail["extracted_text"]


def test_multipage_pdf_processing(db):
    pdf_path = str(TEST_STORAGE_DIR / "test_multipage.pdf")
    create_multipage_pdf(pdf_path)

    doc = InboxRepository.create_document(
        db=db,
        filename="test_multipage.pdf",
        file_path=pdf_path,
        document_type=DocumentType.PDF_DIGITAL,
    )

    result = PdfProcessingService.process_pdf_document(db, doc.id)
    assert result["success"] is True

    db.refresh(doc)
    assert doc.processing_status == "COMPLETED"
    assert "Page 1" in doc.extracted_text
    assert "Page 2" in doc.extracted_text
    assert "Page 3" in doc.extracted_text


def test_empty_text_pdf_processing(db):
    pdf_path = str(TEST_STORAGE_DIR / "test_empty.pdf")
    create_empty_text_pdf(pdf_path)

    doc = InboxRepository.create_document(
        db=db,
        filename="test_empty.pdf",
        file_path=pdf_path,
        document_type=DocumentType.PDF_DIGITAL,
    )

    result = PdfProcessingService.process_pdf_document(db, doc.id)
    assert result["success"] is True

    db.refresh(doc)
    assert doc.processing_status == "COMPLETED"


def test_french_pdf_detection(db):
    pdf_path = str(TEST_STORAGE_DIR / "test_french.pdf")
    create_french_pdf(pdf_path)

    doc = InboxRepository.create_document(
        db=db,
        filename="test_french.pdf",
        file_path=pdf_path,
        document_type=DocumentType.PDF_DIGITAL,
    )

    result = PdfProcessingService.process_pdf_document(db, doc.id)
    assert result["success"] is True

    db.refresh(doc)
    assert doc.language == "fr"
    assert doc.original_text is not None


def test_pdf_processing_result_has_required_keys(db):
    pdf_path = str(TEST_STORAGE_DIR / "test_keys.pdf")
    create_digital_pdf(pdf_path)

    doc = InboxRepository.create_document(
        db=db,
        filename="test_keys.pdf",
        file_path=pdf_path,
        document_type=DocumentType.PDF_DIGITAL,
    )

    result = PdfProcessingService.process_pdf_document(db, doc.id)
    assert "success" in result
    assert "document_type" in result
    assert "extracted_text_preview" in result
    assert result["success"] is True


def test_document_processing_status_persists(db):
    pdf_path = str(TEST_STORAGE_DIR / "test_status.pdf")
    create_digital_pdf(pdf_path)

    doc = InboxRepository.create_document(
        db=db,
        filename="test_status.pdf",
        file_path=pdf_path,
        document_type=DocumentType.PDF_DIGITAL,
    )

    PdfProcessingService.process_pdf_document(db, doc.id)

    db.refresh(doc)
    assert doc.processing_status == "COMPLETED"
    assert doc.processing_time is not None
    assert doc.processing_time > 0


def test_document_list_api_returns_all_types(db, client):
    digital_path = str(TEST_STORAGE_DIR / "test_list_digital.pdf")
    create_digital_pdf(digital_path)
    article_path = str(TEST_STORAGE_DIR / "test_list_article.pdf")
    create_article_pdf(article_path)

    InboxRepository.create_document(
        db=db, filename="list_digital.pdf", file_path=digital_path,
        document_type=DocumentType.PDF_DIGITAL, status=ProcessingStatus.COMPLETED,
    )
    InboxRepository.create_document(
        db=db, filename="list_article.pdf", file_path=article_path,
        document_type=DocumentType.ARTICLE, status=ProcessingStatus.COMPLETED,
    )

    response = client.get("/api/documents")
    assert response.status_code == 200
    docs = response.json()
    assert len(docs) >= 2
    types = {d["document_type"] for d in docs}
    assert "pdf_digital" in types or "article" in types
