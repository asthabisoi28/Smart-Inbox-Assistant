from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, Float, ForeignKey
from sqlalchemy.orm import relationship

from app.db.base import Base


class ExtractedFact(Base):
    __tablename__ = "extracted_facts"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    category = Column(String(50), nullable=False, index=True)      # e.g., ICSR, PQC, MI
    field_name = Column(String(100), nullable=False, index=True)   # e.g., patient, reporter, product, batch_number, etc.
    field_value = Column(Text, nullable=False, default="Not stated")  # Default to "Not stated" when information is missing
    confidence = Column(Float, nullable=True)                      # e.g., 0.92
    source_type = Column(String(50), nullable=True)                # e.g., email_body, pdf_text, table, image_ocr
    source_reference = Column(Text, nullable=True)                 # Verifiable citation (page number, line, snippet)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    document = relationship("Document", back_populates="extracted_facts")

    def __repr__(self) -> str:
        return f"<ExtractedFact id={self.id} field='{self.field_name}' category='{self.category}'>"
