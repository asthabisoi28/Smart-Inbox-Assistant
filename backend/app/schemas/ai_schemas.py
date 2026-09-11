"""
Pydantic schemas for the AI classification service.

Design rules:
- ClassificationItem validates every field strictly so bad AI output is caught early.
- ClassificationResult enforces at least one classification and a valid primary_category.
- ClassifyRequest/Response are the API-level contracts.
- AIErrorDetail captures structured error info when the AI returns invalid JSON.
- StoredFactItem / StoredFactsResponse expose persisted extraction rows via GET.
"""

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator

from app.models.enums import ClassificationCategory


# ---------------------------------------------------------------------------
# Core classification item — one category with confidence + reason
# ---------------------------------------------------------------------------
class ClassificationItem(BaseModel):
    category: ClassificationCategory = Field(
        ...,
        description="The assigned classification category: ICSR, PQC, MI, or NOT_RELEVANT",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score in the range [0.0, 1.0]",
    )
    reason: str = Field(
        ...,
        min_length=5,
        description="Concise one-sentence justification based strictly on evidence in the text",
    )

    @field_validator("reason")
    @classmethod
    def reason_not_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("reason must not be blank")
        return stripped

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        """Accept integers (0 or 1) from the model and clamp to valid range."""
        val = float(v)
        return max(0.0, min(1.0, val))

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# The full classification result returned by the AI (or heuristic engine)
# ---------------------------------------------------------------------------
class ClassificationResult(BaseModel):
    classifications: List[ClassificationItem] = Field(
        ...,
        min_length=1,
        description="List of one or more classifications assigned to the document",
    )
    primary_category: ClassificationCategory = Field(
        ...,
        description="Highest-severity category among all classifications",
    )
    summary: str = Field(
        ...,
        min_length=10,
        description="1–2 sentence executive summary of the document and its classification",
    )

    @model_validator(mode="after")
    def primary_must_be_in_classifications(self) -> "ClassificationResult":
        """
        Ensures primary_category actually appears in the classifications list.
        If the AI returns a primary that doesn't match any item, we pick the
        highest-severity one from the list instead of raising an error.
        """
        category_priority = [
            ClassificationCategory.ICSR,
            ClassificationCategory.PQC,
            ClassificationCategory.MI,
            ClassificationCategory.NOT_RELEVANT,
        ]
        present_categories = {item.category for item in self.classifications}
        if self.primary_category not in present_categories:
            # Auto-correct: pick the highest-priority category present
            for cat in category_priority:
                if cat in present_categories:
                    self.primary_category = cat
                    break
        return self

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# API request / response schemas
# ---------------------------------------------------------------------------
class ClassifyRequest(BaseModel):
    """Input payload for POST /api/ai/classify."""
    email_id: Optional[int] = Field(
        None,
        description="Optional ID of an email already stored in the database. "
                    "If supplied without email_text, the body is loaded from the DB.",
    )
    document_id: Optional[int] = Field(
        None,
        description="Optional ID of an attached document in the database. "
                    "If supplied without extracted_text, the text is loaded from the DB.",
    )
    email_text: Optional[str] = Field(
        None,
        description="Raw email body text to classify (inline — not loaded from DB).",
    )
    extracted_text: Optional[str] = Field(
        None,
        description="Extracted PDF / attachment text if available (inline).",
    )

    @model_validator(mode="after")
    def at_least_one_source(self) -> "ClassifyRequest":
        """Require at least one text source or database reference."""
        has_text = bool((self.email_text or "").strip() or (self.extracted_text or "").strip())
        has_ref = self.email_id is not None or self.document_id is not None
        if not has_text and not has_ref:
            raise ValueError(
                "Provide at least one of: email_text, extracted_text, email_id, or document_id."
            )
        return self


