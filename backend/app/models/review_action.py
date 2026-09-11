from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship

from app.db.base import Base


class ReviewAction(Base):
    __tablename__ = "review_actions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    email_id = Column(Integer, ForeignKey("emails.id", ondelete="CASCADE"), nullable=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=True, index=True)
    action = Column(String(50), nullable=False)          # ACCEPT, OVERRIDE, REJECT, ESCALATE
    reviewer = Column(String(100), nullable=False)       # Reviewer username / identity
    comments = Column(Text, nullable=True)               # Reviewer notes or rationale for override
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    email = relationship("Email", back_populates="review_actions")
    document = relationship("Document", back_populates="review_actions")

    def __repr__(self) -> str:
        return f"<ReviewAction id={self.id} reviewer='{self.reviewer}' action='{self.action}'>"
