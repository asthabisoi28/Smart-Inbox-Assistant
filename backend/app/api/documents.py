"""
Reviewer Dashboard and Document Processing API Router.

Endpoints:
  GET  /api/documents                       — List processed documents (with filters & pagination)
  GET  /api/documents/{id}                  — Get single document details
  GET  /api/documents/{id}/classifications  — Get classifications for a document
  GET  /api/documents/{id}/facts            — Get extracted facts for a document
  GET  /api/documents/{id}/audit            — Get processing and review audit history
  POST /api/documents/{id}/review/accept    — Reviewer accepts AI classification
  POST /api/documents/{id}/review/override  — Reviewer overrides AI classification
  PUT  /api/documents/{id}/facts            — Reviewer updates or adds extracted facts
  POST /api/documents/{id}/process          — Trigger PDF extraction pipeline
  POST /api/documents/process-pending       — Batch process all pending documents
"""

from datetime import datetime
import logging
from typing import List, Optional, Union
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.mock_data_service import get_all_documents, get_document_by_id
from app.models.enums import ClassificationCategory, ProcessingStatus, ReviewActionType, FactSourceType
from app.models.document import Document
from app.models.classification import Classification
from app.models.extracted_fact import ExtractedFact
from app.repositories.inbox_repository import InboxRepository
from app.services.pdf_processing_service import PdfProcessingService
from app.db.session import get_db
from app.schemas.reviewer_schemas import (
    DocumentListItemResponse,
    DocumentDetailResponse,
    ClassificationItemResponse,
    ExtractedFactItemResponse,
    UpdateFactsRequest,
    UpdateFactsResponse,
    AcceptReviewRequest,
    OverrideReviewRequest,
    ReviewResultResponse,
    DocumentAuditHistoryResponse,
    AuditLogItemResponse,
    ReviewActionItemResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["Reviewer Dashboard & Documents"])


# ─────────────────────────────────────────────────────────────────────────────
# Helper: Resolve Primary Category for a Document
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_document_primary_category(db: Session, doc: Document) -> Optional[str]:
    """Resolves primary classification category from document or parent email."""
    # Check document classifications
    doc_classifications = InboxRepository.get_classifications(db, document_id=doc.id)
    if doc_classifications:
        return doc_classifications[0].category
    # Fallback to parent email classifications
    if doc.email_id:
        email_classifications = InboxRepository.get_classifications(db, email_id=doc.email_id)
        if email_classifications:
            return email_classifications[0].category
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 1. GET /api/documents — List processed documents
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=List[DocumentListItemResponse],
    status_code=status.HTTP_200_OK,
    summary="List processed documents for reviewer dashboard",
    description="Lists documents with pagination and optional filtering by processing status and category.",
)
def list_documents(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=100, description="Max records to return"),
    status: Optional[str] = Query(None, description="Filter by processing status (PENDING, PROCESSING, COMPLETED, FAILED)"),
    category: Optional[str] = Query(None, description="Filter by classification category (ICSR, PQC, MI, NOT_RELEVANT)"),
    review_status: Optional[str] = Query(None, description="Filter by review status (PENDING_REVIEW, REVIEWED)"),
    db: Session = Depends(get_db),
) -> List[DocumentListItemResponse]:
    """Lists documents with summary metadata, classification status, and fact counts."""
    # If mock mode is enabled, bypass DB and return static mock data
    if settings.USE_MOCK_DATA:
        raw_docs = get_all_documents()
        # Apply pagination
        start = skip
        end = skip + limit
        raw_page = raw_docs[start:end]
        # Apply optional filters
        filtered = []
        for d in raw_page:
            if status and d.get("processing_status") != status:
                continue
            if category and d.get("primary_category") != category:
                continue
            filtered.append(DocumentListItemResponse(**d))
        return filtered
    # Normal DB path
    docs = InboxRepository.list_documents(db, skip=skip, limit=limit, status=status)
    results = []
    for doc in docs:
        primary_cat = _resolve_document_primary_category(db, doc)
        if category and primary_cat != category:
            continue
        if review_status and getattr(doc, 'review_status', None) != review_status:
            continue
        classifications = InboxRepository.get_classifications(db, document_id=doc.id)
        facts = InboxRepository.get_facts_by_document(db, document_id=doc.id)
        confidence_val = classifications[0].confidence if classifications else None
        subject_val = doc.email.subject if doc.email else None
        sender_val = doc.email.sender if doc.email else None
        received_date_val = doc.email.received_date if doc.email else None
        results.append(
            DocumentListItemResponse(
                id=doc.id,
                email_id=doc.email_id,
                filename=doc.filename,
                file_path=doc.file_path,
                document_type=doc.document_type,
                processing_status=doc.processing_status,
                language=doc.language,
                ocr_confidence=doc.ocr_confidence,
                processing_time=doc.processing_time,
                primary_category=primary_cat,
                confidence=confidence_val,
                subject=subject_val,
                sender=sender_val,
                received_date=received_date_val,
                classifications_count=len(classifications),
                facts_count=len(facts),
                review_status=getattr(doc, 'review_status', "PENDING_REVIEW"),
                created_at=doc.created_at,
            )
        )
    return results


