from datetime import datetime
from typing import List, Optional, Union
from sqlalchemy.orm import Session, joinedload


from sqlalchemy import desc

from app.models.email import Email
from app.models.document import Document
from app.models.classification import Classification
from app.models.extracted_fact import ExtractedFact
from app.models.review_action import ReviewAction
from app.models.audit_log import AuditLog
from app.models.enums import (
    ClassificationCategory,
    ProcessingStatus,
    DocumentType,
    ReviewActionType,
    FactSourceType,
)


class InboxRepository:
    """Repository layer encapsulating database access for emails, documents, classifications, facts, reviews, and logs."""

    # ==========================================
    # Email Operations
    # ==========================================
    @staticmethod
    def create_email(
        db: Session,
        sender: str,
        subject: Optional[str] = None,
        body: Optional[str] = None,
        received_date: Optional[datetime] = None,
        message_id: Optional[str] = None,
        status: Union[ProcessingStatus, str] = ProcessingStatus.PENDING,
    ) -> Email:
        status_val = status.value if isinstance(status, ProcessingStatus) else str(status)
        email = Email(
            sender=sender,
            subject=subject,
            body=body,
            message_id=message_id,
            received_date=received_date or datetime.utcnow(),
            processing_status=status_val,
        )
        db.add(email)
        db.commit()
        db.refresh(email)
        return email

    @staticmethod
    def get_email_by_id(db: Session, email_id: int) -> Optional[Email]:
        return db.query(Email).filter(Email.id == email_id).first()

    @staticmethod
    def get_email_by_message_id(db: Session, message_id: str) -> Optional[Email]:
        if not message_id:
            return None
        return db.query(Email).filter(Email.message_id == message_id).first()

    @staticmethod
    def list_emails(
        db: Session,
        skip: int = 0,
        limit: int = 50,
        status: Optional[Union[ProcessingStatus, str]] = None,
    ) -> List[Email]:
        query = db.query(Email)
        if status:
            status_val = status.value if isinstance(status, ProcessingStatus) else str(status)
            query = query.filter(Email.processing_status == status_val)
        return query.order_by(desc(Email.created_at)).offset(skip).limit(limit).all()

    @staticmethod
    def update_email_status(
        db: Session,
        email_id: int,
        status: Union[ProcessingStatus, str],
    ) -> Optional[Email]:
        email = db.query(Email).filter(Email.id == email_id).first()
        if email:
            status_val = status.value if isinstance(status, ProcessingStatus) else str(status)
            email.processing_status = status_val
            db.commit()
            db.refresh(email)
        return email

    # ==========================================
    # Document / Attachment Operations
    # ==========================================
    @staticmethod
    def create_document(
        db: Session,
        filename: str,
        email_id: Optional[int] = None,
        file_path: Optional[str] = None,
        document_type: Union[DocumentType, str] = DocumentType.PDF_DIGITAL,
        extracted_text: Optional[str] = None,
        language: Optional[str] = "en",
        ocr_confidence: Optional[float] = None,
        status: Union[ProcessingStatus, str] = ProcessingStatus.PENDING,
        processing_time: Optional[float] = None,
    ) -> Document:
        doc_type_val = document_type.value if isinstance(document_type, DocumentType) else str(document_type)
        status_val = status.value if isinstance(status, ProcessingStatus) else str(status)
        document = Document(
            email_id=email_id,
            filename=filename,
            file_path=file_path,
            document_type=doc_type_val,
            extracted_text=extracted_text,
            language=language,
            ocr_confidence=ocr_confidence,
            processing_status=status_val,
            processing_time=processing_time,
        )
        db.add(document)
        db.commit()
        db.refresh(document)
        return document

    @staticmethod
    def get_document_by_id(db: Session, document_id: int) -> Optional[Document]:
        doc = (
            db.query(Document)
            .filter(Document.id == document_id)
            .first()
        )

        if doc and doc.email_id:
            from app.models.email import Email
            doc.email = (
                db.query(Email)
                .filter(Email.id == doc.email_id)
                .first()
            )

        return doc

    @staticmethod
    def list_documents_by_email(db: Session, email_id: int) -> List[Document]:
        return db.query(Document).filter(Document.email_id == email_id).all()

    @staticmethod
    def list_documents(
        db: Session,
        skip: int = 0,
        limit: int = 50,
        status: Optional[Union[ProcessingStatus, str]] = None,
    ) -> List[Document]:
        query = db.query(Document)
        if status:
            status_val = status.value if isinstance(status, ProcessingStatus) else str(status)
            query = query.filter(Document.processing_status == status_val)
        return query.order_by(desc(Document.created_at)).offset(skip).limit(limit).all()

    @staticmethod
    def update_document_processing(
        db: Session,
        document_id: int,
        status: Union[ProcessingStatus, str],
        extracted_text: Optional[str] = None,
        processing_time: Optional[float] = None,
    ) -> Optional[Document]:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if doc:
            doc.processing_status = status.value if isinstance(status, ProcessingStatus) else str(status)
            if extracted_text is not None:
                doc.extracted_text = extracted_text
            if processing_time is not None:
                doc.processing_time = processing_time
            db.commit()
            db.refresh(doc)
        return doc

    # ==========================================
    # Classification Operations
    # ==========================================
    @staticmethod
    def add_classification(
        db: Session,
        category: Union[ClassificationCategory, str],
        confidence: Optional[float] = None,
        reason: Optional[str] = None,
        email_id: Optional[int] = None,
        document_id: Optional[int] = None,
    ) -> Classification:
        cat_val = category.value if isinstance(category, ClassificationCategory) else str(category)
        classification = Classification(
            email_id=email_id,
            document_id=document_id,
            category=cat_val,
            confidence=confidence,
            reason=reason,
        )
        db.add(classification)
        db.commit()
        db.refresh(classification)
        return classification

    @staticmethod
    def get_classifications(
        db: Session,
        email_id: Optional[int] = None,
        document_id: Optional[int] = None,
    ) -> List[Classification]:
        query = db.query(Classification)
        if email_id is not None:
            query = query.filter(Classification.email_id == email_id)
        if document_id is not None:
            query = query.filter(Classification.document_id == document_id)
        return query.order_by(desc(Classification.created_at)).all()

    # ==========================================
    # Extracted Facts Operations
    # ==========================================
    @staticmethod
    def add_extracted_fact(
        db: Session,
        document_id: int,
        category: Union[ClassificationCategory, str],
        field_name: str,
        field_value: str = "Not stated",
        confidence: Optional[float] = None,
        source_type: Optional[Union[FactSourceType, str]] = None,
        source_reference: Optional[str] = None,
    ) -> ExtractedFact:
        cat_val = category.value if isinstance(category, ClassificationCategory) else str(category)
        src_val = source_type.value if isinstance(source_type, FactSourceType) else (str(source_type) if source_type else None)
        fact = ExtractedFact(
            document_id=document_id,
            category=cat_val,
            field_name=field_name,
            field_value=field_value if field_value is not None else "Not stated",
            confidence=confidence,
            source_type=src_val,
            source_reference=source_reference,
        )
        db.add(fact)
        db.commit()
        db.refresh(fact)
        return fact

    @staticmethod
    def clear_facts_by_document(
        db: Session,
        document_id: int,
        category: Optional[Union[ClassificationCategory, str]] = None,
    ) -> int:
        query = db.query(ExtractedFact).filter(ExtractedFact.document_id == document_id)
        if category:
            cat_val = category.value if isinstance(category, ClassificationCategory) else str(category)
            query = query.filter(ExtractedFact.category == cat_val)
        deleted_count = query.delete(synchronize_session=False)
        db.commit()
        return deleted_count

    @staticmethod
    def get_facts_by_document(
        db: Session,
        document_id: int,
        category: Optional[Union[ClassificationCategory, str]] = None,
    ) -> List[ExtractedFact]:
        query = db.query(ExtractedFact).filter(ExtractedFact.document_id == document_id)
        if category:
            cat_val = category.value if isinstance(category, ClassificationCategory) else str(category)
            query = query.filter(ExtractedFact.category == cat_val)
        return query.order_by(ExtractedFact.field_name).all()

    @staticmethod
    def get_extracted_fact_by_id(db: Session, fact_id: int) -> Optional[ExtractedFact]:
        return db.query(ExtractedFact).filter(ExtractedFact.id == fact_id).first()

    @staticmethod
    def update_extracted_fact(
        db: Session,
        fact_id: int,
        field_value: str,
        confidence: Optional[float] = None,
        source_type: Optional[str] = None,
        source_reference: Optional[str] = None,
    ) -> Optional[ExtractedFact]:
        fact = db.query(ExtractedFact).filter(ExtractedFact.id == fact_id).first()
        if fact:
            fact.field_value = field_value
            if confidence is not None:
                fact.confidence = confidence
            if source_type is not None:
                fact.source_type = source_type
            if source_reference is not None:
                fact.source_reference = source_reference
            db.commit()
            db.refresh(fact)
        return fact

    @staticmethod
    def upsert_extracted_fact(
        db: Session,
        document_id: int,
        field_name: str,
        field_value: str,
        category: Union[ClassificationCategory, str],
        confidence: Optional[float] = None,
        source_type: Optional[Union[FactSourceType, str]] = None,
        source_reference: Optional[str] = None,
    ) -> ExtractedFact:
        cat_val = category.value if isinstance(category, ClassificationCategory) else str(category)
        src_val = source_type.value if isinstance(source_type, FactSourceType) else (str(source_type) if source_type else None)

        fact = db.query(ExtractedFact).filter(
            ExtractedFact.document_id == document_id,
            ExtractedFact.field_name == field_name,
        ).first()

        if fact:
            fact.field_value = field_value
            fact.category = cat_val
            if confidence is not None:
                fact.confidence = confidence
            if src_val is not None:
                fact.source_type = src_val
            if source_reference is not None:
                fact.source_reference = source_reference
            db.commit()
            db.refresh(fact)
            return fact

        return InboxRepository.add_extracted_fact(
            db=db,
            document_id=document_id,
            category=cat_val,
            field_name=field_name,
            field_value=field_value,
            confidence=confidence,
            source_type=src_val,
            source_reference=source_reference,
        )

    # ==========================================
    # Review Actions Operations
    # ==========================================
    @staticmethod
    def record_review_action(
        db: Session,
        reviewer: str,
        action: Union[ReviewActionType, str],
        comments: Optional[str] = None,
        email_id: Optional[int] = None,
        document_id: Optional[int] = None,
    ) -> ReviewAction:
        action_val = action.value if isinstance(action, ReviewActionType) else str(action)
        review = ReviewAction(
            email_id=email_id,
            document_id=document_id,
            reviewer=reviewer,
            action=action_val,
            comments=comments,
            timestamp=datetime.utcnow(),
        )
        db.add(review)
        db.commit()
        db.refresh(review)
        return review

    @staticmethod
    def get_review_history(
        db: Session,
        email_id: Optional[int] = None,
        document_id: Optional[int] = None,
    ) -> List[ReviewAction]:
        query = db.query(ReviewAction)
        if email_id is not None:
            query = query.filter(ReviewAction.email_id == email_id)
        if document_id is not None:
            query = query.filter(ReviewAction.document_id == document_id)
        return query.order_by(desc(ReviewAction.timestamp)).all()

    # ==========================================
    # Audit Logs Operations
    # ==========================================
    @staticmethod
    def log_event(
        db: Session,
        event: str,
        details: Optional[str] = None,
        email_id: Optional[int] = None,
        document_id: Optional[int] = None,
    ) -> AuditLog:
        log_entry = AuditLog(
            email_id=email_id,
            document_id=document_id,
            event=event,
            details=details,
            timestamp=datetime.utcnow(),
        )
        db.add(log_entry)
        db.commit()
        db.refresh(log_entry)
        return log_entry

    @staticmethod
    def get_audit_logs(
        db: Session,
        email_id: Optional[int] = None,
        document_id: Optional[int] = None,
    ) -> List[AuditLog]:
        query = db.query(AuditLog)
        if email_id is not None:
            query = query.filter(AuditLog.email_id == email_id)
        if document_id is not None:
            query = query.filter(AuditLog.document_id == document_id)
        return query.order_by(desc(AuditLog.timestamp)).all()
