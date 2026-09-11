from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship

from app.db.base import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    email_id = Column(Integer, ForeignKey("emails.id", ondelete="CASCADE"), nullable=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=True, index=True)
    event = Column(String(100), nullable=False, index=True)  # e.g., INGESTED, OCR_DONE, AI_CLASSIFIED, REVIEW_OVERRIDE
    details = Column(Text, nullable=True)                    # JSON string / structured details of event
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    email = relationship("Email", back_populates="audit_logs")
    document = relationship("Document", back_populates="audit_logs")

    def __repr__(self) -> str:
        return f"<AuditLog id={self.id} event='{self.event}' timestamp={self.timestamp}>"