# ─────────────────────────────────────────────────────────────────────────────
# 2. GET /api/documents/{document_id} — Get single document details
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/{document_id}",
    response_model=DocumentDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get document details",
    description="Retrieves full details of a single document including extracted text, language, OCR score, and status.",
)
def get_document_details(
    document_id: int,
    db: Session = Depends(get_db),
) -> DocumentDetailResponse:
    """Retrieves full document record with resolved primary category."""
    # Mock mode shortcut
    if settings.USE_MOCK_DATA:
        doc = get_document_by_id(document_id)
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document with ID {document_id} not found.",
            )
        # Return full detail response using mock dict (some fields may be missing)
        return DocumentDetailResponse(**doc)
    # Normal DB path
    doc = InboxRepository.get_document_by_id(db, document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} not found.",
        )
    primary_cat = _resolve_document_primary_category(db, doc)
    return DocumentDetailResponse(
    id=doc.id,
    email_id=doc.email_id,
    filename=doc.filename,
    file_path=doc.file_path,
    document_type=doc.document_type,
    extracted_text=doc.extracted_text,
    original_text=doc.original_text,
    language=doc.language,
    ocr_confidence=doc.ocr_confidence,
    tables_json=doc.tables_json,
    images_json=doc.images_json,
    processing_status=doc.processing_status,
    processing_time=doc.processing_time,
    primary_category=primary_cat,
    subject=doc.email.subject if doc.email else None,
    sender=doc.email.sender if doc.email else None,
    received_date=doc.email.received_date if doc.email else None,
    email_body=doc.email.body if doc.email else None,
    created_at=doc.created_at,
    
)


# ─────────────────────────────────────────────────────────────────────────────
# 3. GET /api/documents/{document_id}/classifications — Get classifications
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/{document_id}/classifications",
    response_model=List[ClassificationItemResponse],
    status_code=status.HTTP_200_OK,
    summary="Get document classifications",
    description="Retrieves all classifications associated with a document (and parent email if inherited).",
)
def get_document_classifications(
    document_id: int,
    db: Session = Depends(get_db),
) -> List[ClassificationItemResponse]:
    """Returns classifications list for the document."""
    doc = InboxRepository.get_document_by_id(db, document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} not found.",
        )

    classifications = InboxRepository.get_classifications(db, document_id=document_id)
    if not classifications and doc.email_id:
        classifications = InboxRepository.get_classifications(db, email_id=doc.email_id)

    return [
        ClassificationItemResponse(
            id=c.id,
            document_id=c.document_id,
            email_id=c.email_id,
            category=c.category,
            confidence=c.confidence,
            reason=c.reason,
            created_at=c.created_at,
        )
        for c in classifications
    ]


