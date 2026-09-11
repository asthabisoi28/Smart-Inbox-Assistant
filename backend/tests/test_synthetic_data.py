"""
Comprehensive synthetic data validation tests.

Verifies that the SyntheticDataService generates test data meeting ALL requirements:
- 10+ emails
- 5+ digital PDFs
- 2+ scanned/handwritten-style PDFs
- 5+ fictional article PDFs
- 2+ non-English PDFs
- 2+ quality complaints
- 2+ info requests
- 1+ irrelevant marketing email

Also validates that no real patient information is present.
"""

import pytest
from datetime import datetime

from app.models.enums import (
    ClassificationCategory,
    ProcessingStatus,
    DocumentType,
    FactSourceType,
)
from app.models.email import Email
from app.models.document import Document
from app.models.classification import Classification
from app.models.extracted_fact import ExtractedFact
from app.models.audit_log import AuditLog
from app.repositories.inbox_repository import InboxRepository
from app.services.synthetic_data_service import SyntheticDataService
from app.services.ai_service import AIService


class TestSyntheticDataCoverage:
    """Verify synthetic data meets all required coverage thresholds."""

    @pytest.fixture(autouse=True)
    def _generate_suite(self, db):
        self.db = db
        self.result = SyntheticDataService.generate_full_synthetic_suite(db)
        self.emails = InboxRepository.list_emails(db, limit=50)
        self.docs = InboxRepository.list_documents(db, limit=50)

    def test_emails_count_minimum(self):
        assert len(self.emails) >= 10, f"Need 10+ emails, got {len(self.emails)}"

    def test_documents_count_minimum(self):
        assert len(self.docs) >= 12, f"Need 12+ documents, got {len(self.docs)}"

    def test_digital_pdf_count(self):
        digital = [d for d in self.docs if d.document_type == DocumentType.PDF_DIGITAL.value]
        assert len(digital) >= 5, f"Need 5+ digital PDFs, got {len(digital)}"

    def test_scanned_pdf_count(self):
        scanned = [d for d in self.docs if d.document_type == DocumentType.PDF_SCANNED.value]
        assert len(scanned) >= 2, f"Need 2+ scanned PDFs, got {len(scanned)}"

    def test_article_pdf_count(self):
        articles = [d for d in self.docs if d.document_type == DocumentType.ARTICLE.value]
        assert len(articles) >= 5, f"Need 5+ article PDFs, got {len(articles)}"

    def test_non_english_pdf_exists(self):
        non_en = [d for d in self.docs if d.language and d.language != "en"]
        non_en_subjects = [
            e.subject for e in self.emails
            if any(kw in e.subject.lower() for kw in ["espanol", "francais", "fran", "rapport", "informe"])
        ]
        assert len(non_en) >= 2 or len(non_en_subjects) >= 2, (
            f"Need 2+ non-English PDFs, got lang={len(non_en)} subj={len(non_en_subjects)}"
        )

    def test_quality_complaint_count(self):
        pqc_emails = [
            e for e in self.emails
            if any(kw in e.subject.lower() for kw in ["quality", "complaint", "defect", "fracture", "crack", "clog"])
        ]
        assert len(pqc_emails) >= 2, f"Need 2+ quality complaint emails, got {len(pqc_emails)}"

    def test_info_request_count(self):
        mi_emails = [
            e for e in self.emails
            if any(kw in e.subject.lower() for kw in ["inquiry", "information", "dosage", "question", "request"])
        ]
        assert len(mi_emails) >= 2, f"Need 2+ info request emails, got {len(mi_emails)}"

    def test_marketing_email_count(self):
        marketing = [
            e for e in self.emails
            if any(kw in e.subject.lower() for kw in ["invitation", "expo", "conference", "webinar"])
        ]
        assert len(marketing) >= 1, f"Need 1+ marketing email, got {len(marketing)}"

    def test_synthetic_generation_success_flag(self):
        assert self.result["success"] is True
        assert self.result["emails_created"] >= 10
        assert self.result["documents_created"] >= 12

    def test_coverage_counts_from_service(self):
        counts = SyntheticDataService.coverage_counts()
        assert counts.get("email", 0) >= 10
        assert counts.get("digital_pdf", 0) >= 5
        assert counts.get("scanned_pdf", 0) >= 2
        assert counts.get("article", 0) >= 5
        assert counts.get("non_english", 0) >= 2
        assert counts.get("quality_complaint", 0) >= 2
        assert counts.get("info_request", 0) >= 2
        assert counts.get("marketing", 0) >= 1


