"""
AI classification API router.

Endpoints:
  POST /api/ai/classify          — Classify a message; store result in DB.
  POST /api/ai/classify/preview  — Classify without storing (dry-run / preview).
  GET  /api/ai/status            — Check AI service availability.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.schemas.ai_schemas import (
    ClassifyRequest,
    ClassifyResponse,
    ClassificationResult,
    ExtractResponse,
    StoredFactsResponse,
)
from app.services.ai_service import ai_service, GENAI_AVAILABLE

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["AI Classification"])


# ─────────────────────────────────────────────────────────────────────────────
# Response schemas (local to this router)
# ─────────────────────────────────────────────────────────────────────────────

class AIStatusResponse(BaseModel):
    """Reports whether the Gemini AI backend is reachable and configured."""
    service: str
    gemini_available: bool
    api_key_configured: bool
    model: str
    fallback_available: bool
    status: str


class PreviewClassifyResponse(BaseModel):
    """
    Response for the dry-run preview endpoint.
    Identical to ClassifyResponse but never persists to the database.
    """
    success: bool
    primary_category: str
    classifications: list
    summary: str
    processing_time: float
    model_used: str
    error: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/ai/classify
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/classify",
    response_model=ClassifyResponse,
    status_code=status.HTTP_200_OK,
    summary="Classify a healthcare message",
    description=(
        "Classifies the supplied email body and/or extracted PDF text into one or "
        "more categories: ICSR (adverse event), PQC (quality complaint), MI (medical "
        "information request), or NOT_RELEVANT. Results are stored in the database "
        "and linked to the email / document record if IDs are provided."
    ),
    responses={
        200: {"description": "Classification completed successfully"},
        400: {"description": "Invalid request — no text or DB reference supplied"},
        422: {"description": "Request body validation error"},
        500: {"description": "Unexpected server error during classification"},
    },
)
def classify_message(
    payload: ClassifyRequest,
    db: Session = Depends(get_db),
) -> ClassifyResponse:
    """
    Classify a healthcare communication and store the result in the database.

    **Input** (at least one required):
    - `email_text` — raw email body text (inline)
    - `extracted_text` — extracted PDF/attachment text (inline)
    - `email_id` — ID of an email already in the database
    - `document_id` — ID of a document already in the database

    **Output:**
    - `primary_category` — highest-severity category
    - `classifications` — list of categories with confidence scores and reasons
    - `summary` — 1–2 sentence executive summary
    - `model_used` — "gemini-1.5-flash" or "heuristic-rule-engine-v1"

    **Classification categories:**
    | Category | Meaning |
    |---|---|
    | ICSR | Individual Case Safety Report (adverse event) |
    | PQC | Product Quality Complaint |
    | MI | Medical Information Request |
    | NOT_RELEVANT | Spam / marketing / internal admin |
    """
    try:
        response = ai_service.classify_and_store(
            db=db,
            email_id=payload.email_id,
            document_id=payload.document_id,
            email_text=payload.email_text,
            extracted_text=payload.extracted_text,
        )
        return response

    except ValueError as exc:
        # Configuration-level errors (missing key etc.) that should surface to the caller
        logger.error("Classification configuration error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error during classification: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "An unexpected error occurred during classification. "
                "Check server logs for details."
            ),
        ) from exc


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/ai/classify/preview  (dry-run — no DB writes)
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/classify/preview",
    response_model=ClassifyResponse,
    status_code=status.HTTP_200_OK,
    summary="Preview classification (dry-run, no DB storage)",
    description=(
        "Runs the same classification pipeline as /classify but does NOT store "
        "any results in the database. Useful for testing prompt quality or "
        "previewing how a message would be classified before ingestion."
    ),
)
def preview_classify(
    payload: ClassifyRequest,
) -> ClassifyResponse:
    """
    Classify without persisting to the database.

    Accepts the same payload as `/classify` but ignores `email_id` and
    `document_id` for storage purposes — only inline text is used.
    """
    import time
    start = time.monotonic()

    try:
        result, model_used = ai_service.classify(
            email_text=payload.email_text or "",
            extracted_text=payload.extracted_text or "",
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Preview classification error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Classification preview failed. Check server logs.",
        ) from exc

    elapsed = round(time.monotonic() - start, 3)

    return ClassifyResponse(
        success=True,
        email_id=None,
        document_id=None,
        primary_category=result.primary_category,
        classifications=result.classifications,
        summary=result.summary,
        processing_time=elapsed,
        model_used=model_used,
        error=None,
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/ai/status
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/status",
    response_model=AIStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="AI service status",
    description=(
        "Returns whether the Gemini API is configured and available. "
        "The heuristic fallback is always available."
    ),
)
def ai_status() -> AIStatusResponse:
    """Check the health and configuration of the AI classification backend."""
    api_key_configured = bool(settings.GEMINI_API_KEY)
    gemini_available = GENAI_AVAILABLE and api_key_configured

    return AIStatusResponse(
        service="smart-inbox-ai-classifier",
        gemini_available=gemini_available,
        api_key_configured=api_key_configured,
        model=settings.GEMINI_MODEL,
        fallback_available=True,
        status="ready" if gemini_available else "fallback-only",
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/ai/extract/{document_id}
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/extract/{document_id}",
    response_model=ExtractResponse,
    status_code=status.HTTP_200_OK,
    summary="Extract structured facts from a classified document",
    description=(
        "Extracts structured clinical safety (ICSR patient/reporter/product/reaction/severity/narrative), "
        "product quality (PQC product/lot/problem/photo), or medical inquiry (MI question/topic) facts "
        "from a document. Validates all fields using Pydantic, guarantees confidence scores and source "
        "citations, and persists extracted facts to the database."
    ),
    responses={
        200: {"description": "Fact extraction completed successfully"},
        400: {"description": "Bad request / extraction configuration error"},
        404: {"description": "Document not found in database"},
        500: {"description": "Unexpected error during extraction"},
    },
)
def extract_document_facts(
    document_id: int,
    category: Optional[str] = None,
    db: Session = Depends(get_db),
) -> ExtractResponse:
    """
    Extracts structured facts from a document and persists them to Oracle / SQLite.
    """
    try:
        response = ai_service.extract_and_store(
            db=db,
            document_id=document_id,
            category=category,
        )
        return response
    except ValueError as exc:
        logger.error("Extraction error for document %s: %s", document_id, exc)
        if "not found" in str(exc).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error during fact extraction: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error during fact extraction. Check server logs.",
        ) from exc

# ─────────────────────────────────────────────────────────────────────────────
# GET /api/ai/extract/{document_id}
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/extract/{document_id}",
    response_model=StoredFactsResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve previously extracted facts for a document",
    description=(
        "Returns all structured facts that were extracted and persisted for a document "
        "by a prior ``POST /api/ai/extract/{document_id}`` call. "
        "Includes both a flat row list and a typed nested structure (ICSR / PQC / MI). "
        "Pass ``?category=ICSR`` (or PQC / MI) to filter to a single category."
    ),
    responses={
        200: {"description": "Stored facts retrieved successfully"},
        404: {"description": "Document not found in database"},
        500: {"description": "Unexpected error during retrieval"},
    },
)
def get_extracted_facts(
    document_id: int,
    category: Optional[str] = None,
    db: Session = Depends(get_db),
) -> StoredFactsResponse:
    """
    Read back structured extraction facts stored in Oracle / SQLite.

    **Query parameters**:
    - ``category`` (optional) — filter by ``ICSR``, ``PQC``, or ``MI``.

    **Response fields**:
    - ``facts`` — flat list of every ``ExtractedFact`` row (id, field_name, value,
      confidence, source_type, source_reference, created_at).
    - ``structured`` — typed nested object (ICSRExtraction / PQCExtraction /
      MIExtraction) reconstructed from the stored rows.
    - ``facts_count`` — number of stated (non-'Not stated') facts.
    """
    try:
        response = ai_service.get_stored_facts(
            db=db,
            document_id=document_id,
            category=category,
        )
        return response
    except ValueError as exc:
        logger.error("get_stored_facts error for document %s: %s", document_id, exc)
        if "not found" in str(exc).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error reading stored facts: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error retrieving stored facts. Check server logs.",
        ) from exc