class ClassifyResponse(BaseModel):
    """Response payload for POST /api/ai/classify."""
    success: bool = Field(..., description="True if classification completed without fatal error")
    email_id: Optional[int] = Field(None, description="Database ID of the classified email")
    document_id: Optional[int] = Field(None, description="Database ID of the classified document")
    primary_category: ClassificationCategory = Field(
        ..., description="Highest-priority classification category"
    )
    classifications: List[ClassificationItem] = Field(
        ..., description="All classification items with confidence and reason"
    )
    summary: str = Field(..., description="Executive summary of the classification decision")
    processing_time: float = Field(..., description="Wall-clock time in seconds")
    model_used: str = Field(..., description="AI model or engine that produced the result")
    error: Optional[str] = Field(
        None,
        description="Non-null when a recoverable error occurred (e.g. AI returned invalid JSON "
                    "and the heuristic fallback was used instead)",
    )

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Structured error detail for AI JSON parse failures
# ---------------------------------------------------------------------------
class AIParseError(BaseModel):
    """Captures details of an AI response that failed Pydantic validation."""
    raw_response: str = Field(..., description="The raw string returned by the AI model")
    parse_error: str = Field(..., description="The validation / JSON error message")
    fallback_used: bool = Field(
        default=True,
        description="True when the heuristic fallback classifier was invoked after this failure",
    )


# ---------------------------------------------------------------------------
# Extraction Schemas (ICSR, PQC, MI)
# ---------------------------------------------------------------------------

class ExtractedField(BaseModel):
    """
    Unified container for each extracted fact field.
    Guarantees a value, confidence score [0.0, 1.0], and source reference.
    """
    value: str = Field(
        default="Not stated",
        description="Extracted value or 'Not stated' if absent in text",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence score in the range [0.0, 1.0]",
    )
    source_reference: str = Field(
        default="Not stated",
        description="Specific citation identifying email body or PDF page (e.g. 'Email body', 'PDF Page 1')",
    )

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, v) -> float:
        try:
            val = float(v)
            return max(0.0, min(1.0, val))
        except (TypeError, ValueError):
            return 0.0

    @field_validator("value", "source_reference", mode="before")
    @classmethod
    def clean_text_field(cls, v) -> str:
        if v is None:
            return "Not stated"
        s = str(v).strip()
        return s if s else "Not stated"

    model_config = ConfigDict(from_attributes=True)


class PatientInfo(BaseModel):
    age: ExtractedField = Field(default_factory=ExtractedField)
    sex: ExtractedField = Field(default_factory=ExtractedField)
    weight: ExtractedField = Field(default_factory=ExtractedField)
    height: ExtractedField = Field(default_factory=ExtractedField)
    relevant_history: ExtractedField = Field(default_factory=ExtractedField)

    model_config = ConfigDict(from_attributes=True)


class ReporterInfo(BaseModel):
    name: ExtractedField = Field(default_factory=ExtractedField)
    role: ExtractedField = Field(default_factory=ExtractedField)
    country: ExtractedField = Field(default_factory=ExtractedField)

    model_config = ConfigDict(from_attributes=True)


class ProductInfo(BaseModel):
    name: ExtractedField = Field(default_factory=ExtractedField)
    dose: ExtractedField = Field(default_factory=ExtractedField)
    route: ExtractedField = Field(default_factory=ExtractedField)
    start_date: ExtractedField = Field(default_factory=ExtractedField)
    stop_date: ExtractedField = Field(default_factory=ExtractedField)

    model_config = ConfigDict(from_attributes=True)


class ReactionInfo(BaseModel):
    reaction: ExtractedField = Field(default_factory=ExtractedField)
    start_date: ExtractedField = Field(default_factory=ExtractedField)
    outcome: ExtractedField = Field(default_factory=ExtractedField)

    model_config = ConfigDict(from_attributes=True)


class SeverityInfo(BaseModel):
    serious: ExtractedField = Field(default_factory=ExtractedField)
    death: ExtractedField = Field(default_factory=ExtractedField)
    hospitalization: ExtractedField = Field(default_factory=ExtractedField)
    life_threatening: ExtractedField = Field(default_factory=ExtractedField)
    other_severity: ExtractedField = Field(default_factory=ExtractedField)

    model_config = ConfigDict(from_attributes=True)


class NarrativeInfo(BaseModel):
    case_summary: ExtractedField = Field(default_factory=ExtractedField)

    model_config = ConfigDict(from_attributes=True)


class ICSRExtraction(BaseModel):
    patient: PatientInfo = Field(default_factory=PatientInfo)
    reporter: ReporterInfo = Field(default_factory=ReporterInfo)
    product: ProductInfo = Field(default_factory=ProductInfo)
    reaction: ReactionInfo = Field(default_factory=ReactionInfo)
    severity: SeverityInfo = Field(default_factory=SeverityInfo)
    narrative: NarrativeInfo = Field(default_factory=NarrativeInfo)

    model_config = ConfigDict(from_attributes=True)


