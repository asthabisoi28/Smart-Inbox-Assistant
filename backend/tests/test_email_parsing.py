"""
Tests for email parsing and ingestion edge cases.

Covers:
- MIME header decoding (UTF-8, Latin-1, encoded subjects)
- Body extraction from multipart and plain messages
- Attachment detection and filtering (PDF vs non-PDF)
- Message-ID generation for emails without Message-ID
- Duplicate prevention via hash fallback
- Empty and missing fields handling
- Special character handling in subjects and bodies
"""

import email
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.utils import format_datetime

import pytest
from fastapi.testclient import TestClient

from app.models.enums import ProcessingStatus, DocumentType
from app.models.email import Email
from app.models.document import Document
from app.models.audit_log import AuditLog
from app.repositories.inbox_repository import InboxRepository
from app.services.email_service import EmailService


class TestMimeHeaderDecoding:
    """Test MIME header decoding for various encodings."""

    def test_decode_ascii_header(self):
        result = EmailService._decode_mime_header("Simple Subject Line")
        assert result == "Simple Subject Line"

    def test_decode_empty_header(self):
        assert EmailService._decode_mime_header(None) == ""
        assert EmailService._decode_mime_header("") == ""

    def test_decode_utf8_encoded_header(self):
        raw_header = "=?UTF-8?Q?Reporte_de_Farmacovigilancia_=C3=9Anico?="
        result = EmailService._decode_mime_header(raw_header)
        assert "Farmacovigilancia" in result

    def test_decode_latin1_header(self):
        raw_header = "=?ISO-8859-1?Q?R=e9action_Adverse_Report?="
        result = EmailService._decode_mime_header(raw_header)
        assert "Adverse" in result

    def test_decode_already_plain_string(self):
        result = EmailService._decode_mime_header("Just a plain string")
        assert result == "Just a plain string"


class TestBodyExtraction:
    """Test email body extraction from various message structures."""

    def _make_plain_message(self, subject, body, sender="test@synthetic.local"):
        msg = MIMEMultipart()
        msg["From"] = sender
        msg["Subject"] = subject
        msg["Date"] = format_datetime(datetime(2026, 9, 1, 10, 0, 0))
        msg.attach(MIMEText(body, "plain", "utf-8"))
        return msg

    def _make_multipart_mixed(self, subject, body, pdf_data=b"fake pdf", pdf_name="doc.pdf"):
        msg = MIMEMultipart()
        msg["From"] = "sender@synthetic.local"
        msg["Subject"] = subject
        msg["Date"] = format_datetime(datetime(2026, 9, 1, 10, 0, 0))
        msg.attach(MIMEText(body, "plain", "utf-8"))
        part = MIMEApplication(pdf_data, _subtype="pdf")
        part.add_header("Content-Disposition", "attachment", filename=pdf_name)
        msg.attach(part)
        return msg

    def test_extract_body_from_plain_message(self):
        msg = self._make_plain_message("Test", "Hello World body text")
        body, attachments = EmailService._extract_body_and_attachments(msg)
        assert "Hello World" in body
        assert len(attachments) == 0

    def test_extract_body_and_pdf_attachment(self):
        msg = self._make_multipart_mixed("Report", "PDF attached", pdf_data=b"%PDF-1.4 fake")
        body, attachments = EmailService._extract_body_and_attachments(msg)
        assert "PDF attached" in body
        assert len(attachments) == 1
        assert attachments[0]["filename"] == "doc.pdf"

    def test_extract_non_pdf_attachment(self):
        msg = self._make_multipart_mixed(
            "Brochure", "See attached",
            pdf_data=b"PK fake docx",
            pdf_name="brochure.docx",
        )
        body, attachments = EmailService._extract_body_and_attachments(msg)
        assert len(attachments) == 1
        assert attachments[0]["filename"] == "brochure.docx"

    def test_extract_multiple_attachments(self):
        msg = MIMEMultipart()
        msg["From"] = "test@synthetic.local"
        msg["Subject"] = "Multi attachment"
        msg["Date"] = format_datetime(datetime(2026, 9, 1, 10, 0, 0))
        msg.attach(MIMEText("Body text", "plain", "utf-8"))
        for name in ["report.pdf", "photo.jpg", "data.xlsx"]:
            part = MIMEApplication(b"fake content", _subtype="octet-stream")
            part.add_header("Content-Disposition", "attachment", filename=name)
            msg.attach(part)
        body, attachments = EmailService._extract_body_and_attachments(msg)
        assert len(attachments) == 3
        filenames = [a["filename"] for a in attachments]
        assert "report.pdf" in filenames
        assert "photo.jpg" in filenames
        assert "data.xlsx" in filenames

    def test_extract_body_from_non_multipart(self):
        msg = MIMEText("Single part body", "plain", "utf-8")
        msg["From"] = "test@synthetic.local"
        body, attachments = EmailService._extract_body_and_attachments(msg)
        assert "Single part body" in body
        assert len(attachments) == 0


