from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.models.enums import ProcessingStatus


class Email(Base):
    __tablename__ = "emails"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    message_id = Column(String(255), unique=True, nullable=True, index=True)
    sender = Column(String(255), nullable=False, index=True)
    subject = Column(String(500), nullable=True)
    received_date = Column(DateTime, nullable=True)
    body = Column(Text, nullable=True)
    processing_status = Column(String(50), default=ProcessingStatus.PENDING.value, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    documents = relationship("Document", back_populates="email", cascade="all, delete-orphan")
    classifications = relationship("Classification", back_populates="email", cascade="all, delete-orphan")
    review_actions = relationship("ReviewAction", back_populates="email", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="email", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Email id={self.id} sender='{self.sender}' subject='{self.subject}' status='{self.processing_status}'>"
