from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, Float, ForeignKey
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.models.enums import DocumentType, ProcessingStatus


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    email_id = Column(Integer, ForeignKey("emails.id", ondelete="CASCADE"), nullable=True, index=True)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=True)
    document_type = Column(String(50), default=DocumentType.PDF_DIGITAL.value, nullable=False)
    extracted_text = Column(Text, nullable=True)
    original_text = Column(Text, nullable=True)  # Untranslated raw text if non-English
    language = Column(String(50), nullable=True, default="en")
    ocr_confidence = Column(Float, nullable=True)  # OCR confidence score (0.0 - 1.0)
    tables_json = Column(Text, nullable=True)     # JSON structured tables
    images_json = Column(Text, nullable=True)     # JSON image metadata & descriptions
    processing_status = Column(String(50), default=ProcessingStatus.PENDING.value, nullable=False)
    review_status = Column(String(50), default="PENDING_REVIEW", nullable=False)
    processing_time = Column(Float, nullable=True)  # Duration in seconds
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    email = relationship("Email", back_populates="documents")
    classifications = relationship("Classification", back_populates="document", cascade="all, delete-orphan")
    extracted_facts = relationship("ExtractedFact", back_populates="document", cascade="all, delete-orphan")
    review_actions = relationship("ReviewAction", back_populates="document", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="document", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Document id={self.id} filename='{self.filename}' type='{self.document_type}' status='{self.processing_status}'>"