class PQCExtraction(BaseModel):
    product: ExtractedField = Field(default_factory=ExtractedField)
    lot_number: ExtractedField = Field(default_factory=ExtractedField)
    problem: ExtractedField = Field(default_factory=ExtractedField)
    photo_mentioned: ExtractedField = Field(default_factory=ExtractedField)

    model_config = ConfigDict(from_attributes=True)


class MIExtraction(BaseModel):
    questions_asked: ExtractedField = Field(default_factory=ExtractedField)
    product_topic: ExtractedField = Field(default_factory=ExtractedField)

    model_config = ConfigDict(from_attributes=True)


class ExtractionResult(BaseModel):
    category: ClassificationCategory = Field(
        ...,
        description="Category for which facts were extracted: ICSR, PQC, MI, or NOT_RELEVANT",
    )
    icsr: Optional[ICSRExtraction] = Field(None, description="Extracted facts if category is ICSR")
    pqc: Optional[PQCExtraction] = Field(None, description="Extracted facts if category is PQC")
    mi: Optional[MIExtraction] = Field(None, description="Extracted facts if category is MI")
    facts_count: int = Field(0, description="Total count of stated facts extracted")
    summary: str = Field(default="", description="Executive summary of the extraction")

    model_config = ConfigDict(from_attributes=True)


class ExtractResponse(BaseModel):
    """Response payload for POST /api/ai/extract/{document_id}."""
    success: bool = Field(..., description="True if extraction completed without fatal error")
    document_id: int = Field(..., description="Database ID of the extracted document")
    category: ClassificationCategory = Field(..., description="Category used for extraction")
    extraction: ExtractionResult = Field(..., description="Structured extracted facts")
    facts_stored: int = Field(..., description="Total number of discrete facts stored in database")
    processing_time: float = Field(..., description="Wall-clock time in seconds")
    model_used: str = Field(..., description="AI model or engine used for extraction")
    error: Optional[str] = Field(None, description="Recoverable error message if any")

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Stored Facts GET response schemas
# ---------------------------------------------------------------------------

class StoredFactItem(BaseModel):
    """
    A single extracted fact row as persisted in the ``extracted_facts`` table.
    Returned by ``GET /api/ai/extract/{document_id}``.
    """
    id: int = Field(..., description="Primary key of the extracted_fact row")
    document_id: int = Field(..., description="Foreign key to the parent document")
    category: str = Field(..., description="Extraction category: ICSR, PQC, or MI")
    field_name: str = Field(
        ...,
        description="Dotted field path, e.g. 'patient.age', 'lot_number'",
    )
    field_value: str = Field(
        default="Not stated",
        description="Extracted value or 'Not stated' if absent in source",
    )
    confidence: Optional[float] = Field(
        None,
        description="Confidence score [0.0, 1.0]; None if not recorded",
    )
    source_type: Optional[str] = Field(
        None,
        description="Source medium: email_body, pdf_text, table, image_ocr",
    )
    source_reference: Optional[str] = Field(
        None,
        description="Specific citation e.g. 'Email body', 'PDF Page 2'",
    )
    created_at: datetime = Field(..., description="UTC timestamp when fact was stored")

    model_config = ConfigDict(from_attributes=True)


class StoredFactsResponse(BaseModel):
    """
    Response for ``GET /api/ai/extract/{document_id}``.

    Returns:
    - ``facts``: flat list of all stored ``ExtractedFact`` rows.
    - ``structured``: reconstructed typed extraction object (ICSR / PQC / MI)
      built from the flat rows — mirrors the shape of ``ExtractionResult``.
    - ``facts_count``: total number of stated (non-'Not stated') facts.
    """
    document_id: int = Field(..., description="Database ID of the document")
    category: Optional[str] = Field(
        None,
        description="Category filter applied; None means all categories returned",
    )
    facts: List[StoredFactItem] = Field(
        default_factory=list,
        description="Flat list of every stored fact row for this document",
    )
    structured: Optional[ExtractionResult] = Field(
        None,
        description=(
            "Typed extraction object reconstructed from stored fact rows. "
            "Populated only when all facts belong to a single recognised category."
        ),
    )
    facts_count: int = Field(
        0,
        description="Total stated facts (value != 'Not stated') in this response",
    )
    model_used: Optional[str] = Field(
        None,
        description="AI model or heuristic engine that originally produced these facts",
    )

    model_config = ConfigDict(from_attributes=True)
