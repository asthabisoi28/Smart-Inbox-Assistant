"""
AI Classification Service
=========================
Orchestrates document classification using the Google Gemini API.

Architecture:
  1. _classify_with_gemini()   — Calls Gemini with JSON mode, validates with Pydantic.
  2. _heuristic_fallback()     — Deterministic keyword classifier used when API is
                                  unavailable or returns invalid output.
  3. classify()                — Tries Gemini first, falls back to heuristic on any error.
  4. classify_and_store()      — Public method: classifies then persists to the DB.

Safety guarantees:
  - API key is read exclusively from environment / settings — never hardcoded.
  - Markdown fences (```json ... ```) are stripped before JSON parsing.
  - Pydantic ValidationError is caught and logged; heuristic fallback is always safe.
  - All unhandled exceptions surface via the fallback so callers always get a result.
"""

import os
import json
import re
import time
import logging
from typing import Any, Dict, List, Optional, Tuple, Union

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.prompts import (
    CLASSIFICATION_SYSTEM_PROMPT,
    CLASSIFICATION_USER_PROMPT_TEMPLATE,
    EXTRACTION_SYSTEM_PROMPT,
    ICSR_EXTRACTION_USER_PROMPT_TEMPLATE,
    PQC_EXTRACTION_USER_PROMPT_TEMPLATE,
    MI_EXTRACTION_USER_PROMPT_TEMPLATE,
)
from app.models.enums import ClassificationCategory, FactSourceType, ProcessingStatus
from app.models.email import Email
from app.models.document import Document
from app.repositories.inbox_repository import InboxRepository
from app.schemas.ai_schemas import (
    AIParseError,
    ClassificationItem,
    ClassificationResult,
    ClassifyRequest,
    ClassifyResponse,
    ExtractedField,
    PatientInfo,
    ReporterInfo,
    ProductInfo,
    ReactionInfo,
    SeverityInfo,
    NarrativeInfo,
    ICSRExtraction,
    PQCExtraction,
    MIExtraction,
    ExtractionResult,
    ExtractResponse,
    StoredFactItem,
    StoredFactsResponse,
)

logger = logging.getLogger(__name__)

# ── Gemini SDK availability guard (google-genai v2+) ─────────────────────────
try:
    from google import genai
    from google.genai import types as genai_types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    logger.warning(
        "google-genai package not installed. "
        "Run: pip install google-genai  "
        "Gemini classification is unavailable; heuristic fallback will be used."
    )

# ── Category priority for multi-label primary selection ──────────────────────
_CATEGORY_PRIORITY: List[ClassificationCategory] = [
    ClassificationCategory.ICSR,
    ClassificationCategory.PQC,
    ClassificationCategory.MI,
    ClassificationCategory.NOT_RELEVANT,
]

# ── Regex to strip markdown code fences the model might produce ──────────────
_MARKDOWN_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _strip_markdown_fences(text: str) -> str:
    """Remove ```json ... ``` or ``` ... ``` wrappers from a model response."""
    match = _MARKDOWN_FENCE_RE.search(text)
    if match:
        return match.group(1).strip()
    return text.strip()


def _pick_primary(items: List[ClassificationItem]) -> ClassificationCategory:
    """Return the highest-priority category present in *items*."""
    present = {item.category for item in items}
    for cat in _CATEGORY_PRIORITY:
        if cat in present:
            return cat
    return items[0].category  # fallback: first item


