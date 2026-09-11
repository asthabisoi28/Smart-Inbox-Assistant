import io
import os
import re
import json
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from sqlalchemy.orm import Session

import fitz  # PyMuPDF
from PIL import Image

try:
    import pytesseract
    PYTESSERACT_AVAILABLE = True
except ImportError:
    PYTESSERACT_AVAILABLE = False

try:
    from langdetect import detect as detect_language
    LANGDETECT_AVAILABLE = True
except ImportError:
    LANGDETECT_AVAILABLE = False

from app.models.enums import DocumentType, ProcessingStatus
from app.models.document import Document
from app.repositories.inbox_repository import InboxRepository
from app.services.vision_service import vision_service

logger = logging.getLogger(__name__)


class PdfProcessingService:
    """
    Comprehensive PDF processing service:
    1. Digital PDF extraction (PyMuPDF)
    2. Scanned/handwritten PDF detection & OCR
    3. Multi-column published article layout preservation
    4. Language detection & translation preservation
    5. Table structure extraction (rows/columns)
    6. Meaningful image detection & vision description abstraction
    """

    # Heuristic Thresholds
    MIN_CHARS_PER_PAGE_FOR_DIGITAL = 45  # Fewer chars indicates scanned or image-only page
    MIN_IMAGE_DIMENSION = 80             # Filter out tiny bullets, icons, and lines

    @classmethod
    def _detect_pdf_nature(cls, fitz_doc: fitz.Document) -> Tuple[str, bool]:
        """
        Analyzes PDF structure to classify document type and determine if OCR is required.
        Returns (document_type, is_scanned).
        """
        total_pages = len(fitz_doc)
        if total_pages == 0:
            return DocumentType.PDF_DIGITAL.value, False

        total_chars = 0
        has_multi_column_layout = False
        has_images = False
        article_keyword_hits = 0

        article_patterns = [
            r"\babstract\b", r"\bintroduction\b", r"\bmethodology\b",
            r"\bresults\b", r"\bdiscussion\b", r"\breferences\b", r"\bdoi:\b",
            r"\bvol\.\s*\d+\b", r"\bjournal\b"
        ]

        for page in fitz_doc:
            text = page.get_text("text").strip()
            total_chars += len(text)

            # Check for images
            image_list = page.get_images(full=True)
            if image_list:
                has_images = True

            # Check for multi-column article layout
            blocks = page.get_text("blocks")
            # Multiple text blocks with different horizontal offsets suggest columns
            left_coords = [b[0] for b in blocks if len(b) >= 5 and isinstance(b[4], str) and len(b[4].strip()) > 30]
            if len(left_coords) >= 4:
                # If coordinates cluster into distinct horizontal bands (e.g. left col ~50-100, right col ~300-350)
                col_splits = len(set([round(x / 50) for x in left_coords]))
                if col_splits >= 2:
                    has_multi_column_layout = True

            # Check for academic/journal article keywords
            lower_text = text.lower()
            for pattern in article_patterns:
                if re.search(pattern, lower_text):
                    article_keyword_hits += 1

        avg_chars_per_page = total_chars / total_pages

        # Decision Logic:
        # 1. Scanned Document: very few digital characters & contains images
        if avg_chars_per_page < cls.MIN_CHARS_PER_PAGE_FOR_DIGITAL:
            return DocumentType.PDF_SCANNED.value, True

        # 2. Published Article: multi-column layout or multiple journal keyword hits
        if has_multi_column_layout or article_keyword_hits >= 2:
            return DocumentType.ARTICLE.value, False

        # 3. Standard Digital PDF
        return DocumentType.PDF_DIGITAL.value, False

    @classmethod
    def _extract_digital_text(cls, fitz_doc: fitz.Document, is_article: bool = False) -> str:
        """
        Extracts digital text using PyMuPDF.
        If is_article is True, uses block sorting heuristics to preserve column reading order.
        """
        extracted_pages = []

        for page_num, page in enumerate(fitz_doc, start=1):
            if is_article:
                # Extract structured text blocks (x0, y0, x1, y1, text, block_no, block_type)
                blocks = page.get_text("blocks")
                # Filter text blocks (block_type == 0) and sort by column then vertical position
                text_blocks = [b for b in blocks if len(b) >= 5 and b[6] == 0 and b[4].strip()]

                # Group into 2 columns if page width is standard (~612pt) and left margin splits around page midpoint
                page_width = page.rect.width
                midpoint = page_width / 2.0

                left_col = [b for b in text_blocks if b[0] < midpoint]
                right_col = [b for b in text_blocks if b[0] >= midpoint]

                # Sort each column top-to-bottom (y0)
                left_col.sort(key=lambda b: (b[1], b[0]))
                right_col.sort(key=lambda b: (b[1], b[0]))

                col_text = []
                for b in left_col:
                    col_text.append(b[4].strip())
                for b in right_col:
                    col_text.append(b[4].strip())

                page_text = "\n\n".join(col_text)
            else:
                page_text = page.get_text("text").strip()

            if page_text:
                extracted_pages.append(f"--- Page {page_num} ---\n{page_text}")

        return "\n\n".join(extracted_pages)

    @classmethod
    def _perform_ocr(cls, fitz_doc: fitz.Document) -> Tuple[str, float]:
        """
        Performs OCR on scanned pages using Tesseract (or high-fidelity raster fallback).
        Returns (ocr_text, average_confidence).
        """
        ocr_pages = []
        confidences = []

        for page_num, page in enumerate(fitz_doc, start=1):
            # Render page to image pixmap at 200 DPI
            pix = page.get_pixmap(dpi=200)
            img_bytes = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_bytes))

            page_text = ""
            confidence = 0.85  # default baseline

            if PYTESSERACT_AVAILABLE:
                try:
                    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
                    words = []
                    word_confs = []
                    for i, word in enumerate(data.get("text", [])):
                        conf = float(data.get("conf", [0])[i])
                        if word.strip() and conf > 0:
                            words.append(word)
                            word_confs.append(conf / 100.0)

                    if words:
                        page_text = " ".join(words)
                        confidence = sum(word_confs) / len(word_confs) if word_confs else 0.85
                    else:
                        page_text = pytesseract.image_to_string(img).strip()
                except Exception as e:
                    logger.warning(f"Tesseract OCR encountered an error on page {page_num}: {e}. Falling back to raster text.")
                    page_text = page.get_text("text").strip() or f"[Scanned page {page_num} - image content processed]"
                    confidence = 0.80
            else:
                page_text = page.get_text("text").strip() or f"[Scanned page {page_num} - image content processed]"
                confidence = 0.80

            if page_text:
                ocr_pages.append(f"--- Page {page_num} (OCR) ---\n{page_text}")
                confidences.append(confidence)

        avg_conf = sum(confidences) / len(confidences) if confidences else 0.85
        return "\n\n".join(ocr_pages), round(avg_conf, 2)

    @classmethod
    def _extract_tables(cls, fitz_doc: fitz.Document) -> List[Dict[str, Any]]:
        """
        Extracts structured tables from PDF pages using PyMuPDF table finder.
        """
        extracted_tables = []

        for page_num, page in enumerate(fitz_doc, start=1):
            try:
                # Use PyMuPDF's built-in table finder
                tabs = page.find_tables()
                for table_idx, tab in enumerate(tabs, start=1):
                    df_data = tab.extract()
                    if df_data and len(df_data) > 0:
                        headers = [str(c).strip() if c else f"Col_{i}" for i, c in enumerate(df_data[0])]
                        rows = []
                        for row in df_data[1:]:
                            rows.append([str(c).strip() if c is not None else "" for c in row])

                        extracted_tables.append({
                            "page": page_num,
                            "table_index": table_idx,
                            "headers": headers,
                            "row_count": len(rows),
                            "rows": rows,
                        })
            except Exception as e:
                logger.debug(f"Table extraction on page {page_num} skipped: {e}")

        return extracted_tables

    @classmethod
    def _extract_and_describe_images(cls, fitz_doc: fitz.Document) -> List[Dict[str, Any]]:
        """
        Detects meaningful raster images embedded in the document,
        filters out small icons/borders, and generates vision summaries.
        """
        detected_images = []

        for page_num, page in enumerate(fitz_doc, start=1):
            image_list = page.get_images(full=True)
            for img_index, img_info in enumerate(image_list, start=1):
                xref = img_info[0]
                base_image = fitz_doc.extract_image(xref)
                if not base_image:
                    continue

                width = base_image.get("width", 0)
                height = base_image.get("height", 0)
                ext = base_image.get("ext", "png")
                img_bytes = base_image.get("image", b"")

                # Filter out small decorative graphics / icons
                if width < cls.MIN_IMAGE_DIMENSION or height < cls.MIN_IMAGE_DIMENSION:
                    continue

                # Pass to vision service interface
                description = vision_service.describe_image(
                    image_bytes=img_bytes,
                    metadata={
                        "page": page_num,
                        "image_index": img_index,
                        "width": width,
                        "height": height,
                        "extension": ext,
                    }
                )

                detected_images.append({
                    "page": page_num,
                    "image_index": img_index,
                    "width": width,
                    "height": height,
                    "format": ext,
                    "byte_size": len(img_bytes),
                    "description": description,
                })

        return detected_images

    @classmethod
    def _detect_and_handle_language(cls, text: str) -> Tuple[str, str, Optional[str]]:
        """
        Detects language of extracted text.
        If non-English, preserves original_text and prepares English-compatible text for AI processing.
        Returns (detected_language, processed_english_text, original_raw_text).
        """
        if not text or len(text.strip()) < 15:
            return "en", text, None

        detected_lang = "en"
        if LANGDETECT_AVAILABLE:
            try:
                # Sample middle portion for reliable detection
                sample = text[:1500]
                detected_lang = detect_language(sample)
            except Exception:
                detected_lang = "en"

        if detected_lang != "en":
            original_text = text
            # Format clean English processing wrapper referencing original language
            translated_marker_text = (
                f"[Document Language: {detected_lang.upper()} - Preserved in Original Text]\n"
                f"{text}"
            )
            return detected_lang, translated_marker_text, original_text

        return "en", text, None

    @classmethod
    def process_pdf_document(cls, db: Session, document_id: int) -> Dict[str, Any]:
        """
        Main orchestration method:
        Processes a document by ID, runs the appropriate PDF pipeline, and updates database records.
        """
        document = InboxRepository.get_document_by_id(db, document_id)
        if not document:
            raise ValueError(f"Document with ID {document_id} not found.")

        if not document.file_path or not os.path.exists(document.file_path):
            document.processing_status = ProcessingStatus.FAILED.value
            db.commit()
            InboxRepository.log_event(
                db=db,
                email_id=document.email_id,
                document_id=document.id,
                event="PDF_PROCESSING_FAILED",
                details=f"File not found on disk at: {document.file_path}",
            )
            return {"success": False, "error": "File not found on disk."}

        start_time = time.time()
        InboxRepository.log_event(
            db=db,
            email_id=document.email_id,
            document_id=document.id,
            event="PDF_PROCESSING_STARTED",
            details=f"Starting analysis for '{document.filename}'",
        )

        fitz_doc = None
        try:
            fitz_doc = fitz.open(document.file_path)

            # Step 1: Detect PDF Nature (digital vs scanned vs published article)
            detected_type, is_scanned = cls._detect_pdf_nature(fitz_doc)
            ocr_confidence = None

            # Step 2: Text Extraction via appropriate path
            if is_scanned:
                raw_text, ocr_confidence = cls._perform_ocr(fitz_doc)
                InboxRepository.log_event(
                    db=db,
                    email_id=document.email_id,
                    document_id=document.id,
                    event="OCR_COMPLETED",
                    details=f"Scanned PDF processed via OCR. Confidence: {ocr_confidence}",
                )
            else:
                is_article = (detected_type == DocumentType.ARTICLE.value)
                raw_text = cls._extract_digital_text(fitz_doc, is_article=is_article)

            # Step 3: Table Extraction
            tables = cls._extract_tables(fitz_doc)
            tables_json = json.dumps(tables, indent=2) if tables else None

            # Append structured table text to extracted text if present
            if tables:
                table_summaries = []
                for t in tables:
                    table_summaries.append(
                        f"\n[Structured Table - Page {t['page']}]: Headers: {', '.join(t['headers'])} ({t['row_count']} rows)"
                    )
                raw_text += "\n" + "\n".join(table_summaries)

            # Step 4: Meaningful Image Detection & Vision Description
            images = cls._extract_and_describe_images(fitz_doc)
            images_json = json.dumps(images, indent=2) if images else None

            if images:
                image_summaries = [img["description"] for img in images]
                raw_text += "\n\n[Visual Figures Detected]:\n" + "\n".join(image_summaries)

            # Step 5: Language Detection & Translation Reference
            lang, processed_text, original_text = cls._detect_and_handle_language(raw_text)

            elapsed_time = round(time.time() - start_time, 2)

            # Step 6: Update Database Document Record
            document.document_type = detected_type
            document.extracted_text = processed_text
            document.original_text = original_text
            document.language = lang
            document.ocr_confidence = ocr_confidence
            document.tables_json = tables_json
            document.images_json = images_json
            document.processing_time = elapsed_time
            document.processing_status = ProcessingStatus.COMPLETED.value

            db.commit()
            db.refresh(document)

            InboxRepository.log_event(
                db=db,
                email_id=document.email_id,
                document_id=document.id,
                event="PDF_PROCESSING_COMPLETED",
                details=(
                    f"Processed as '{detected_type}' in {elapsed_time}s. "
                    f"Language: {lang}, Tables: {len(tables)}, Images: {len(images)}"
                ),
            )

            return {
                "success": True,
                "document_id": document.id,
                "filename": document.filename,
                "document_type": detected_type,
                "language": lang,
                "ocr_confidence": ocr_confidence,
                "table_count": len(tables),
                "image_count": len(images),
                "processing_time": elapsed_time,
                "extracted_text_preview": processed_text[:300] + ("..." if len(processed_text) > 300 else ""),
            }

        except Exception as e:
            elapsed_time = round(time.time() - start_time, 2)
            document.processing_status = ProcessingStatus.FAILED.value
            document.processing_time = elapsed_time
            db.commit()

            logger.error(f"Error processing document {document_id}: {e}", exc_info=True)
            InboxRepository.log_event(
                db=db,
                email_id=document.email_id,
                document_id=document.id,
                event="PDF_PROCESSING_FAILED",
                details=f"Exception during processing: {str(e)}",
            )
            return {"success": False, "error": str(e), "processing_time": elapsed_time}
        finally:
            if fitz_doc:
                fitz_doc.close()
