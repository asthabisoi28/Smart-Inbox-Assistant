from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, Float, ForeignKey
from sqlalchemy.orm import relationship

from app.db.base import Base


class Classification(Base):
    __tablename__ = "classifications"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    email_id = Column(Integer, ForeignKey("emails.id", ondelete="CASCADE"), nullable=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=True, index=True)
    category = Column(String(50), nullable=False, index=True)  # ICSR, PQC, MI, NOT_RELEVANT
    confidence = Column(Float, nullable=True)                  # e.g., 0.95 (95%)
    reason = Column(Text, nullable=True)                       # One-line explanation for classification
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    email = relationship("Email", back_populates="classifications")
    document = relationship("Document", back_populates="classifications")

    def __repr__(self) -> str:
        return f"<Classification id={self.id} category='{self.category}' confidence={self.confidence}>"