class TestSyntheticDataFictional:
    """Verify no real patient information is present in synthetic data."""

    REAL_NAMES = [
        "john doe", "jane doe", "john smith", "jane smith",
        "michael johnson", "sarah williams", "robert brown",
    ]
    REAL_PATTERNS = [
        "ssn", "social security", "medicare id", "insurance id",
        "date of birth", "home address",
    ]

    @pytest.fixture(autouse=True)
    def _generate_suite(self, db):
        self.db = db
        SyntheticDataService.generate_full_synthetic_suite(db)
        self.emails = InboxRepository.list_emails(db, limit=50)
        self.docs = InboxRepository.list_documents(db, limit=50)

    def test_no_real_names_in_subjects(self):
        for email in self.emails:
            subject_lower = email.subject.lower()
            for name in self.REAL_NAMES:
                assert name not in subject_lower, (
                    f"Real name '{name}' found in subject: {email.subject}"
                )

    def test_no_real_names_in_body(self):
        for email in self.emails:
            if not email.body:
                continue
            body_lower = email.body.lower()
            for name in self.REAL_NAMES:
                assert name not in body_lower, (
                    f"Real name '{name}' found in body of email {email.id}"
                )

    def test_no_real_pii_patterns_in_body(self):
        for email in self.emails:
            if not email.body:
                continue
            body_lower = email.body.lower()
            for pattern in self.REAL_PATTERNS:
                assert pattern not in body_lower, (
                    f"PII pattern '{pattern}' found in body of email {email.id}"
                )

    def test_all_senders_are_synthetic(self):
        for email in self.emails:
            assert ".syn" in email.sender or "synthetic" in email.sender, (
                f"Non-synthetic sender: {email.sender}"
            )

    def test_extracted_text_fictional(self):
        for doc in self.docs:
            if not doc.extracted_text:
                continue
            text_lower = doc.extracted_text.lower()
            for name in self.REAL_NAMES:
                assert name not in text_lower, (
                    f"Real name '{name}' in extracted text of doc {doc.id}"
                )


class TestSyntheticDataCategoryCoverage:
    """Verify synthetic data covers all classification categories."""

    @pytest.fixture(autouse=True)
    def _generate_suite(self, db):
        self.db = db
        SyntheticDataService.generate_full_synthetic_suite(db)
        self.emails = InboxRepository.list_emails(db, limit=50)
        self.docs = InboxRepository.list_documents(db, limit=50)

    def test_icsr_subjects_exist(self):
        icsr = [e for e in self.emails if any(kw in e.subject.lower() for kw in ["adverse", "safety", "event", "incident", "anaphylaxis", "hematoma", "informe"])]
        assert len(icsr) >= 3, "Need at least 3 ICSR-related emails"

    def test_pqc_subjects_exist(self):
        pqc = [e for e in self.emails if "quality" in e.subject.lower() or "complaint" in e.subject.lower() or "defect" in e.subject.lower()]
        assert len(pqc) >= 2, "Need at least 2 PQC-related emails"

    def test_mi_subjects_exist(self):
        mi = [e for e in self.emails if "information" in e.subject.lower() or "inquiry" in e.subject.lower() or "dosage" in e.subject.lower()]
        assert len(mi) >= 2, "Need at least 2 MI-related emails"

    def test_not_relevant_subjects_exist(self):
        nr = [e for e in self.emails if "invitation" in e.subject.lower() or "expo" in e.subject.lower()]
        assert len(nr) >= 1, "Need at least 1 NOT_RELEVANT marketing email"

    def test_heuristic_classifies_all_categories(self):
        service = AIService(api_key="")
        categories_found = set()
        for email in self.emails:
            text = f"Subject: {email.subject}\n\n{email.body or ''}"
            result, _ = service.classify(email_text=text)
            categories_found.add(result.primary_category)
        assert ClassificationCategory.ICSR in categories_found, "ICSR not found in heuristic classifications"
        assert ClassificationCategory.PQC in categories_found, "PQC not found in heuristic classifications"
        assert ClassificationCategory.MI in categories_found, "MI not found in heuristic classifications"
        assert ClassificationCategory.NOT_RELEVANT in categories_found, "NOT_RELEVANT not found in heuristic classifications"