class TestEmailIngestion:
    """Test single email ingestion with various scenarios."""

    def test_ingest_basic_email(self, db):
        email_rec, is_new, msg = EmailService.ingest_single_email(
            db=db,
            sender="dr.test@synthetic.local",
            subject="Test Adverse Event",
            received_date=datetime(2026, 9, 1, 10, 0, 0),
            body="Patient experienced rash after medication.",
            message_id="<test-001@synthetic.local>",
        )
        assert is_new is True
        assert email_rec.sender == "dr.test@synthetic.local"
        assert email_rec.processing_status == "PENDING"

    def test_duplicate_prevention_by_message_id(self, db):
        EmailService.ingest_single_email(
            db=db,
            sender="dr.test@synthetic.local",
            subject="Duplicate Test",
            received_date=datetime(2026, 9, 1, 10, 0, 0),
            body="Body",
            message_id="<dup-001@synthetic.local>",
        )
        _, is_new, msg = EmailService.ingest_single_email(
            db=db,
            sender="dr.test@synthetic.local",
            subject="Duplicate Test",
            received_date=datetime(2026, 9, 1, 10, 0, 0),
            body="Body",
            message_id="<dup-001@synthetic.local>",
        )
        assert is_new is False
        assert "Duplicate" in msg

    def test_duplicate_prevention_by_hash(self, db):
        EmailService.ingest_single_email(
            db=db,
            sender="hash.test@synthetic.local",
            subject="Hash Dedup Test",
            received_date=datetime(2026, 9, 1, 10, 0, 0),
            body="Body for hash dedup",
        )
        _, is_new, _ = EmailService.ingest_single_email(
            db=db,
            sender="hash.test@synthetic.local",
            subject="Hash Dedup Test",
            received_date=datetime(2026, 9, 1, 10, 0, 0),
            body="Body for hash dedup",
        )
        assert is_new is False

    def test_different_messages_not_deduped(self, db):
        _, is_new1, _ = EmailService.ingest_single_email(
            db=db, sender="a@synthetic.local", subject="Subject A",
            received_date=datetime(2026, 9, 1), body="Body A",
        )
        _, is_new2, _ = EmailService.ingest_single_email(
            db=db, sender="b@synthetic.local", subject="Subject B",
            received_date=datetime(2026, 9, 1), body="Body B",
        )
        assert is_new1 is True
        assert is_new2 is True

    def test_pdf_attachment_creates_document(self, db):
        email_rec, is_new, _ = EmailService.ingest_single_email(
            db=db,
            sender="attach@synthetic.local",
            subject="PDF Test",
            received_date=datetime(2026, 9, 1),
            body="See attached PDF",
            message_id="<attach-pdf-001@synthetic.local>",
            attachments=[{
                "filename": "safety_report.pdf",
                "content_type": "application/pdf",
                "data": b"%PDF-1.4 fake",
            }],
        )
        assert is_new is True
        docs = InboxRepository.list_documents_by_email(db, email_rec.id)
        assert len(docs) == 1
        assert docs[0].filename == "safety_report.pdf"

    def test_non_pdf_attachment_creates_no_document(self, db):
        email_rec, _, _ = EmailService.ingest_single_email(
            db=db,
            sender="nonpdf@synthetic.local",
            subject="DOCX Test",
            received_date=datetime(2026, 9, 1),
            body="See attached",
            message_id="<nonpdf-001@synthetic.local>",
            attachments=[{
                "filename": "brochure.docx",
                "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "data": b"PK fake docx",
            }],
        )
        docs = InboxRepository.list_documents_by_email(db, email_rec.id)
        assert len(docs) == 0

    def test_duplicate_email_audit_logged(self, db):
        EmailService.ingest_single_email(
            db=db, sender="audit@synthetic.local", subject="Audit Test",
            received_date=datetime(2026, 9, 1), body="Body",
            message_id="<audit-dup-001@synthetic.local>",
        )
        EmailService.ingest_single_email(
            db=db, sender="audit@synthetic.local", subject="Audit Test",
            received_date=datetime(2026, 9, 1), body="Body",
            message_id="<audit-dup-001@synthetic.local>",
        )
        email_rec = InboxRepository.get_email_by_message_id(db, "<audit-dup-001@synthetic.local>")
        logs = InboxRepository.get_audit_logs(db, email_id=email_rec.id)
        assert any(l.event == "EMAIL_DUPLICATE_IGNORED" for l in logs)

    def test_ingest_email_with_special_characters(self, db):
        email_rec, is_new, _ = EmailService.ingest_single_email(
            db=db,
            sender="special@synthetic.local",
            subject="Report: Patient #12345 - Drug X (50mg) & Y!",
            received_date=datetime(2026, 9, 1),
            body="Line 1\nLine 2\n\nSpecial chars: @#$%^&*()",
            message_id="<special-chars-001@synthetic.local>",
        )
        assert is_new is True
        assert "&" in email_rec.subject
        assert "Line 1" in email_rec.body

    def test_ingest_email_with_empty_body(self, db):
        email_rec, is_new, _ = EmailService.ingest_single_email(
            db=db,
            sender="empty@synthetic.local",
            subject="Empty Body Email",
            received_date=datetime(2026, 9, 1),
            body="",
            message_id="<empty-body-001@synthetic.local>",
        )
        assert is_new is True
        assert email_rec.body == ""


class TestSyntheticTestEmails:
    """Test the mock ingestion endpoint that generates synthetic test data."""

    def test_mock_ingest_returns_five(self, client):
        response = client.post("/api/emails/mock-ingest")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["ingested_count"] == 5

    def test_mock_ingest_idempotent(self, client):
        client.post("/api/emails/mock-ingest")
        res2 = client.post("/api/emails/mock-ingest")
        assert res2.json()["ingested_count"] == 0
        assert res2.json()["skipped_count"] == 5

    def test_emails_list_returns_all(self, client):
        client.post("/api/emails/mock-ingest")
        response = client.get("/api/emails")
        emails = response.json()
        assert len(emails) == 5
        for e in emails:
            assert "sender" in e
            assert "subject" in e
            assert "body" in e

    def test_email_detail_includes_documents(self, client):
        client.post("/api/emails/mock-ingest")
        list_res = client.get("/api/emails")
        email_id = list_res.json()[0]["id"]
        detail = client.get(f"/api/emails/{email_id}")
        assert detail.status_code == 200
        assert "documents" in detail.json()

    def test_email_detail_not_found(self, client):
        response = client.get("/api/emails/999999")
        assert response.status_code == 404