# ─────────────────────────────────────────────────────────────────────────────
# 4. GET /api/documents/{document_id}/facts — Get extracted facts
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/{document_id}/facts",
    response_model=List[ExtractedFactItemResponse],
    status_code=status.HTTP_200_OK,
    summary="Get extracted facts for a document",
    description="Returns all extracted clinical, quality, or medical inquiry facts for the document.",
)
def get_document_facts(
    document_id: int,
    category: Optional[str] = Query(None, description="Optional category filter (ICSR, PQC, MI)"),
    db: Session = Depends(get_db),
) -> List[ExtractedFactItemResponse]:
    """Returns extracted facts list for the document."""
    doc = InboxRepository.get_document_by_id(db, document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} not found.",
        )

    facts = InboxRepository.get_facts_by_document(db, document_id=document_id, category=category)
    return [
        ExtractedFactItemResponse(
            id=f.id,
            document_id=f.document_id,
            category=f.category,
            field_name=f.field_name,
            field_value=f.field_value,
            confidence=f.confidence,
            source_type=f.source_type,
            source_reference=f.source_reference,
            created_at=f.created_at,
        )
        for f in facts
    ]


# ─────────────────────────────────────────────────────────────────────────────
# 5. GET /api/documents/{document_id}/audit — Get processing & audit history
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/{document_id}/audit",
    response_model=DocumentAuditHistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get processing and review audit history",
    description="Retrieves timestamped audit logs and reviewer action history for the document.",
)
def get_document_audit_history(
    document_id: int,
    db: Session = Depends(get_db),
) -> DocumentAuditHistoryResponse:
    """Returns audit logs and reviewer actions associated with this document."""
    doc = InboxRepository.get_document_by_id(db, document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} not found.",
        )

    logs = InboxRepository.get_audit_logs(db, document_id=document_id)
    reviews = InboxRepository.get_review_history(db, document_id=document_id)

    # Also include parent email logs/reviews if linked
    if doc.email_id:
        email_logs = InboxRepository.get_audit_logs(db, email_id=doc.email_id)
        email_reviews = InboxRepository.get_review_history(db, email_id=doc.email_id)
        existing_log_ids = {l.id for l in logs}
        for el in email_logs:
            if el.id not in existing_log_ids:
                logs.append(el)
        existing_rev_ids = {r.id for r in reviews}
        for er in email_reviews:
            if er.id not in existing_rev_ids:
                reviews.append(er)

    # Sort descending by timestamp
    logs.sort(key=lambda x: x.timestamp, reverse=True)
    reviews.sort(key=lambda x: x.timestamp, reverse=True)

    return DocumentAuditHistoryResponse(
        document_id=document_id,
        audit_logs=[
            AuditLogItemResponse(
                id=l.id,
                email_id=l.email_id,
                document_id=l.document_id,
                event=l.event,
                details=l.details,
                timestamp=l.timestamp,
            )
            for l in logs
        ],
        review_actions=[
            ReviewActionItemResponse(
                id=r.id,
                email_id=r.email_id,
                document_id=r.document_id,
                action=r.action,
                reviewer=r.reviewer,
                comments=r.comments,
                timestamp=r.timestamp,
            )
            for r in reviews
        ],
    )