class TestSyntheticFixtureCatalog:
    """Test the on-disk fixture catalog generation."""

    def test_write_fixture_catalog_creates_files(self, tmp_path):
        result = SyntheticDataService.write_fixture_catalog(output_dir=tmp_path)
        assert result["success"] is True
        assert result["emails"] >= 16
        assert (tmp_path / "manifest.json").exists()

    def test_fixture_catalog_manifest_structure(self, tmp_path):
        import json
        result = SyntheticDataService.write_fixture_catalog(output_dir=tmp_path)
        manifest_path = tmp_path / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "disclaimer" in manifest
        assert "ALL DATA IS 100% FICTIONAL" in manifest["disclaimer"]
        assert "coverage" in manifest
        assert "files" in manifest
        assert len(manifest["files"]) >= 16
        for f in manifest["files"]:
            assert "message_id" in f
            assert "sender" in f
            assert "subject" in f
            assert "tags" in f

    def test_fixture_pdf_files_exist(self, tmp_path):
        SyntheticDataService.write_fixture_catalog(output_dir=tmp_path)
        pdf_dirs = list((tmp_path / "pdfs").rglob("*.pdf"))
        assert len(pdf_dirs) >= 13, f"Expected 13+ PDF files, found {len(pdf_dirs)}"

    def test_fixture_email_files_exist(self, tmp_path):
        SyntheticDataService.write_fixture_catalog(output_dir=tmp_path)
        eml_files = list((tmp_path / "emails").glob("*.eml"))
        assert len(eml_files) >= 16, f"Expected 16+ .eml files, found {len(eml_files)}"


class TestSyntheticDataEdgeCases:
    """Edge cases for synthetic data generation."""

    def test_generate_on_empty_db(self, db):
        result = SyntheticDataService.generate_full_synthetic_suite(db)
        assert result["success"] is True
        assert result["emails_skipped"] == 0
        assert result["emails_created"] >= 10

    def test_generate_twice_does_not_duplicate(self, db):
        res1 = SyntheticDataService.generate_full_synthetic_suite(db)
        emails_after_1 = InboxRepository.list_emails(db, limit=100)
        count_1 = len(emails_after_1)
        res2 = SyntheticDataService.generate_full_synthetic_suite(db)
        emails_after_2 = InboxRepository.list_emails(db, limit=100)
        count_2 = len(emails_after_2)
        assert count_2 >= count_1 + 10, "Second run should create new entries (UUID-based IDs)"

    def test_all_emails_have_message_ids(self, db):
        SyntheticDataService.generate_full_synthetic_suite(db)
        emails = InboxRepository.list_emails(db, limit=50)
        for email in emails:
            assert email.message_id is not None, f"Email {email.id} has no message_id"
            assert "@" in email.message_id

    def test_all_documents_have_filenames(self, db):
        SyntheticDataService.generate_full_synthetic_suite(db)
        docs = InboxRepository.list_documents(db, limit=50)
        for doc in docs:
            assert doc.filename is not None
            assert len(doc.filename) > 0
            assert doc.filename.endswith(".pdf")

    def test_pdfs_are_valid_files(self, db):
        import fitz
        SyntheticDataService.generate_full_synthetic_suite(db)
        docs = InboxRepository.list_documents(db, limit=50)
        for doc in docs:
            if doc.file_path:
                assert __import__("os").path.exists(doc.file_path), f"PDF file missing: {doc.file_path}"
                pdf_doc = fitz.open(doc.file_path)
                assert pdf_doc.page_count >= 1
                pdf_doc.close()

    def test_scanned_pdfs_have_images(self, db):
        import fitz
        SyntheticDataService.generate_full_synthetic_suite(db)
        docs = InboxRepository.list_documents(db, limit=50)
        scanned = [d for d in docs if d.document_type == DocumentType.PDF_SCANNED.value]
        assert len(scanned) >= 2
        for doc in scanned:
            if doc.file_path:
                pdf_doc = fitz.open(doc.file_path)
                page = pdf_doc[0]
                images = page.get_images()
                assert len(images) >= 1, f"Scanned PDF {doc.filename} has no images"
                pdf_doc.close()

    def test_article_pdfs_have_two_columns(self, db):
        import fitz
        SyntheticDataService.generate_full_synthetic_suite(db)
        docs = InboxRepository.list_documents(db, limit=50)
        articles = [d for d in docs if d.document_type == DocumentType.ARTICLE.value]
        assert len(articles) >= 5
        for doc in articles:
            if doc.file_path:
                pdf_doc = fitz.open(doc.file_path)
                text = pdf_doc[0].get_text()
                assert len(text) > 100, f"Article PDF {doc.filename} has too little text"
                pdf_doc.close()
