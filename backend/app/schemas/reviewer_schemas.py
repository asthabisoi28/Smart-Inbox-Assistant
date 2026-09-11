"""
Pydantic schemas for reviewer dashboard APIs and document workflows.

Covers:
- Processed document listings and details
- Classifications query schemas
- Extracted facts query and update schemas
- Audit logs and review history schemas
- Reviewer actions: Accept, Override, Update Facts
"""

from datetime import datetime
from typing import List, Optional, Any
from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ClassificationCategory, ReviewActionType


# ─────────────────────────────────────────────────────────────────────────────
# Document Listing & Detail Schemas
# ─────────────────────────────────────────────────────────────────────────────

class DocumentListItemResponse(BaseModel):
    """Summarized document model for dashboard table views."""
    id: int
    email_id: Optional[int] = None
    filename: str
    file_path: Optional[str] = None
    document_type: str
    processing_status: str
    language: Optional[str] = "en"
    ocr_confidence: Optional[float] = None
    processing_time: Optional[float] = None
    primary_category: Optional[str] = None
    confidence: Optional[float] = None
    subject: Optional[str] = None
    sender: Optional[str] = None
    received_date: Optional[datetime] = None
    review_status: str = "PENDING_REVIEW"
    classifications_count: int = 0
    facts_count: int = 0
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentDetailResponse(BaseModel):
    """Full detail model for single document inspection."""
    id: int
    email_id: Optional[int] = None
    filename: str
    file_path: Optional[str] = None
    document_type: str
    extracted_text: Optional[str] = None
    original_text: Optional[str] = None
    language: Optional[str] = "en"
    ocr_confidence: Optional[float] = None
    tables_json: Optional[str] = None
    images_json: Optional[str] = None
    processing_status: str
    processing_time: Optional[float] = None
    primary_category: Optional[str] = None
    confidence: Optional[float] = None
    subject: Optional[str] = None
    sender: Optional[str] = None
    received_date: Optional[datetime] = None
    email_body: Optional[str] = None
    review_status: str = "PENDING_REVIEW"
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ─────────────────────────────────────────────────────────────────────────────
# Classifications Query Schema
# ─────────────────────────────────────────────────────────────────────────────

class ClassificationItemResponse(BaseModel):
    id: int
    document_id: Optional[int] = None
    email_id: Optional[int] = None
    category: str
    confidence: Optional[float] = None
    reason: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ─────────────────────────────────────────────────────────────────────────────
# Extracted Facts Query & Update Schemas
# ─────────────────────────────────────────────────────────────────────────────

class ExtractedFactItemResponse(BaseModel):
    id: int
    document_id: int
    category: str
    field_name: str
    field_value: str
    confidence: Optional[float] = None
    source_type: Optional[str] = None
    source_reference: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UpdateFactItem(BaseModel):
    id: Optional[int] = Field(None, description="Existing fact ID if updating a specific row")
    field_name: str = Field(..., min_length=1, description="Fact field name (e.g., 'patient.age', 'lot_number')")
    field_value: str = Field(..., description="New value for the field")
    category: Optional[ClassificationCategory] = Field(None, description="Category of the fact")
    confidence: Optional[float] = Field(1.0, ge=0.0, le=1.0, description="Confidence score")
    source_type: Optional[str] = Field("manual_review", description="Origin/source type")
    source_reference: Optional[str] = Field("Reviewer update", description="Citation / reference notes")


class UpdateFactsRequest(BaseModel):
    reviewer: str = Field(..., min_length=1, description="Username / identity of the reviewer")
    facts: List[UpdateFactItem] = Field(..., min_length=1, description="List of facts to update or add")
    comments: Optional[str] = Field(None, description="Optional notes regarding fact edits")


class UpdateFactsResponse(BaseModel):
    success: bool
    document_id: int
    reviewer: str
    updated_count: int
    facts: List[ExtractedFactItemResponse]
    timestamp: datetime
    message: str

    model_config = ConfigDict(from_attributes=True)


# ─────────────────────────────────────────────────────────────────────────────
# Review Actions (Accept / Override)
# ─────────────────────────────────────────────────────────────────────────────

class AcceptReviewRequest(BaseModel):
    reviewer: str = Field(..., min_length=1, description="Username / identity of the reviewer")
    comments: Optional[str] = Field(None, description="Optional feedback / sign-off notes")


class OverrideReviewRequest(BaseModel):
    reviewer: str = Field(..., min_length=1, description="Username / identity of the reviewer")
    new_category: ClassificationCategory = Field(..., description="Corrected category (ICSR, PQC, MI, NOT_RELEVANT)")
    reason: str = Field(..., min_length=2, description="Reason / rationale for the classification override")
    comments: Optional[str] = Field(None, description="Optional additional reviewer notes")


class ReviewResultResponse(BaseModel):
    success: bool
    document_id: int
    action: str
    reviewer: str
    comments: Optional[str] = None
    current_category: Optional[str] = None
    timestamp: datetime
    message: str

    model_config = ConfigDict(from_attributes=True)


# ─────────────────────────────────────────────────────────────────────────────
# Audit Logs & History Schemas
# ─────────────────────────────────────────────────────────────────────────────

class AuditLogItemResponse(BaseModel):
    id: int
    email_id: Optional[int] = None
    document_id: Optional[int] = None
    event: str
    details: Optional[str] = None
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


class ReviewActionItemResponse(BaseModel):
    id: int
    email_id: Optional[int] = None
    document_id: Optional[int] = None
    action: str
    reviewer: str
    comments: Optional[str] = None
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentAuditHistoryResponse(BaseModel):
    document_id: int
    audit_logs: List[AuditLogItemResponse]
    review_actions: List[ReviewActionItemResponse]

    model_config = ConfigDict(from_attributes=True)