# ─────────────────────────────────────────────────────────────────────────────
# 6. POST /api/documents/{document_id}/review/accept — Accept AI result
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/{document_id}/review/accept",
    response_model=ReviewResultResponse,
    status_code=status.HTTP_200_OK,
    summary="Accept AI classification result",
    description="Reviewer approves and accepts the AI classification decision. Creates a timestamped review action and audit log.",
)
def accept_document_review(
    document_id: int,
    payload: AcceptReviewRequest,
    db: Session = Depends(get_db),
) -> ReviewResultResponse:
    """Records an ACCEPT review action and logs an audit trail event."""
    doc = InboxRepository.get_document_by_id(db, document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} not found.",
        )

    current_cat = _resolve_document_primary_category(db, doc)

    # 1. Record Review Action
    action = InboxRepository.record_review_action(
        db=db,
        reviewer=payload.reviewer,
        action=ReviewActionType.ACCEPT,
        comments=payload.comments,
        document_id=document_id,
        email_id=doc.email_id,
    )

    # 2. Log Audit Event
    # Update review status
    doc.review_status = "ACCEPTED"
    db.commit()
    db.refresh(doc)
    # Log audit event
    InboxRepository.log_event(
        db=db,
        document_id=document_id,
        email_id=doc.email_id,
        event="REVIEW_ACCEPTED",
        details=f"Reviewer '{payload.reviewer}' accepted classification '{current_cat or 'UNCLASSIFIED'}'. Comments: {payload.comments or 'None'}",
    )

    # 3. Update status
    InboxRepository.update_document_processing(
        db=db,
        document_id=document_id,
        status=ProcessingStatus.COMPLETED,
    )

    logger.info("Document %d review ACCEPTED by %s", document_id, payload.reviewer)

    return ReviewResultResponse(
        success=True,
        document_id=document_id,
        action="ACCEPT",
        reviewer=payload.reviewer,
        comments=payload.comments,
        current_category=current_cat,
        timestamp=action.timestamp,
        message="AI classification result accepted successfully.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# 7. POST /api/documents/{document_id}/review/override — Override AI result
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/{document_id}/review/override",
    response_model=ReviewResultResponse,
    status_code=status.HTTP_200_OK,
    summary="Override AI classification result",
    description="Reviewer overrides the AI classification with a new category. Creates a timestamped review action, updates classifications, and logs audit trail.",
)
def override_document_review(
    document_id: int,
    payload: OverrideReviewRequest,
    db: Session = Depends(get_db),
) -> ReviewResultResponse:
    """Overrides classification, persists new classification record, and writes audit logs."""
    doc = InboxRepository.get_document_by_id(db, document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} not found.",
        )

    old_cat = _resolve_document_primary_category(db, doc)

    # 1. Add overridden classification
    InboxRepository.add_classification(
        db=db,
        document_id=document_id,
        category=payload.new_category,
        confidence=1.0,  # Human verified
        reason=f"Manual override by {payload.reviewer}: {payload.reason}",
    )

    # 2. Record Review Action
    comment_text = f"Overridden to {payload.new_category.value}. Reason: {payload.reason}. Notes: {payload.comments or 'None'}"
    action = InboxRepository.record_review_action(
        db=db,
        reviewer=payload.reviewer,
        action=ReviewActionType.OVERRIDE,
        comments=comment_text,
        document_id=document_id,
        email_id=doc.email_id,
    )

    # 3. Log Audit Event
    # Update review status
    doc.review_status = "OVERRIDDEN"
    db.commit()
    db.refresh(doc)
    # Log audit event
    InboxRepository.log_event(
        db=db,
        document_id=document_id,
        email_id=doc.email_id,
        event="REVIEW_OVERRIDDEN",
        details=f"Reviewer '{payload.reviewer}' changed category from '{old_cat or 'UNCLASSIFIED'}' to '{payload.new_category.value}'. Reason: {payload.reason}",
    )

    logger.info("Document %d review OVERRIDDEN by %s to %s", document_id, payload.reviewer, payload.new_category.value)

    return ReviewResultResponse(
        success=True,
        document_id=document_id,
        action="OVERRIDE",
        reviewer=payload.reviewer,
        comments=comment_text,
        current_category=payload.new_category.value,
        timestamp=action.timestamp,
        message=f"Classification successfully overridden to {payload.new_category.value}.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# 8. PUT /api/documents/{document_id}/facts — Update extracted fields
# ─────────────────────────────────────────────────────────────────────────────

@router.put(
    "/{document_id}/facts",
    response_model=UpdateFactsResponse,
    status_code=status.HTTP_200_OK,
    summary="Update or add extracted facts for a document",
    description="Reviewer edits or adds extracted facts. Updates facts in database, creates a timestamped review action, and logs audit events.",
)
def update_document_facts(
    document_id: int,
    payload: UpdateFactsRequest,
    db: Session = Depends(get_db),
) -> UpdateFactsResponse:
    """Updates/upserts extracted facts and records review action."""
    doc = InboxRepository.get_document_by_id(db, document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} not found.",
        )

    doc_category = _resolve_document_primary_category(db, doc) or ClassificationCategory.ICSR.value
    updated_facts = []

    for item in payload.facts:
        fact_category = item.category.value if item.category else doc_category

        if item.id:
            # Update specific fact by ID
            fact = InboxRepository.update_extracted_fact(
                db=db,
                fact_id=item.id,
                field_value=item.field_value,
                confidence=item.confidence or 1.0,
                source_type=item.source_type or FactSourceType.EMAIL_BODY.value,
                source_reference=item.source_reference or "Reviewer edit",
            )
            if not fact:
                # If ID didn't match, upsert by field name
                fact = InboxRepository.upsert_extracted_fact(
                    db=db,
                    document_id=document_id,
                    field_name=item.field_name,
                    field_value=item.field_value,
                    category=fact_category,
                    confidence=item.confidence or 1.0,
                    source_type=item.source_type or FactSourceType.EMAIL_BODY.value,
                    source_reference=item.source_reference or "Reviewer edit",
                )
        else:
            # Upsert by document_id and field_name
            fact = InboxRepository.upsert_extracted_fact(
                db=db,
                document_id=document_id,
                field_name=item.field_name,
                field_value=item.field_value,
                category=fact_category,
                confidence=item.confidence or 1.0,
                source_type=item.source_type or FactSourceType.EMAIL_BODY.value,
                source_reference=item.source_reference or "Reviewer edit",
            )

        updated_facts.append(
            ExtractedFactItemResponse(
                id=fact.id,
                document_id=fact.document_id,
                category=fact.category,
                field_name=fact.field_name,
                field_value=fact.field_value,
                confidence=fact.confidence,
                source_type=fact.source_type,
                source_reference=fact.source_reference,
                created_at=fact.created_at,
            )
        )

    now = datetime.utcnow()
    # 1. Record Review Action
    InboxRepository.record_review_action(
        db=db,
        reviewer=payload.reviewer,
        action=ReviewActionType.OVERRIDE,
        comments=f"Updated {len(updated_facts)} fact(s). Notes: {payload.comments or 'None'}",
        document_id=document_id,
        email_id=doc.email_id,
    )

    # 2. Log Audit Event
    fields_summary = ", ".join(f"{f.field_name}='{f.field_value}'" for f in payload.facts[:5])
    if len(payload.facts) > 5:
        fields_summary += f" and {len(payload.facts) - 5} more"

    InboxRepository.log_event(
        db=db,
        document_id=document_id,
        email_id=doc.email_id,
        event="FACTS_UPDATED",
        details=f"Reviewer '{payload.reviewer}' modified {len(updated_facts)} fact(s): [{fields_summary}]. Notes: {payload.comments or 'None'}",
    )

    logger.info("Document %d facts (%d fields) updated by %s", document_id, len(updated_facts), payload.reviewer)

    return UpdateFactsResponse(
        success=True,
        document_id=document_id,
        reviewer=payload.reviewer,
        updated_count=len(updated_facts),
        facts=updated_facts,
        timestamp=now,
        message=f"Successfully updated {len(updated_facts)} extracted fact(s).",
    )


