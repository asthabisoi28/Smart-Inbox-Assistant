import os
import email
import imaplib
import logging
import hashlib
from datetime import datetime
from email.header import decode_header
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.enums import DocumentType, ProcessingStatus
from app.models.email import Email
from app.models.document import Document
from app.repositories.inbox_repository import InboxRepository

logger = logging.getLogger(__name__)

# Base directory for storing downloaded attachments
ATTACHMENTS_DIR = Path(__file__).resolve().parent.parent.parent / "storage" / "attachments"
ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)


class EmailService:
    """Service responsible for IMAP email ingestion, parsing, duplicate prevention, and attachment management."""

    @staticmethod
    def _decode_mime_header(header_value: Optional[str]) -> str:
        """Decodes MIME encoded header strings (e.g. UTF-8 encoded subject)."""
        if not header_value:
            return ""
        decoded_parts = decode_header(header_value)
        result = []
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                try:
                    result.append(part.decode(encoding or "utf-8", errors="replace"))
                except Exception:
                    result.append(part.decode("latin-1", errors="replace"))
            else:
                result.append(str(part))
        return "".join(result).strip()

    @staticmethod
    def _extract_body_and_attachments(msg: email.message.Message) -> Tuple[str, List[Dict[str, Any]]]:
        """Extracts plain text body and identifies PDF and non-PDF attachments from an email message."""
        body_parts = []
        attachments = []

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))
                filename = part.get_filename()

                # If filename is present or it's marked as attachment
                if filename or "attachment" in content_disposition:
                    decoded_filename = EmailService._decode_mime_header(filename or "attachment.dat")
                    payload = part.get_payload(decode=True)
                    attachments.append({
                        "filename": decoded_filename,
                        "content_type": content_type,
                        "data": payload,
                    })
                elif content_type == "text/plain" and "attachment" not in content_disposition:
                    try:
                        charset = part.get_content_charset() or "utf-8"
                        body_parts.append(part.get_payload(decode=True).decode(charset, errors="replace"))
                    except Exception:
                        pass
                elif content_type == "text/html" and not body_parts and "attachment" not in content_disposition:
                    # Fallback to HTML if plain text isn't available yet
                    try:
                        charset = part.get_content_charset() or "utf-8"
                        raw_html = part.get_payload(decode=True).decode(charset, errors="replace")
                        body_parts.append(raw_html)
                    except Exception:
                        pass
        else:
            payload = msg.get_payload(decode=True)
            charset = msg.get_content_charset() or "utf-8"
            if payload:
                body_parts.append(payload.decode(charset, errors="replace"))

        body_text = "\n\n".join(body_parts).strip()
        return body_text, attachments

    @staticmethod
    def _generate_synthetic_pdf(title: str, content: str) -> bytes:
        """Generates a minimal valid PDF byte sequence for synthetic testing."""
        # Simple minimal PDF format for synthetic test cases
        pdf_data = (
            b"%PDF-1.4\n"
            b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
            b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
            b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> >> endobj\n"
            b"4 0 obj << /Length " + str(len(content) + 50).encode("utf-8") + b" >>\n"
            b"stream\n"
            b"BT /F1 12 Tf 50 750 Td (" + title.encode("latin-1", errors="replace") + b") Tj ET\n"
            b"BT /F1 10 Tf 50 720 Td (" + content[:500].encode("latin-1", errors="replace") + b") Tj ET\n"
            b"endstream\n"
            b"endobj\n"
            b"xref\n0 5\n0000000000 65535 f \n0000000010 00000 n \n0000000060 00000 n \n0000000117 00000 n \n0000000263 00000 n \n"
            b"trailer << /Size 5 /Root 1 0 R >>\nstartxref\n380\n%%EOF"
        )
        return pdf_data

    @staticmethod
    def save_attachment_file(filename: str, data: bytes, email_id: int) -> str:
        """Saves an attachment file to disk with a clean namespaced path."""
        safe_filename = "".join([c if c.isalnum() or c in "._-" else "_" for c in filename])
        timestamp_prefix = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        target_name = f"email_{email_id}_{timestamp_prefix}_{safe_filename}"
        target_path = ATTACHMENTS_DIR / target_name
        with open(target_path, "wb") as f:
            f.write(data)
        return str(target_path)

    @classmethod
    def ingest_single_email(
        cls,
        db: Session,
        sender: str,
        subject: str,
        received_date: datetime,
        body: str,
        message_id: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[Optional[Email], bool, str]:
        """
        Ingests a single parsed email.
        Returns (Email, is_new, message_or_reason).
        Prevents duplicates by checking message_id or deterministic hash.
        """
        # If message_id is absent, compute a deterministic fallback hash
        if not message_id:
            raw_hash = f"{sender}|{subject}|{received_date.isoformat()}|{body[:100]}"
            message_id = "<" + hashlib.sha256(raw_hash.encode("utf-8")).hexdigest()[:24] + "@synthetic.local>"

        # Check for duplicates
        existing = InboxRepository.get_email_by_message_id(db, message_id)
        if existing:
            InboxRepository.log_event(
                db=db,
                email_id=existing.id,
                event="EMAIL_DUPLICATE_IGNORED",
                details=f"Email with message_id '{message_id}' already ingested. Skipping duplicate.",
            )
            return existing, False, "Duplicate email detected - skipped."

        # Create email record
        email_record = InboxRepository.create_email(
            db=db,
            sender=sender,
            subject=subject,
            body=body,
            received_date=received_date,
            message_id=message_id,
            status=ProcessingStatus.PENDING,
        )

        InboxRepository.log_event(
            db=db,
            email_id=email_record.id,
            event="EMAIL_INGESTED",
            details=f"Ingested email from '{sender}' with subject '{subject}'. Message-ID: {message_id}",
        )

        # Process attachments
        if attachments:
            for att in attachments:
                filename = att.get("filename", "unknown_file")
                content_type = att.get("content_type", "")
                data = att.get("data", b"")
                is_pdf = filename.lower().endswith(".pdf") or "pdf" in content_type.lower()

                if is_pdf and data:
                    saved_path = cls.save_attachment_file(filename, data, email_record.id)
                    doc = InboxRepository.create_document(
                        db=db,
                        email_id=email_record.id,
                        filename=filename,
                        file_path=saved_path,
                        document_type=DocumentType.PDF_DIGITAL,
                        status=ProcessingStatus.PENDING,
                    )
                    InboxRepository.log_event(
                        db=db,
                        email_id=email_record.id,
                        document_id=doc.id,
                        event="PDF_ATTACHMENT_DETECTED",
                        details=f"Saved PDF attachment '{filename}' to disk ({len(data)} bytes).",
                    )
                else:
                    # Non-PDF attachments: log and do not queue as document for processing
                    InboxRepository.log_event(
                        db=db,
                        email_id=email_record.id,
                        event="NON_PDF_ATTACHMENT_IGNORED",
                        details=f"Ignored non-PDF attachment '{filename}' (type: {content_type}, size: {len(data) if data else 0} bytes).",
                    )

        return email_record, True, "Successfully ingested."

    @classmethod
    def sync_from_imap(cls, db: Session, max_emails: int = 20) -> Dict[str, Any]:
        """
        Connects to the configured IMAP mailbox, fetches unread/latest emails,
        and saves new ones to the database.
        """
        if not settings.IMAP_SERVER or not settings.IMAP_USERNAME or not settings.IMAP_PASSWORD:
            return {
                "success": False,
                "error": "IMAP credentials not configured. Please set IMAP_SERVER, IMAP_USERNAME, and IMAP_PASSWORD in .env.",
                "synced_count": 0,
                "skipped_count": 0,
            }

        synced_count = 0
        skipped_count = 0
        errors = []

        try:
            if settings.IMAP_USE_SSL:
                mail = imaplib.IMAP4_SSL(settings.IMAP_SERVER, settings.IMAP_PORT)
            else:
                mail = imaplib.IMAP4(settings.IMAP_SERVER, settings.IMAP_PORT)

            mail.login(settings.IMAP_USERNAME, settings.IMAP_PASSWORD)
            mail.select("INBOX")

            # Search for latest messages
            status, messages = mail.search(None, "ALL")
            if status != "OK" or not messages[0]:
                mail.logout()
                return {
                    "success": True,
                    "message": "Mailbox checked; no messages found.",
                    "synced_count": 0,
                    "skipped_count": 0,
                }

            email_ids = messages[0].split()
            # Process up to max_emails (latest first)
            selected_ids = email_ids[-max_emails:][::-1]

            for e_id in selected_ids:
                try:
                    res, data = mail.fetch(e_id, "(RFC822)")
                    if res != "OK" or not data or not data[0]:
                        continue

                    raw_email = data[0][1]
                    msg = email.message_from_bytes(raw_email)

                    sender = cls._decode_mime_header(msg.get("From", "Unknown Sender"))
                    subject = cls._decode_mime_header(msg.get("Subject", "(No Subject)"))
                    date_str = msg.get("Date")
                    try:
                        received_date = parsedate_to_datetime(date_str) if date_str else datetime.utcnow()
                    except Exception:
                        received_date = datetime.utcnow()

                    message_id = msg.get("Message-ID")
                    body, attachments = cls._extract_body_and_attachments(msg)

                    _, is_new, _ = cls.ingest_single_email(
                        db=db,
                        sender=sender,
                        subject=subject,
                        received_date=received_date,
                        body=body,
                        message_id=message_id,
                        attachments=attachments,
                    )

                    if is_new:
                        synced_count += 1
                    else:
                        skipped_count += 1

                except Exception as inner_err:
                    logger.error(f"Error parsing email id {e_id}: {inner_err}")
                    errors.append(str(inner_err))

            mail.logout()
            return {
                "success": True,
                "synced_count": synced_count,
                "skipped_count": skipped_count,
                "errors": errors,
            }

        except Exception as e:
            logger.error(f"Failed IMAP synchronization: {e}")
            return {
                "success": False,
                "error": str(e),
                "synced_count": synced_count,
                "skipped_count": skipped_count,
            }


