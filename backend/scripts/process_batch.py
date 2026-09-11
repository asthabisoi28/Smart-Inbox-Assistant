"""
Batch Document Processing Script for Smart Inbox Assistant.
Processes a batch of 10-15 documents through the full extraction & AI classification pipeline.

Measures and displays:
Document | Processing Time | Classification | Confidence

IMPORTANT: Uses 100% synthetic fictional test data.
"""

import sys
import time
import uuid
from pathlib import Path

# Add backend root to sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.db.session import SessionLocal, engine
from app.db.base import Base
from app.repositories.inbox_repository import InboxRepository
from app.services.pdf_processing_service import PdfProcessingService
from app.services.ai_service import ai_service
from app.services.synthetic_data_service import SyntheticDataService


def _clean_synthetic_data(db):
    """Remove all previously generated synthetic emails (identified by @health.syn sender)."""
    from app.models.email import Email
    synthetic_emails = db.query(Email).filter(Email.sender.like("%@%.syn")).all()
    count = len(synthetic_emails)
    for email in synthetic_emails:
        db.delete(email)
    db.commit()
    return count


def run_batch_processing(batch_limit: int = 15, force_regenerate: bool = False):
    # Ensure tables exist
    import app.models  # noqa: F401
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        print("=" * 85)
        print("  SMART INBOX ASSISTANT - BATCH DOCUMENT PROCESSING & PERFORMANCE BENCHMARK")
        print("=" * 85)

        # 1. Check if documents exist in DB; if not (or forced), generate synthetic suite
        documents = InboxRepository.list_documents(db, limit=batch_limit)
        if len(documents) < 10 or force_regenerate:
            if force_regenerate:
                cleaned = _clean_synthetic_data(db)
                if cleaned:
                    print(f"\n[INFO] Cleaned {cleaned} previous synthetic email(s) from database.")
            print("\n[INFO] Generating synthetic test suite (15 fictional cases)...")
            res = SyntheticDataService.generate_full_synthetic_suite(db)
            print(f"[INFO] {res['message']}")
            documents = InboxRepository.list_documents(db, limit=batch_limit)

        if not documents:
            print("\n[ERROR] No documents found in database. Cannot proceed.")
            return

        print(f"\nProcessing batch of {len(documents)} synthetic document(s)...\n")

        # Table Header
        header = f"| {'#':<3} | {'Document':<40} | {'Time':<8} | {'Classification':<14} | {'Confidence':<10} |"
        divider = f"|{'-' * 5}|{'-' * 42}|{'-' * 10}|{'-' * 16}|{'-' * 12}|"

        print(header)
        print(divider)

        total_start_time = time.perf_counter()
        processed_records = []
        errors = []

        for idx, doc in enumerate(documents, start=1):
            doc_start = time.perf_counter()

            try:
                # Step 1: PDF Extraction (OCR/text layout extraction)
                pdf_result = PdfProcessingService.process_pdf_document(db, doc.id)

                # Step 2: AI Classification & Fact Extraction
                ai_result = ai_service.classify_and_store(db, document_id=doc.id)
                ai_service.extract_and_store(db, document_id=doc.id)

                doc_end = time.perf_counter()
                elapsed = doc_end - doc_start

                # Resolve Category and Confidence
                cat_label = ai_result.primary_category.value if hasattr(ai_result.primary_category, 'value') else str(ai_result.primary_category)
                primary_item = ai_result.classifications[0] if ai_result.classifications else None
                conf = primary_item.confidence if primary_item else 0.0
                conf_str = f"{int(conf * 100)}%"

                filename_disp = doc.filename[:38] if len(doc.filename) > 38 else doc.filename
                time_str = f"{elapsed:.2f}s"

                print(f"| {idx:<3} | {filename_disp:<40} | {time_str:<8} | {cat_label:<14} | {conf_str:<10} |")

                processed_records.append({
                    "filename": doc.filename,
                    "time": elapsed,
                    "category": cat_label,
                    "confidence": conf,
                })

            except Exception as e:
                doc_end = time.perf_counter()
                elapsed = doc_end - doc_start
                filename_disp = doc.filename[:38] if len(doc.filename) > 38 else doc.filename
                print(f"| {idx:<3} | {filename_disp:<40} | {elapsed:.2f}s  | {'ERROR':<14} | {'N/A':<10} |")
                errors.append({"filename": doc.filename, "error": str(e)})

        total_elapsed = time.perf_counter() - total_start_time
        processed_count = len(processed_records)
        avg_time = total_elapsed / len(documents) if documents else 0

        print(divider)
        print(f"\n{'=' * 85}")
        print(f"  BATCH SUMMARY")
        print(f"{'=' * 85}")
        print(f"  • Total Documents Processed : {processed_count}/{len(documents)}")
        print(f"  • Total Batch Execution Time: {total_elapsed:.2f}s")
        print(f"  • Average Time Per Document : {avg_time:.2f}s")
        if errors:
            print(f"  • Errors Encountered        : {len(errors)}")
            for err in errors:
                print(f"    X {err['filename']}: {err['error'][:80]}")
        print(f"{'=' * 85}")

    finally:
        db.close()


if __name__ == "__main__":
    limit = 15
    force = False
    for arg in sys.argv[1:]:
        if arg == "--force" or arg == "-f":
            force = True
        elif arg.isdigit():
            limit = int(arg)
    run_batch_processing(batch_limit=limit, force_regenerate=force)