# ─────────────────────────────────────────────────────────────────────────────
# PDF Processing Trigger Endpoints (Existing)
# ─────────────────────────────────────────────────────────────────────────────

class ProcessDocumentResponse(DocumentListItemResponse):
    pass


class BatchProcessResponse(DocumentListItemResponse):
    pass


@router.post(
    "/{document_id}/process",
    status_code=status.HTTP_200_OK,
    summary="Trigger PDF extraction pipeline for a specific document",
)
def process_document(
    document_id: int,
    db: Session = Depends(get_db),
):
    """Triggers PDF extraction pipeline for a specific document."""
    doc = InboxRepository.get_document_by_id(db, document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} not found.",
        )

    result = PdfProcessingService.process_pdf_document(db, document_id)
    return result


@router.post(
    "/process-pending",
    status_code=status.HTTP_200_OK,
    summary="Batch process all pending documents in the queue",
)
def process_all_pending_documents(
    db: Session = Depends(get_db),
):
    """Processes all pending documents in the queue."""
    pending_docs = db.query(Document).filter(Document.processing_status == ProcessingStatus.PENDING.value).all()
    results = []
    successful = 0
    failed = 0

    for doc in pending_docs:
        res = PdfProcessingService.process_pdf_document(db, doc.id)
        results.append(res)
        if res.get("success"):
            successful += 1
        else:
            failed += 1

    return {
        "total_processed": len(pending_docs),
        "successful_count": successful,
        "failed_count": failed,
        "results": results,
    }
