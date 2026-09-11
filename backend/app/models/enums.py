from enum import Enum


class ClassificationCategory(str, Enum):
    ICSR = "ICSR"                    # Individual Case Safety Report
    PQC = "PQC"                      # Product Quality Complaint
    MI = "MI"                        # Medical Information Request
    NOT_RELEVANT = "NOT_RELEVANT"    # Out of scope / spam / non-actionable


class ProcessingStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class DocumentType(str, Enum):
    PDF_DIGITAL = "pdf_digital"
    PDF_SCANNED = "pdf_scanned"
    EMAIL_BODY = "email_body"
    IMAGE = "image"
    ARTICLE = "article"


class ReviewActionType(str, Enum):
    ACCEPT = "ACCEPT"
    OVERRIDE = "OVERRIDE"
    REJECT = "REJECT"
    ESCALATE = "ESCALATE"


class FactSourceType(str, Enum):
    EMAIL_BODY = "email_body"
    PDF_TEXT = "pdf_text"
    TABLE = "table"
    IMAGE_OCR = "image_ocr"