class AIService:
    """
    Service orchestrating AI classification, LLM prompt generation,
    schema validation, and Oracle/SQLite database storage.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> None:
        # Read the API key from settings or environment variable GEMINI_API_KEY.
        # Never hardcode the API key.
        self._api_key: Optional[str] = api_key
        self._model_name: Optional[str] = model_name

    @property
    def api_key(self) -> str:
        return self._api_key or settings.GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY", "")

    @property
    def model_name(self) -> str:
        return self._model_name or settings.GEMINI_MODEL or "gemini-1.5-flash"

    # ─────────────────────────────────────────────────────────────────────────
    # Private: Gemini API call
    # ─────────────────────────────────────────────────────────────────────────

    def _classify_with_gemini(
        self, email_text: str, extracted_text: str
    ) -> Tuple[ClassificationResult, str]:
        """
        Calls the Google Gemini API (google-genai v2 SDK) in JSON response mode
        and validates the output with Pydantic.

        Raises:
            ValueError: If the SDK is unavailable or no API key is configured.
            json.JSONDecodeError: If the model returns non-parseable JSON.
            pydantic.ValidationError: If the JSON structure violates our schema.
            Exception: Propagated for any other Gemini SDK error.
        """
        if not GENAI_AVAILABLE:
            raise ValueError(
                "google-genai SDK is not installed. "
                "Run: pip install google-genai"
            )
        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY environment variable is not set. "
                "Classification cannot proceed without an API key."
            )

        # Build the combined prompt content (system + user)
        full_prompt = (
            CLASSIFICATION_SYSTEM_PROMPT
            + "\n\n"
            + CLASSIFICATION_USER_PROMPT_TEMPLATE.format(
                email_text=email_text.strip() if email_text else "(No email body provided)",
                extracted_text=(
                    extracted_text.strip()
                    if extracted_text
                    else "(No PDF attachment text provided)"
                ),
            )
        )

        # Instantiate the client with the API key from the environment variable.
        client = genai.Client(api_key=self.api_key)

        logger.debug("Sending classification prompt to Gemini (%s)...", self.model_name)

        response = client.models.generate_content(
            model=self.model_name,
            contents=full_prompt,
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,   # Low temperature → deterministic, consistent output
                top_p=0.9,
                max_output_tokens=1024,
            ),
        )

        raw_text: str = response.text or ""

        # ── Step 1: Strip markdown fences in case the model wraps the JSON ──
        clean_text = _strip_markdown_fences(raw_text)

        # ── Step 2: Parse JSON ───────────────────────────────────────────────
        try:
            parsed_dict = json.loads(clean_text)
        except json.JSONDecodeError as exc:
            logger.error(
                "Gemini returned non-JSON output.\nRaw response:\n%s\nError: %s",
                raw_text,
                exc,
            )
            raise  # Caller handles this

        # ── Step 3: Validate with Pydantic ───────────────────────────────────
        try:
            result = ClassificationResult.model_validate(parsed_dict)
        except ValidationError as exc:
            logger.error(
                "Gemini JSON failed Pydantic validation.\nParsed dict: %s\nErrors: %s",
                parsed_dict,
                exc,
            )
            raise  # Caller handles this

        logger.info(
            "Gemini classification succeeded. primary=%s classifications=%d",
            result.primary_category.value,
            len(result.classifications),
        )
        return result, self.model_name

    # ─────────────────────────────────────────────────────────────────────────
    # Private: Heuristic fallback classifier
    # ─────────────────────────────────────────────────────────────────────────

    def _heuristic_fallback_classify(
        self, email_text: str, extracted_text: str
    ) -> Tuple[ClassificationResult, str]:
        """
        Deterministic, rule-based clinical keyword classifier.

        Used when:
          - GEMINI_API_KEY is missing / empty
          - Gemini returns invalid JSON or a Pydantic validation error
          - Any other Gemini SDK exception

        Never raises — always returns a valid ClassificationResult.
        """
        combined = f"{email_text}\n{extracted_text}".lower()
        items: List[ClassificationItem] = []

        # ── ICSR signals ─────────────────────────────────────────────────────
        icsr_keywords = [
            "adverse event", "adverse drug reaction", "adverse reaction", "icsr",
            "adverse", "reaction", "side effect", "allergic reaction", "allergy",
            "bronchospasm", "urticaria", "rash", "hives", "swelling", "edema", "angioedema",
            "anaphylaxis", "anaphylactic", "hematoma", "tachycardia", "nausea", "vomiting", "fever",
            "hospitaliz", "hospitalise", "injury", "fatality", "death", "pruritus", "prurito",
            "dyspnea", "dyspnoea", "chest pain", "dizziness", "seizure", "syncope", "triage",
            "reaccion", "reacción", "adversa", "pharmacovigilance", "farmacovigilancia",
            "indesirable", "indésirable", "vertiges", "somnolence", "efecto adverso",
        ]
        has_icsr = any(kw in combined for kw in icsr_keywords)

        # ── PQC signals ───────────────────────────────────────────────────────
        pqc_keywords = [
            "quality complaint", "pqc", "defect", "cracked", "broken", "fractured",
            "leaking", "contamination", "particulate", "discoloration", "counterfeit",
            "bent needle", "faulty", "seal broken", "broken seal", "packaging defect",
            "wrong colour", "wrong color", "damaged packaging", "manufacturing defect",
            "defaut", "défaut", "flacon", "fuite", "lote", "reclamat", "réclamat",
            "calidad", "qualite", "qualité", "queja", "clogged", "actuator",
        ]
        has_pqc = any(kw in combined for kw in pqc_keywords)

        # ── MI signals ────────────────────────────────────────────────────────
        mi_keywords = [
            "dosage", "dose", "titration", "how to take", "administration",
            "interaction", "renal impairment", "stability", "inquiry", "enquiry",
            "medical information", "guideline", "what is the recommended",
            "can i take", "when should i", "storage condition", "posologia", "posología",
            "titration", "excursion",
        ]
        has_mi = any(kw in combined for kw in mi_keywords)

        # ── NOT_RELEVANT signals ──────────────────────────────────────────────
        nonrel_keywords = [
            "expo ", "conference", "invitation", "webinar", "early bird",
            "newsletter", "sale ", "discount", "marketing", "unsubscribe",
            "click here", "limited offer",
        ]
        is_nonrel = any(kw in combined for kw in nonrel_keywords)

        # ── Build classification items ────────────────────────────────────────
        if has_icsr:
            items.append(ClassificationItem(
                category=ClassificationCategory.ICSR,
                confidence=0.85,
                reason=(
                    "Clinical safety keywords (e.g. adverse event, adverse reaction, "
                    "or specific symptoms) detected in the text."
                ),
            ))

        if has_pqc:
            items.append(ClassificationItem(
                category=ClassificationCategory.PQC,
                confidence=0.83,
                reason=(
                    "Product quality keywords (e.g. broken seal, contamination, "
                    "counterfeit, or packaging defect) detected in the text."
                ),
            ))

        if has_mi:
            reason = (
                "Medical information request keywords (e.g. dosage, interactions, "
                "how to take, administration) detected."
            )
            items.append(ClassificationItem(
                category=ClassificationCategory.MI,
                confidence=0.80,
                reason=reason,
            ))

        if not items:
            reason = (
                "Promotional or marketing content detected; no safety, quality, or "
                "medical information signals present."
                if is_nonrel
                else
                "No ICSR, PQC, or MI signals detected; text does not contain "
                "actionable healthcare correspondence."
            )
            items.append(ClassificationItem(
                category=ClassificationCategory.NOT_RELEVANT,
                confidence=0.75 if not is_nonrel else 0.90,
                reason=reason,
            ))

        primary = _pick_primary(items)
        summary = (
            f"Heuristic classification: {primary.value} "
            f"({len(items)} tag(s) assigned). "
            "Note: AI model was unavailable; result is keyword-based."
        )
        result = ClassificationResult(
            classifications=items,
            primary_category=primary,
            summary=summary,
        )
        return result, "heuristic-rule-engine-v1"

    # ─────────────────────────────────────────────────────────────────────────
    # Public: classify (Gemini + fallback)
    # ─────────────────────────────────────────────────────────────────────────

    def classify(
        self,
        email_text: str = "",
        extracted_text: str = "",
    ) -> Tuple[ClassificationResult, str]:
        """
        Classify the supplied text.

        1. If GEMINI_API_KEY is set and the SDK is available → try Gemini.
           - On json.JSONDecodeError or pydantic.ValidationError → log parse
             error details and fall back to heuristic.
           - On any other exception (network, quota, etc.) → log and fall back.
        2. Otherwise → heuristic fallback directly.

        Always returns a (ClassificationResult, model_name_str) tuple.
        """
        if self.api_key and GENAI_AVAILABLE:
            try:
                return self._classify_with_gemini(email_text, extracted_text)

            except (json.JSONDecodeError, ValidationError) as exc:
                # Structured parse error — log the details for debugging
                logger.warning(
                    "AI response validation failed (%s). Using heuristic fallback. "
                    "Details: %s",
                    type(exc).__name__,
                    exc,
                )

            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Gemini API call failed (%s: %s). Using heuristic fallback.",
                    type(exc).__name__,
                    exc,
                )

        return self._heuristic_fallback_classify(email_text, extracted_text)

    # ─────────────────────────────────────────────────────────────────────────
    # Public: classify_and_store (classification + DB persistence)
    # ─────────────────────────────────────────────────────────────────────────

    def classify_and_store(
        self,
        db: Session,
        email_id: Optional[int] = None,
        document_id: Optional[int] = None,
        email_text: Optional[str] = None,
        extracted_text: Optional[str] = None,
    ) -> ClassifyResponse:
        """
        Run classification and persist all results to the database.

        Steps:
          1. If DB references (email_id / document_id) are provided but text is
             not supplied inline, load text from the database.
          2. Run classify() → always returns a valid result.
          3. Persist each ClassificationItem as a Classification ORM row.
          4. Update processing status on Email / Document records.
          5. Write an audit log entry.
          6. Return ClassifyResponse.
        """
        start_time = time.monotonic()
        error_msg: Optional[str] = None

        # ── 1. Load text from DB if not supplied inline ───────────────────────
        if email_id and not (email_text and email_text.strip()):
            email_record: Optional[Email] = InboxRepository.get_email_by_id(db, email_id)
            if email_record:
                subject_prefix = f"Subject: {email_record.subject}\n\n" if email_record.subject else ""
                email_text = f"{subject_prefix}{email_record.body or ''}"
                if not (extracted_text and extracted_text.strip()):
                    docs = InboxRepository.list_documents_by_email(db, email_id)
                    doc_texts = [
                        d.extracted_text for d in docs if d.extracted_text
                    ]
                    if doc_texts:
                        extracted_text = "\n\n".join(doc_texts)

        if document_id and not (extracted_text and extracted_text.strip()):
            doc_record: Optional[Document] = InboxRepository.get_document_by_id(
                db, document_id
            )
            if doc_record:
                if doc_record.extracted_text:
                    extracted_text = doc_record.extracted_text
                if not email_id and doc_record.email_id:
                    email_id = doc_record.email_id

        # ── 2. Classify ───────────────────────────────────────────────────────
        result, model_used = self.classify(
            email_text=email_text or "",
            extracted_text=extracted_text or "",
        )

        elapsed = round(time.monotonic() - start_time, 3)

        # ── 3. Persist classifications ────────────────────────────────────────
        for item in result.classifications:
            InboxRepository.add_classification(
                db=db,
                category=item.category,
                confidence=item.confidence,
                reason=item.reason,
                email_id=email_id,
                document_id=document_id,
            )

        # ── 4. Update statuses ────────────────────────────────────────────────
        if email_id:
            InboxRepository.update_email_status(
                db, email_id, ProcessingStatus.COMPLETED
            )
        if document_id:
            InboxRepository.update_document_processing(
                db=db,
                document_id=document_id,
                status=ProcessingStatus.COMPLETED,
            )

        # ── 5. Audit log ──────────────────────────────────────────────────────
        cats_str = ", ".join(
            f"{c.category.value} ({int(c.confidence * 100)}%)"
            for c in result.classifications
        )
        InboxRepository.log_event(
            db=db,
            email_id=email_id,
            document_id=document_id,
            event="AI_CLASSIFICATION_COMPLETED",
            details=(
                f"Model: {model_used} | Time: {elapsed}s | "
                f"Primary: {result.primary_category.value} | "
                f"Tags: [{cats_str}] | "
                f"Summary: {result.summary}"
            ),
        )

        logger.info(
            "classify_and_store complete — email_id=%s doc_id=%s primary=%s model=%s time=%.3fs",
            email_id,
            document_id,
            result.primary_category.value,
            model_used,
            elapsed,
        )

        # ── 6. Return response ────────────────────────────────────────────────
        return ClassifyResponse(
            success=True,
            email_id=email_id,
            document_id=document_id,
            primary_category=result.primary_category,
            classifications=result.classifications,
            summary=result.summary,
            processing_time=elapsed,
            model_used=model_used,
            error=error_msg,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Extraction: Private Gemini extraction
    # ─────────────────────────────────────────────────────────────────────────

    def _extract_with_gemini(
        self,
        document_content: str,
        category: ClassificationCategory,
    ) -> Tuple[ExtractionResult, str]:
        """
        Calls Gemini to extract structured facts according to the category schema.
        Validates the output strictly with Pydantic.
        """
        if not GENAI_AVAILABLE:
            raise ValueError("google-genai SDK is not installed.")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not set in environment.")

        # Select the prompt template matching category
        if category == ClassificationCategory.ICSR:
            user_prompt = ICSR_EXTRACTION_USER_PROMPT_TEMPLATE.format(
                document_content=document_content.strip() or "(No content provided)"
            )
        elif category == ClassificationCategory.PQC:
            user_prompt = PQC_EXTRACTION_USER_PROMPT_TEMPLATE.format(
                document_content=document_content.strip() or "(No content provided)"
            )
        elif category == ClassificationCategory.MI:
            user_prompt = MI_EXTRACTION_USER_PROMPT_TEMPLATE.format(
                document_content=document_content.strip() or "(No content provided)"
            )
        else:
            return ExtractionResult(
                category=ClassificationCategory.NOT_RELEVANT,
                facts_count=0,
                summary="Document classified as NOT_RELEVANT; no safety, quality, or medical facts to extract.",
            ), self.model_name

        full_prompt = f"{EXTRACTION_SYSTEM_PROMPT}\n\n{user_prompt}"

        client = genai.Client(api_key=self.api_key)
        logger.debug("Sending extraction prompt to Gemini (%s) for category %s...", self.model_name, category.value)

        response = client.models.generate_content(
            model=self.model_name,
            contents=full_prompt,
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0,  # Zero temp for strict deterministic extraction
                top_p=0.9,
                max_output_tokens=2048,
            ),
        )

        raw_text: str = response.text or ""
        clean_text = _strip_markdown_fences(raw_text)

        parsed_dict = json.loads(clean_text)

        # Validate with Pydantic based on category
        if category == ClassificationCategory.ICSR:
            icsr_obj = ICSRExtraction.model_validate(parsed_dict)
            facts_count = 0
            for section in [icsr_obj.patient, icsr_obj.reporter, icsr_obj.product, icsr_obj.reaction, icsr_obj.severity, icsr_obj.narrative]:
                for _, f in section.model_dump().items():
                    if isinstance(f, dict) and f.get("value") and f.get("value") != "Not stated":
                        facts_count += 1

            result = ExtractionResult(
                category=ClassificationCategory.ICSR,
                icsr=icsr_obj,
                facts_count=facts_count,
                summary=parsed_dict.get("summary", "ICSR safety facts extracted successfully."),
            )
        elif category == ClassificationCategory.PQC:
            pqc_obj = PQCExtraction.model_validate(parsed_dict)
            facts_count = sum(
                1 for _, f in pqc_obj.model_dump().items()
                if isinstance(f, dict) and f.get("value") and f.get("value") != "Not stated"
            )
            result = ExtractionResult(
                category=ClassificationCategory.PQC,
                pqc=pqc_obj,
                facts_count=facts_count,
                summary=parsed_dict.get("summary", "PQC quality complaint facts extracted successfully."),
            )
        elif category == ClassificationCategory.MI:
            mi_obj = MIExtraction.model_validate(parsed_dict)
            facts_count = sum(
                1 for _, f in mi_obj.model_dump().items()
                if isinstance(f, dict) and f.get("value") and f.get("value") != "Not stated"
            )
            result = ExtractionResult(
                category=ClassificationCategory.MI,
                mi=mi_obj,
                facts_count=facts_count,
                summary=parsed_dict.get("summary", "MI inquiry facts extracted successfully."),
            )

        logger.info(
            "Gemini extraction succeeded for %s (%d stated facts)",
            category.value,
            result.facts_count,
        )
        return result, self.model_name

    # ─────────────────────────────────────────────────────────────────────────
    # Extraction: Private Heuristic fallback extraction
    # ─────────────────────────────────────────────────────────────────────────

    def _heuristic_fallback_extract(
        self,
        document_content: str,
        category: ClassificationCategory,
    ) -> Tuple[ExtractionResult, str]:
        """
        Deterministic regex/rule-based clinical fact extraction engine.
        Ensures strict compliance with:
        - Never guess (defaults to 'Not stated', 0.0 confidence, 'Not stated' source)
        - Every field has confidence and source_reference
        """
        text = document_content or ""
        source_ref = "Document text" if text.strip() else "Not stated"

        def _make_field(val: Optional[str], default_source: str = source_ref, conf: float = 0.85) -> ExtractedField:
            if val and val.strip() and val.strip().lower() != "not stated":
                return ExtractedField(
                    value=val.strip(),
                    confidence=conf,
                    source_reference=default_source,
                )
            return ExtractedField(
                value="Not stated",
                confidence=0.0,
                source_reference="Not stated",
            )

        if category == ClassificationCategory.ICSR:
            # Patient extraction
            age_m = re.search(r"\b(\d{1,3})\s*(?:years?\s*old|yo|y/o|yr\s*old)\b", text, re.IGNORECASE) or \
                    re.search(r"age[:\s]+(\d{1,3})", text, re.IGNORECASE)
            sex_m = re.search(r"\b(female|male|woman|man|boy|girl)\b", text, re.IGNORECASE)
            wt_m = re.search(r"(\d+(?:\.\d+)?\s*(?:kg|lbs|pounds|kilograms))\b", text, re.IGNORECASE)
            ht_m = re.search(r"(\d+(?:\.\d+)?\s*(?:cm|m|feet|inches))\b", text, re.IGNORECASE)
            hist_m = re.search(r"(?:history|medical history|diagnosed with|conditions?):\s*([^\.\n]+)", text, re.IGNORECASE)

            # Reporter extraction
            rep_name_m = re.search(r"(?:reported by|reporter[:\s]+|from[:\s]+)\s*([A-Za-z\s\.\-]+?)(?:\n|,|$)", text, re.IGNORECASE)
            # Prioritize HCP roles (Physician, Nurse, Doctor, Pharmacist) over generic Patient keyword
            rep_role_m = re.search(r"\b(physician|doctor|nurse|pharmacist|healthcare professional|hcp)\b", text, re.IGNORECASE) or \
                         re.search(r"(?:reporter|role)[:\s]+\b(patient|consumer)\b", text, re.IGNORECASE) or \
                         re.search(r"\b(consumer)\b", text, re.IGNORECASE)
            rep_country_m = re.search(r"\b(usa|united states|uk|united kingdom|canada|germany|france|japan|india|australia|italy|spain)\b", text, re.IGNORECASE)

            # Product extraction
            prod_name_m = re.search(r"\b(Drug\s+[A-Za-z0-9\-_]+|Med-[A-Za-z0-9\-_]+|Solution\s+[A-Za-z0-9\-_]+|Vaccine\s+[A-Za-z0-9\-_]+)\b", text, re.IGNORECASE) or \
                          re.search(r"(?:taking|received|administered|prescribed|drug|product|medication)\s+([A-Z][A-Za-z0-9\-_]+)", text)
            dose_m = re.search(r"(\d+(?:\.\d+)?\s*(?:mg|mcg|ml|g|units|iu)(?:\s*(?:daily|bid|tid|weekly|monthly))?)", text, re.IGNORECASE)
            route_m = re.search(r"\b(oral|orally|intravenous|iv|subcutaneous|sc|sub-q|intramuscular|im|topical|inhalation|injection)\b", text, re.IGNORECASE)
            start_date_m = re.search(r"(?:started|start date|since|on)\s*([0-9]{4}-[0-9]{2}-[0-9]{2}|[A-Za-z]+\s+\d{1,2},?\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4})", text, re.IGNORECASE)
            stop_date_m = re.search(r"(?:stopped|stop date|discontinued on)\s*([0-9]{4}-[0-9]{2}-[0-9]{2}|[A-Za-z]+\s+\d{1,2},?\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4})", text, re.IGNORECASE)

            # Reaction extraction
            react_m = re.search(r"(?:developed|experienced|suffered|complained of)\s+([^\.\n,]+)", text, re.IGNORECASE) or \
                      re.search(r"\b(rash|urticaria|hives|swelling|anaphylaxis|bronchospasm|hematoma|nausea|vomiting|tachycardia|fever|chest pain|dyspnea)\b", text, re.IGNORECASE)
            react_start_m = re.search(r"(?:onset|reaction started|began on)\s*([0-9]{4}-[0-9]{2}-[0-9]{2}|[A-Za-z]+\s+\d{1,2},?\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4})", text, re.IGNORECASE)
            outcome_m = re.search(r"\b(recovered|recovering|not recovered|fatal|resolved|improving|died)\b", text, re.IGNORECASE)

            # Severity extraction
            is_serious = any(w in text.lower() for w in ["hospital", "death", "fatal", "life-threatening", "serious", "emergency"])
            is_death = any(w in text.lower() for w in ["death", "fatal", "died"])
            is_hosp = any(w in text.lower() for w in ["hospital", "hospitalization", "hospitalized", "hospitalised", "emergency room", "er"])
            is_lt = "life-threatening" in text.lower() or "life threatening" in text.lower()

            # Narrative case summary
            first_sentences = " ".join([s.strip() for s in text.split(".")[:2] if s.strip()])
            narrative_val = first_sentences if len(first_sentences) > 15 else "Adverse event case reported."

            patient = PatientInfo(
                age=_make_field(age_m.group(1) if age_m else None),
                sex=_make_field(sex_m.group(1).capitalize() if sex_m else None),
                weight=_make_field(wt_m.group(1) if wt_m else None),
                height=_make_field(ht_m.group(1) if ht_m else None),
                relevant_history=_make_field(hist_m.group(1) if hist_m else None),
            )
            reporter = ReporterInfo(
                name=_make_field(rep_name_m.group(1) if rep_name_m else None),
                role=_make_field(rep_role_m.group(1).capitalize() if rep_role_m else None),
                country=_make_field(rep_country_m.group(1).upper() if rep_country_m else None),
            )
            product = ProductInfo(
                name=_make_field(prod_name_m.group(1) if prod_name_m else None),
                dose=_make_field(dose_m.group(1) if dose_m else None),
                route=_make_field(route_m.group(1).capitalize() if route_m else None),
                start_date=_make_field(start_date_m.group(1) if start_date_m else None),
                stop_date=_make_field(stop_date_m.group(1) if stop_date_m else None),
            )
            reaction = ReactionInfo(
                reaction=_make_field(react_m.group(1) if react_m else None),
                start_date=_make_field(react_start_m.group(1) if react_start_m else None),
                outcome=_make_field(outcome_m.group(1).capitalize() if outcome_m else None),
            )
            severity = SeverityInfo(
                serious=_make_field("Yes" if is_serious else None),
                death=_make_field("Yes" if is_death else None),
                hospitalization=_make_field("Yes" if is_hosp else None),
                life_threatening=_make_field("Yes" if is_lt else None),
                other_severity=_make_field("Hospital admission required" if is_hosp else None),
            )
            narrative = NarrativeInfo(
                case_summary=_make_field(narrative_val),
            )

            icsr_obj = ICSRExtraction(
                patient=patient,
                reporter=reporter,
                product=product,
                reaction=reaction,
                severity=severity,
                narrative=narrative,
            )

            facts_count = 0
            for sec in [patient, reporter, product, reaction, severity, narrative]:
                for _, f in sec.model_dump().items():
                    if isinstance(f, dict) and f.get("value") and f.get("value") != "Not stated":
                        facts_count += 1

            result = ExtractionResult(
                category=ClassificationCategory.ICSR,
                icsr=icsr_obj,
                facts_count=facts_count,
                summary=f"Heuristic ICSR extraction completed ({facts_count} fact(s) identified).",
            )
            return result, "heuristic-extraction-engine-v1"

        elif category == ClassificationCategory.PQC:
            prod_m = re.search(r"(?:product|device|drug|item|batch of)\s+([A-Z][A-Za-z0-9\-_]+)", text) or \
                     re.search(r"\b(Solution\s+[A-Z]|Autoinjector|Syringe|Vial|Med-[A-Z]|Drug\s+[A-Z])\b", text, re.IGNORECASE)
            lot_m = re.search(r"(?:lot|batch)(?:\s*(?:#|no\.?|number)?:?\s*)([A-Z0-9\-]+)", text, re.IGNORECASE)
            prob_m = re.search(r"(?:problem|defect|issue|complaint|found|observed):\s*([^\.\n]+)", text, re.IGNORECASE) or \
                     re.search(r"\b(broken seal|broken|cracked|discoloration|wrong colou?r|contamination|particulate|damaged packaging|counterfeit|bent needle|leak(?:ing)?)\b", text, re.IGNORECASE)
            photo_m = any(w in text.lower() for w in ["photo", "picture", "image", "photograph", "attached image"])

            pqc_obj = PQCExtraction(
                product=_make_field(prod_m.group(1) if prod_m else None),
                lot_number=_make_field(lot_m.group(1) if lot_m else None),
                problem=_make_field(prob_m.group(1) if prob_m else None),
                photo_mentioned=_make_field("Yes" if photo_m else None),
            )
            facts_count = sum(
                1 for _, f in pqc_obj.model_dump().items()
                if isinstance(f, dict) and f.get("value") and f.get("value") != "Not stated"
            )
            result = ExtractionResult(
                category=ClassificationCategory.PQC,
                pqc=pqc_obj,
                facts_count=facts_count,
                summary=f"Heuristic PQC extraction completed ({facts_count} fact(s) identified).",
            )
            return result, "heuristic-extraction-engine-v1"

        elif category == ClassificationCategory.MI:
            q_m = re.search(r"(?:question|inquiry|asking|please provide|how to|what is the):\s*([^\.\n\?]+(?:\?|$))", text, re.IGNORECASE) or \
                  re.search(r"(?:can i take|how should i take|what is the recommended dosage[^\.\n\?]*\?)", text, re.IGNORECASE)
            prod_m = re.search(r"(?:regarding|about|for|product)\s+([A-Z][A-Za-z0-9\-_]+)", text) or \
                     re.search(r"\b(Solution\s+[A-Z]|Drug\s+[A-Z]|Med-[A-Z]|Vaccine\s+[A-Z0-9]+)\b", text, re.IGNORECASE)

            # If question regex didn't catch full line, look for first line ending in ? or containing inquiry
            q_val = q_m.group(0) if q_m else None
            if not q_val:
                for line in text.splitlines():
                    if "?" in line or any(k in line.lower() for k in ["dosage", "interaction", "how to take", "administer"]):
                        q_val = line.strip()
                        break

            mi_obj = MIExtraction(
                questions_asked=_make_field(q_val),
                product_topic=_make_field(prod_m.group(1) if prod_m else None),
            )
            facts_count = sum(
                1 for _, f in mi_obj.model_dump().items()
                if isinstance(f, dict) and f.get("value") and f.get("value") != "Not stated"
            )
            result = ExtractionResult(
                category=ClassificationCategory.MI,
                mi=mi_obj,
                facts_count=facts_count,
                summary=f"Heuristic MI extraction completed ({facts_count} fact(s) identified).",
            )
            return result, "heuristic-extraction-engine-v1"

        else:
            return ExtractionResult(
                category=ClassificationCategory.NOT_RELEVANT,
                facts_count=0,
                summary="Document classified as NOT_RELEVANT; no safety, quality, or medical facts to extract.",
            ), "heuristic-extraction-engine-v1"

    # ─────────────────────────────────────────────────────────────────────────
    # Extraction: Public extract_facts
    # ─────────────────────────────────────────────────────────────────────────

    def extract_facts(
        self,
        document_content: str,
        category: ClassificationCategory,
    ) -> Tuple[ExtractionResult, str]:
        """
        Extracts structured facts for a given category.
        Tries Gemini first, safely falling back to heuristic engine on any error.
        """
        if self.api_key and GENAI_AVAILABLE and category in [
            ClassificationCategory.ICSR,
            ClassificationCategory.PQC,
            ClassificationCategory.MI,
        ]:
            try:
                return self._extract_with_gemini(document_content, category)
            except (json.JSONDecodeError, ValidationError) as exc:
                logger.warning(
                    "Extraction validation failed (%s). Using heuristic fallback. Error: %s",
                    type(exc).__name__,
                    exc,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Gemini extraction call failed (%s: %s). Using heuristic fallback.",
                    type(exc).__name__,
                    exc,
                )

        return self._heuristic_fallback_extract(document_content, category)

    # ─────────────────────────────────────────────────────────────────────────
    # Extraction: Public extract_and_store
    # ─────────────────────────────────────────────────────────────────────────

    def extract_and_store(
        self,
        db: Session,
        document_id: int,
        category: Optional[Union[ClassificationCategory, str]] = None,
    ) -> ExtractResponse:
        """
        Runs fact extraction on a document and persists all extracted facts to the database.
        """
        start_time = time.monotonic()
        doc = InboxRepository.get_document_by_id(db, document_id)
        if not doc:
            raise ValueError(f"Document with ID {document_id} not found in database.")

        # 1. Resolve Category
        resolved_category: ClassificationCategory = ClassificationCategory.NOT_RELEVANT
        if category:
            resolved_category = (
                category
                if isinstance(category, ClassificationCategory)
                else ClassificationCategory(str(category))
            )
        else:
            # Check document classifications
            doc_classifications = InboxRepository.get_classifications(db, document_id=document_id)
            if doc_classifications:
                resolved_category = ClassificationCategory(doc_classifications[0].category)
            elif doc.email_id:
                email_classifications = InboxRepository.get_classifications(db, email_id=doc.email_id)
                if email_classifications:
                    resolved_category = ClassificationCategory(email_classifications[0].category)
            
            # If still undetermined, classify the document text
            if resolved_category == ClassificationCategory.NOT_RELEVANT and (doc.extracted_text or "").strip():
                classify_res, _ = self.classify(extracted_text=doc.extracted_text or "")
                resolved_category = classify_res.primary_category

        # 2. Prepare content
        content_parts = []
        if doc.extracted_text:
            content_parts.append(doc.extracted_text)
        if doc.email and doc.email.body:
            content_parts.append(f"Email Body:\n{doc.email.body}")
        
        full_content = "\n\n".join(content_parts) if content_parts else f"Document: {doc.filename}"

        # 3. Extract Facts
        result, model_used = self.extract_facts(
            document_content=full_content,
            category=resolved_category,
        )

        # 4. Persist Facts to Database
        InboxRepository.clear_facts_by_document(db, document_id=document_id)
        stored_count = 0

        # Flatten sections and persist every field
        if result.icsr:
            sections = [
                ("patient", result.icsr.patient),
                ("reporter", result.icsr.reporter),
                ("product", result.icsr.product),
                ("reaction", result.icsr.reaction),
                ("severity", result.icsr.severity),
                ("narrative", result.icsr.narrative),
            ]
            for sec_name, sec_obj in sections:
                for field_key, field_val in sec_obj.model_dump().items():
                    if isinstance(field_val, dict):
                        val_str = field_val.get("value", "Not stated")
                        conf = field_val.get("confidence", 0.0)
                        src_ref = field_val.get("source_reference", "Not stated")
                        src_type = doc.document_type or FactSourceType.PDF_TEXT.value

                        InboxRepository.add_extracted_fact(
                            db=db,
                            document_id=document_id,
                            category=resolved_category,
                            field_name=f"{sec_name}.{field_key}",
                            field_value=val_str,
                            confidence=conf,
                            source_type=src_type,
                            source_reference=src_ref,
                        )
                        stored_count += 1

        elif result.pqc:
            for field_key, field_val in result.pqc.model_dump().items():
                if isinstance(field_val, dict):
                    val_str = field_val.get("value", "Not stated")
                    conf = field_val.get("confidence", 0.0)
                    src_ref = field_val.get("source_reference", "Not stated")
                    src_type = doc.document_type or FactSourceType.PDF_TEXT.value

                    InboxRepository.add_extracted_fact(
                        db=db,
                        document_id=document_id,
                        category=resolved_category,
                        field_name=field_key,
                        field_value=val_str,
                        confidence=conf,
                        source_type=src_type,
                        source_reference=src_ref,
                    )
                    stored_count += 1

        elif result.mi:
            for field_key, field_val in result.mi.model_dump().items():
                if isinstance(field_val, dict):
                    val_str = field_val.get("value", "Not stated")
                    conf = field_val.get("confidence", 0.0)
                    src_ref = field_val.get("source_reference", "Not stated")
                    src_type = doc.document_type or FactSourceType.PDF_TEXT.value

                    InboxRepository.add_extracted_fact(
                        db=db,
                        document_id=document_id,
                        category=resolved_category,
                        field_name=field_key,
                        field_value=val_str,
                        confidence=conf,
                        source_type=src_type,
                        source_reference=src_ref,
                    )
                    stored_count += 1

        # 5. Update Document Status & Audit Log
        InboxRepository.update_document_processing(
            db=db,
            document_id=document_id,
            status=ProcessingStatus.COMPLETED,
        )

        elapsed = round(time.monotonic() - start_time, 3)

        InboxRepository.log_event(
            db=db,
            document_id=document_id,
            email_id=doc.email_id,
            event="AI_EXTRACTION_COMPLETED",
            details=(
                f"Category: {resolved_category.value} | "
                f"Model: {model_used} | "
                f"Facts Stored: {stored_count} | "
                f"Time: {elapsed}s"
            ),
        )

        logger.info(
            "extract_and_store complete — doc_id=%s category=%s facts=%d model=%s time=%.3fs",
            document_id,
            resolved_category.value,
            stored_count,
            model_used,
            elapsed,
        )

        return ExtractResponse(
            success=True,
            document_id=document_id,
            category=resolved_category,
            extraction=result,
            facts_stored=stored_count,
            processing_time=elapsed,
            model_used=model_used,
            error=None,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Public: get_stored_facts — read back persisted facts as structured JSON
    # ─────────────────────────────────────────────────────────────────────────

    def get_stored_facts(
        self,
        db: Session,
        document_id: int,
        category: Optional[str] = None,
    ) -> StoredFactsResponse:
        """
        Retrieves all extracted facts stored in the database for a document and
        reconstructs a typed ExtractionResult (ICSR / PQC / MI) from the flat rows.

        Args:
            db:           SQLAlchemy session.
            document_id:  ID of the document whose facts to retrieve.
            category:     Optional category filter (``"ICSR"``, ``"PQC"``, ``"MI"``).

        Returns:
            ``StoredFactsResponse`` containing:
            - ``facts``:      Flat list of every ``StoredFactItem`` (one per DB row).
            - ``structured``: Typed ``ExtractionResult`` rebuilt from those rows.
            - ``facts_count``: Count of stated (non-'Not stated') facts.

        Raises:
            ValueError: If the document does not exist.
        """
        doc = InboxRepository.get_document_by_id(db, document_id)
        if not doc:
            raise ValueError(f"Document with ID {document_id} not found in database.")

        # ── 1. Fetch raw rows ────────────────────────────────────────────────
        cat_filter: Optional[Union[ClassificationCategory, str]] = None
        if category:
            try:
                cat_filter = ClassificationCategory(category.upper())
            except ValueError:
                cat_filter = category  # pass through; repository handles gracefully

        raw_facts = InboxRepository.get_facts_by_document(
            db=db,
            document_id=document_id,
            category=cat_filter,
        )

        # ── 2. Build flat StoredFactItem list ────────────────────────────────
        fact_items = [StoredFactItem.model_validate(f) for f in raw_facts]

        stated_count = sum(
            1 for f in fact_items
            if f.field_value and f.field_value.strip().lower() != "not stated"
        )

        # ── 3. Determine dominant category ──────────────────────────────────
        cats_present = {f.category for f in fact_items}
        dominant_cat: Optional[str] = category  # honour explicit filter first
        if not dominant_cat and len(cats_present) == 1:
            dominant_cat = next(iter(cats_present))
        elif not dominant_cat and cats_present:
            # Multiple categories — pick highest priority
            for pcat in _CATEGORY_PRIORITY:
                if pcat.value in cats_present:
                    dominant_cat = pcat.value
                    break

        # ── 4. Reconstruct typed ExtractionResult ────────────────────────────
        structured: Optional[ExtractionResult] = None

        if dominant_cat and dominant_cat in ("ICSR", "PQC", "MI"):
            # Build a lookup: field_name → ExtractedField
            def _field(name: str) -> ExtractedField:
                """Look up a fact by field_name; return default 'Not stated' if absent."""
                for f in fact_items:
                    if f.field_name == name and f.category == dominant_cat:
                        return ExtractedField(
                            value=f.field_value or "Not stated",
                            confidence=f.confidence if f.confidence is not None else 0.0,
                            source_reference=f.source_reference or "Not stated",
                        )
                return ExtractedField()

            if dominant_cat == "ICSR":
                icsr_obj = ICSRExtraction(
                    patient=PatientInfo(
                        age=_field("patient.age"),
                        sex=_field("patient.sex"),
                        weight=_field("patient.weight"),
                        height=_field("patient.height"),
                        relevant_history=_field("patient.relevant_history"),
                    ),
                    reporter=ReporterInfo(
                        name=_field("reporter.name"),
                        role=_field("reporter.role"),
                        country=_field("reporter.country"),
                    ),
                    product=ProductInfo(
                        name=_field("product.name"),
                        dose=_field("product.dose"),
                        route=_field("product.route"),
                        start_date=_field("product.start_date"),
                        stop_date=_field("product.stop_date"),
                    ),
                    reaction=ReactionInfo(
                        reaction=_field("reaction.reaction"),
                        start_date=_field("reaction.start_date"),
                        outcome=_field("reaction.outcome"),
                    ),
                    severity=SeverityInfo(
                        serious=_field("severity.serious"),
                        death=_field("severity.death"),
                        hospitalization=_field("severity.hospitalization"),
                        life_threatening=_field("severity.life_threatening"),
                        other_severity=_field("severity.other_severity"),
                    ),
                    narrative=NarrativeInfo(
                        case_summary=_field("narrative.case_summary"),
                    ),
                )
                structured = ExtractionResult(
                    category=ClassificationCategory.ICSR,
                    icsr=icsr_obj,
                    facts_count=stated_count,
                    summary=f"{stated_count} ICSR fact(s) retrieved from database.",
                )

            elif dominant_cat == "PQC":
                pqc_obj = PQCExtraction(
                    product=_field("product"),
                    lot_number=_field("lot_number"),
                    problem=_field("problem"),
                    photo_mentioned=_field("photo_mentioned"),
                )
                structured = ExtractionResult(
                    category=ClassificationCategory.PQC,
                    pqc=pqc_obj,
                    facts_count=stated_count,
                    summary=f"{stated_count} PQC fact(s) retrieved from database.",
                )

            elif dominant_cat == "MI":
                mi_obj = MIExtraction(
                    questions_asked=_field("questions_asked"),
                    product_topic=_field("product_topic"),
                )
                structured = ExtractionResult(
                    category=ClassificationCategory.MI,
                    mi=mi_obj,
                    facts_count=stated_count,
                    summary=f"{stated_count} MI fact(s) retrieved from database.",
                )

        logger.info(
            "get_stored_facts — doc_id=%s category=%s facts=%d stated=%d",
            document_id,
            dominant_cat,
            len(fact_items),
            stated_count,
        )

        return StoredFactsResponse(
            document_id=document_id,
            category=dominant_cat,
            facts=fact_items,
            structured=structured,
            facts_count=stated_count,
            model_used=None,  # not stored per-document; omit from read-back
        )


# ── Module-level singleton (lazy API key resolution at startup) ───────────────
ai_service = AIService()
