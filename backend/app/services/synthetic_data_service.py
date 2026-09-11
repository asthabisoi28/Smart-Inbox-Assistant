"""
Synthetic Data Generation Service for Smart Inbox Assistant.
Generates 100% fictional test data covering:
- 10+ emails (16 total)
- 5+ digital PDFs (7 total)
- 2+ scanned/handwritten-style PDFs (2 total)
- 5+ fictional article PDFs (5 total)
- 2+ non-English PDFs (2 total: Spanish, French)
- 2+ quality complaints (3 total)
- 2+ info requests (2 total)
- 1+ irrelevant marketing email (1 total)

IMPORTANT: ALL PATIENTS, DOCTORS, PRODUCTS, AND INCIDENTS ARE 100% SYNTHETIC AND FICTIONAL.
"""

import json
import uuid
import zipfile
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import format_datetime
import fitz  # PyMuPDF
from PIL import Image, ImageDraw
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.models.enums import DocumentType, ProcessingStatus
from app.repositories.inbox_repository import InboxRepository
from app.services.email_service import ATTACHMENTS_DIR

# On-disk catalog of 100% fictional emails/PDFs used by tests and the batch script.
SYNTHETIC_FIXTURES_DIR = (
    Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures" / "synthetic"
)


class SyntheticDataService:
    """Generates comprehensive synthetic test data without real patient information."""

    @staticmethod
    def _create_digital_pdf(file_path: Path, title: str, text_body: str) -> str:
        """Generates a standard digital PDF file."""
        file_path.parent.mkdir(parents=True, exist_ok=True)
        if file_path.exists():
            try:
                file_path.unlink()
            except Exception:
                pass
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        page.insert_text((50, 50), title, fontsize=14)
        
        # Line wrap basic text
        y = 90
        for line in text_body.split("\n"):
            page.insert_text((50, y), line, fontsize=10)
            y += 18
            
        doc.save(str(file_path))
        doc.close()
        return str(file_path)

    @staticmethod
    def _create_scanned_pdf(file_path: Path, header_text: str, body_text: str) -> str:
        """Generates a scanned/handwritten-style raster image PDF."""
        file_path.parent.mkdir(parents=True, exist_ok=True)
        if file_path.exists():
            try:
                file_path.unlink()
            except Exception:
                pass
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)

        # Draw simulated handwritten/scanned form on PIL Image
        img = Image.new("RGB", (600, 750), color=(252, 252, 248))
        draw = ImageDraw.Draw(img)
        
        # Border box
        draw.rectangle([(20, 20), (580, 730)], outline=(80, 80, 80), width=2)
        draw.text((40, 40), header_text, fill=(30, 30, 90))
        
        y = 90
        for line in body_text.split("\n"):
            draw.text((40, y), line, fill=(20, 20, 20))
            y += 24

        img_bytes_io = fitz.io.BytesIO()
        img.save(img_bytes_io, format="PNG")
        img_bytes = img_bytes_io.getvalue()

        page.insert_image(fitz.Rect(30, 30, 582, 762), stream=img_bytes)
        doc.save(str(file_path))
        doc.close()
        return str(file_path)

    @staticmethod
    def _create_article_pdf(file_path: Path, journal_name: str, title: str, abstract: str, body_left: str, body_right: str) -> str:
        """Generates a multi-column published journal article PDF."""
        file_path.parent.mkdir(parents=True, exist_ok=True)
        if file_path.exists():
            try:
                file_path.unlink()
            except Exception:
                pass
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)

        # Journal header banner
        page.insert_text((50, 40), journal_name, fontsize=9)
        page.draw_line(fitz.Point(50, 48), fitz.Point(562, 48), color=(0.2, 0.2, 0.2), width=1)

        # Article Title & Abstract
        page.insert_text((50, 70), title, fontsize=13)
        page.insert_text((50, 95), f"ABSTRACT: {abstract}", fontsize=9)

        # Divider line
        page.draw_line(fitz.Point(50, 140), fitz.Point(562, 140), color=(0.7, 0.7, 0.7), width=0.5)

        # Two-column layout
        y_left = 160
        for line in body_left.split("\n"):
            page.insert_text((50, y_left), line, fontsize=8.5)
            y_left += 14

        y_right = 160
        for line in body_right.split("\n"):
            page.insert_text((310, y_right), line, fontsize=8.5)
            y_right += 14

        doc.save(str(file_path))
        doc.close()
        return str(file_path)

    @staticmethod
    def _create_docx(file_path: Path, title: str, body_text: str) -> str:
        """Writes a tiny fictional .docx (ZIP + document.xml) for marketing fixtures."""
        document_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f"<w:body><w:p><w:r><w:t>{title}. {body_text}</w:t></w:r></w:p></w:body>"
            "</w:document>"
        )
        content_types = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            "</Types>"
        )
        rels = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="word/document.xml"/>'
            "</Relationships>"
        )
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(file_path, "w") as zf:
            zf.writestr("[Content_Types].xml", content_types)
            zf.writestr("_rels/.rels", rels)
            zf.writestr("word/document.xml", document_xml)
        return str(file_path)

    @classmethod
    def _synthetic_cases(cls) -> List[Dict[str, Any]]:
        """Canonical fictional inbox cases. All patients/products are synthetic."""
        return [
            # Case 1: ICSR - Digital PDF
            {
                "msg_id": "<syn-case-001@health.syn>",
                "sender": "dr.patel@metro-pulmonary.syn",
                "subject": "URGENT: Adverse Event Report - Patient #SYN-9001 CardioVax",
                "date": datetime(2026, 9, 1, 9, 0),
                "body": "Dear Drug Safety Team,\nReporting acute bronchospasm for 54yo male post CardioVax administration. PDF attached.",
                "pdf_filename": "ICSR_Report_SYN_9001_CardioVax.pdf",
                "pdf_type": "digital",
                "pdf_title": "INDIVIDUAL CASE SAFETY REPORT (ICSR)",
                "pdf_text": (
                    "PATIENT DETAILS:\nID: SYN-9001 | Age: 54 | Sex: Male | Weight: 78 kg | History: Asthma\n"
                    "REPORTER: Dr. Rajesh Patel (Physician, USA)\n"
                    "PRODUCT: CardioVax 20mg | Dose: 20mg IM | Lot: CV-88219 | Start: 2026-09-01\n"
                    "REACTION: Acute bronchospasm and severe urticaria | Start: 2026-09-01 | Outcome: Recovered\n"
                    "SEVERITY: Serious = Yes | Hospitalization = Yes | Life-Threatening = No\n"
                    "NARRATIVE: Patient developed severe bronchospasm 25 minutes after injection. Administered epinephrine."
                ),
                "tags": ["email", "digital_pdf", "icsr"],
            },
            # Case 2: PQC - Digital PDF
            {
                "msg_id": "<syn-case-002@health.syn>",
                "sender": "pharmacy@stjudes.syn",
                "subject": "Product Quality Complaint: Fractured Syringes (Lot #PF-4401)",
                "date": datetime(2026, 9, 1, 10, 30),
                "body": "Quality Assurance Team,\nFound 4 cracked syringe barrels of HepaGuard 5000 IU. Inspection form attached.",
                "pdf_filename": "Quality_Complaint_Form_PF4401.pdf",
                "pdf_type": "digital",
                "pdf_title": "PRODUCT QUALITY COMPLAINT (PQC) FORM",
                "pdf_text": (
                    "PRODUCT: HepaGuard 5000 IU Pre-Filled Syringes\n"
                    "BATCH/LOT NUMBER: PF-4401\n"
                    "PROBLEM: 4 cracked glass syringe barrels in box. Leakage observed prior to use.\n"
                    "PHOTO MENTIONED: Yes (photos attached to incident log)\n"
                    "REPORTER: Elena Rostova, PharmD (Lead Pharmacist)"
                ),
                "tags": ["email", "digital_pdf", "pqc", "quality_complaint"],
            },
            # Case 3: MI - Plain Text Inquiry (No PDF)
            {
                "msg_id": "<syn-case-003@health.syn>",
                "sender": "nurse.claire@community.syn",
                "subject": "Medical Information Inquiry: Dosing Adjustments for NeuroCalm",
                "date": datetime(2026, 9, 2, 8, 15),
                "body": (
                    "Hello Medical Affairs,\n\n"
                    "What is the recommended dosage titration for NeuroCalm 25mg in adult patients with moderate renal impairment?\n"
                    "Product/Topic: NeuroCalm 25mg\n"
                    "Question: Is initial dose reduction required for eGFR < 45 mL/min?\n\n"
                    "Thank you,\nClaire Thompson, RN"
                ),
                "pdf_filename": None,
                "tags": ["email", "mi", "info_request"],
            },
            # Case 4: Marketing - Ignored .docx
            {
                "msg_id": "<syn-case-004@health.syn>",
                "sender": "events@expo.syn",
                "subject": "Invitation: Annual Healthcare Innovations Expo 2026",
                "date": datetime(2026, 9, 2, 11, 0),
                "body": "Join us at the 2026 Healthcare Expo. Attached is our brochure agenda.",
                "pdf_filename": None,
                "docx_filename": "conference_agenda_brochure.docx",
                "docx_title": "Healthcare Innovations Expo 2026 Brochure",
                "docx_text": "Fictional conference agenda. Early-bird registration. No patient data.",
                "tags": ["email", "marketing", "not_relevant"],
            },
            # Case 5: ICSR + PQC Combo - Digital PDF
            {
                "msg_id": "<syn-case-005@health.syn>",
                "sender": "dr.zhang@regional.syn",
                "subject": "Rheumaject Auto-Injector Needle Failure + Patient Injection Site Hematoma",
                "date": datetime(2026, 9, 2, 14, 20),
                "body": "Reporting Rheumaject autoinjector needle shield failure resulting in patient thigh hematoma.",
                "pdf_filename": "Device_Failure_and_Injury_Report.pdf",
                "pdf_type": "digital",
                "pdf_title": "COMBINED DEVICE MALFUNCTION & SAFETY INCIDENT REPORT",
                "pdf_text": (
                    "PATIENT: Female | Age: 62 | ID: SYN-9005\n"
                    "PRODUCT: Rheumaject 50mg Auto-Injector | Lot: RJ-99381\n"
                    "PROBLEM: Needle shield stuck during self-administration.\n"
                    "REACTION: Severe subcutaneous hematoma at injection site.\n"
                    "SEVERITY: Serious = Yes | Hospitalization = No | Life-Threatening = No\n"
                    "NARRATIVE: Mechanical device failure caused needle bending and severe tissue trauma."
                ),
                "tags": ["email", "digital_pdf", "icsr", "pqc", "quality_complaint"],
            },
            # Case 6: ICSR - Scanned PDF 1
            {
                "msg_id": "<syn-case-006@health.syn>",
                "sender": "er.triage@city-emergency.syn",
                "subject": "Scanned Anaphylaxis Case Form - Patient #SYN-9006 VaxuShield",
                "date": datetime(2026, 9, 3, 7, 45),
                "body": "Attached is the scanned emergency intake sheet for an anaphylaxis case following VaxuShield.",
                "pdf_filename": "Scanned_Incident_Form_VaxuShield.pdf",
                "pdf_type": "scanned",
                "pdf_title": "EMERGENCY TRIAGE INTAKE SHEET (SCANNED)",
                "pdf_text": (
                    "EMERGENCY ADMISSION FORM (SCANNED IMAGE)\n"
                    "Patient: SYN-9006 | Age: 38 | Sex: Female\n"
                    "Suspect Drug: VaxuShield 0.5mL (Lot #VX-1029)\n"
                    "Reaction: Anaphylactic shock, hypotension 80/50.\n"
                    "Severity: Life-threatening = Yes | Hospitalization = Yes\n"
                    "Outcome: Intubated, stabilized in ICU."
                ),
                "tags": ["email", "scanned_pdf", "icsr"],
            },
            # Case 7: ICSR - Scanned PDF 2
            {
                "msg_id": "<syn-case-007@health.syn>",
                "sender": "dr.hassan@urgentcare.syn",
                "subject": "Handwritten Emergency Note - Patient #SYN-9007 PulmoMist",
                "date": datetime(2026, 9, 3, 10, 0),
                "body": "Scanned handwritten physician note for paradoxical bronchospasm incident.",
                "pdf_filename": "Handwritten_Emergency_Triage_Note.pdf",
                "pdf_type": "scanned",
                "pdf_title": "PHYSICIAN HANDWRITTEN TRIAGE NOTE (SCANNED)",
                "pdf_text": (
                    "CLINICAL NOTE (HANDWRITTEN STYLE)\n"
                    "Patient: SYN-9007 | Age: 29 | Sex: Male\n"
                    "Drug: PulmoMist Inhaler (Lot #PM-5049)\n"
                    "Reaction: Paradoxical bronchospasm immediately after puff 1.\n"
                    "Reporter: Dr. Tariq Hassan | Urgent Care Center"
                ),
                "tags": ["email", "scanned_pdf", "icsr"],
            },
            # Case 8: Journal Article 1 - PDF Article
            {
                "msg_id": "<syn-case-008@health.syn>",
                "sender": "editor@journal-safety.syn",
                "subject": "Journal Article: Phase III Clinical Safety Analysis of CardioVax",
                "date": datetime(2026, 9, 3, 13, 0),
                "body": "Enclosed preprint article on CardioVax safety profile in 1,200 subjects.",
                "pdf_filename": "Article_CardioVax_Phase3_Safety.pdf",
                "pdf_type": "article",
                "journal": "JOURNAL OF PHARMACEUTICAL SAFETY | VOL. 14, 2026",
                "title": "Phase III Clinical Safety Evaluation of CardioVax in Adult Cohorts",
                "abstract": "Evaluation of adverse event frequency across 1,200 randomized trial participants.",
                "body_left": "1. Introduction\nCardioVax demonstrated 94% efficacy.\nSafety reporting identified 12 mild reaction cases.\nNo fatal incidents recorded during trial.",
                "body_right": "2. Safety Results\nIncidence of urticaria was 0.8%.\nAll cases resolved with standard therapy.\nConclusion: Favorable benefit-risk profile.",
                "tags": ["email", "article"],
            },
            # Case 9: Journal Article 2 - PDF Article
            {
                "msg_id": "<syn-case-009@health.syn>",
                "sender": "research@packaging.syn",
                "subject": "Article Reprint: HepaGuard Syringe Glass Fracture Mechanisms",
                "date": datetime(2026, 9, 3, 16, 30),
                "body": "Published research article analyzing glass strain defects in pre-filled syringe barrels.",
                "pdf_filename": "Article_HepaGuard_Packaging_Study.pdf",
                "pdf_type": "article",
                "journal": "INTERNATIONAL PACKAGING JOURNAL | VOL. 22, 2026",
                "title": "Structural Integrity and Defect Rates in Pre-Filled Glass Syringes",
                "abstract": "Root cause analysis of micro-fractures in pre-filled syringe barrels under thermal shock.",
                "body_left": "1. Background\nPackaging quality complaints (PQC) account for 15% of recalls.\nBatch PF-4401 showed elevated flange stress.",
                "body_right": "2. Quality Evaluation\nDefect rate: 0.03% in high-humidity storage.\nRecommend updated annealing protocol.",
                "tags": ["email", "article"],
            },
            # Case 10: Journal Article 3 - PDF Article
            {
                "msg_id": "<syn-case-010@health.syn>",
                "sender": "library@neurology.syn",
                "subject": "Publication: NeuroCalm Dosing Protocols in Impaired Renal Clearance",
                "date": datetime(2026, 9, 4, 9, 15),
                "body": "Medical literature publication regarding renal clearance and NeuroCalm pharmacokinetics.",
                "pdf_filename": "Article_NeuroCalm_Renal_Titration.pdf",
                "pdf_type": "article",
                "journal": "CLINICAL NEUROLOGY REVIEW | VOL. 39, 2026",
                "title": "Pharmacokinetics of NeuroCalm in Renal Impairment Cohorts",
                "abstract": "Systematic review of dosage adjustments for central nervous system agents.",
                "body_left": "1. Introduction\nNeuroCalm is eliminated via glomerular filtration.\nQuery regarding titration in eGFR < 45 mL/min.",
                "body_right": "2. Recommendations\nInitial dose 12.5mg daily for stage 3 CKD.\nMonitor plasma creatinine weekly.",
                "tags": ["email", "article"],
            },
            # Case 11: Journal Article 4 - PDF Article
            {
                "msg_id": "<syn-case-011@health.syn>",
                "sender": "info@aerosol.syn",
                "subject": "Reprint: PulmoMist Actuator Clogging Under High Humidity",
                "date": datetime(2026, 9, 4, 11, 45),
                "body": "Journal article detailing valve clogging issues in dry-powder vs meter-dose inhalers.",
                "pdf_filename": "Article_PulmoMist_Valve_Mechanisms.pdf",
                "pdf_type": "article",
                "journal": "AEROSOL MEDICINE & PULMONOLOGY | VOL. 18, 2026",
                "title": "Nozzle Clogging and Delivery Uniformity of Metered Inhalers",
                "abstract": "Investigation of propellant crystallization causing valve obstruction in PulmoMist.",
                "body_left": "1. Problem Definition\nQuality complaints regarding clogged nozzles.\nBatch PM-5049 evaluated.",
                "body_right": "2. Remediation\nClean nozzle orifice with alcohol swab.\nRedesign actuator cap orifice.",
                "tags": ["email", "article"],
            },
            # Case 12: Journal Article 5 - PDF Article
            {
                "msg_id": "<syn-case-012@health.syn>",
                "sender": "oncology@reviews.syn",
                "subject": "Review Paper: OncoClear Cold-Chain Storage Stability Protocols",
                "date": datetime(2026, 9, 4, 14, 0),
                "body": "Medical information literature review regarding OncoClear temperature excursions.",
                "pdf_filename": "Article_OncoClear_Storage_Stability.pdf",
                "pdf_type": "article",
                "journal": "ONCOLOGY PHARMACY JOURNAL | VOL. 31, 2026",
                "title": "Thermal Stability and Cold-Chain Maintenance for OncoClear Infusions",
                "abstract": "Stability data for OncoClear exposure up to 24 hours at room temperature.",
                "body_left": "1. Introduction\nFrequent medical queries regarding accidental thawing.\nProduct: OncoClear 100mg vial.",
                "body_right": "2. Stability Findings\nPotency remains >98% if kept below 25 deg C for under 12h.",
                "tags": ["email", "article"],
            },
            # Case 13: Non-English Spanish - Digital PDF
            {
                "msg_id": "<syn-case-013@health.syn>",
                "sender": "dr.fernandez@hospital-madrid.syn",
                "subject": "Informe de Seguridad: Reaccion Adversa CardioVax Madrid",
                "date": datetime(2026, 9, 4, 16, 30),
                "body": "Estimado equipo de farmacovigilancia, adjunto informe medico de evento adverso CardioVax.",
                "pdf_filename": "Informe_Caso_Clinico_CardioVax_ES.pdf",
                "pdf_type": "digital",
                "pdf_title": "INFORME DE FARMACOVIGILANCIA (ESPANOL)",
                "pdf_text": (
                    "DATOS DEL PACIENTE:\nID: SYN-9013 | Edad: 47 anos | Sexo: Femenino | Historia: Hipertension\n"
                    "MEDICAMENTO SOSPECHOSO: CardioVax 20mg (Lote: CV-88219)\n"
                    "REACCION ADVERSA: Erupcion cutanea severa, prurito intenso y fiebre de 38.5 C.\n"
                    "RESULTADO: Recuperado tras administracion de antihistaminicos.\n"
                    "INFORMADOR: Dra. Maria Fernandez (Hospital Madrid)"
                ),
                "tags": ["email", "digital_pdf", "non_english", "icsr"],
            },
            # Case 14: Non-English French - Digital PDF
            {
                "msg_id": "<syn-case-014@health.syn>",
                "sender": "dr.dupont@hopital-paris.syn",
                "subject": "Rapport de Pharmacovigilance: Defaut Flacon NeuroCalm Paris",
                "date": datetime(2026, 9, 5, 8, 0),
                "body": "Veuillez trouver ci-joint le rapport de pharmacovigilance et reclamation qualite NeuroCalm.",
                "pdf_filename": "Rapport_Pharmacovigilance_NeuroCalm_FR.pdf",
                "pdf_type": "digital",
                "pdf_title": "RAPPORT DE PHARMACOVIGILANCE ET RECLAMATION QUALITE",
                "pdf_text": (
                    "INFORMATION PATIENT & PRODUIT:\n"
                    "Produit: NeuroCalm 25mg | Lot: NC-1209 | Patient: Homme 51 ans (SYN-9014)\n"
                    "PROBLEME QUALITE: Flacon fisse avec fuite de solution.\n"
                    "EFFET INDESIRABLE: Vertiges et somnolence severe apres ingestion.\n"
                    "RAPPORTEUR: Dr. Jean Dupont (Hopital de Paris)"
                ),
                "tags": ["email", "digital_pdf", "non_english", "pqc", "quality_complaint", "icsr"],
            },
            # Case 15: PQC - Digital PDF
            {
                "msg_id": "<syn-case-015@health.syn>",
                "sender": "qa@pulmo-health.syn",
                "subject": "Product Quality Complaint: Clogged Valve PulmoMist Inhaler (Lot #PM-5049)",
                "date": datetime(2026, 9, 5, 10, 15),
                "body": "Quality defect report for PulmoMist inhaler actuator clogging.",
                "pdf_filename": "Quality_Complaint_PulmoMist_PM5049.pdf",
                "pdf_type": "digital",
                "pdf_title": "PRODUCT QUALITY COMPLAINT - ACTUATOR DEFECT",
                "pdf_text": (
                    "PRODUCT: PulmoMist Inhaler 100mcg\n"
                    "BATCH/LOT NUMBER: PM-5049\n"
                    "PROBLEM: Actuator nozzle completely clogged, zero dose discharge on depression.\n"
                    "PHOTO MENTIONED: Yes (photos included in QA dossier)\n"
                    "REPORTER: Pharmacist Mark Vance"
                ),
                "tags": ["email", "digital_pdf", "pqc", "quality_complaint"],
            },
            # Case 16: Second Medical Information request
            {
                "msg_id": "<syn-case-016@health.syn>",
                "sender": "pharmacist.lee@oncology-hub.syn",
                "subject": "Medical Information Request: OncoClear room-temperature excursion",
                "date": datetime(2026, 9, 5, 12, 40),
                "body": (
                    "Hello Medical Information,\n\n"
                    "Product/Topic: OncoClear 100mg vial\n"
                    "Question: If a carton is left at 22 C for 9 hours during transfer, can it be returned to 2-8 C storage?\n"
                    "Please confirm whether potency remains acceptable and if a replacement vial is required.\n\n"
                    "Thank you,\nAlex Lee, RPh"
                ),
                "pdf_filename": None,
                "tags": ["email", "mi", "info_request"],
            },
        ]

    @classmethod
    def _write_case_pdf(cls, target_path: Path, case: Dict[str, Any]) -> DocumentType:
        pdf_type_str = case.get("pdf_type", "digital")
        if pdf_type_str == "scanned":
            cls._create_scanned_pdf(target_path, case.get("pdf_title", "SCANNED"), case.get("pdf_text", ""))
            return DocumentType.PDF_SCANNED
        if pdf_type_str == "article":
            cls._create_article_pdf(
                target_path,
                case.get("journal", "JOURNAL"),
                case.get("title", "ARTICLE"),
                case.get("abstract", "ABSTRACT"),
                case.get("body_left", "LEFT"),
                case.get("body_right", "RIGHT"),
            )
            return DocumentType.ARTICLE
        cls._create_digital_pdf(target_path, case.get("pdf_title", "REPORT"), case.get("pdf_text", ""))
        return DocumentType.PDF_DIGITAL

    @classmethod
    def coverage_counts(cls) -> Dict[str, int]:
        """Counts tagged synthetic cases for coverage assertions."""
        counts: Dict[str, int] = {}
        for case in cls._synthetic_cases():
            for tag in case.get("tags", []):
                counts[tag] = counts.get(tag, 0) + 1
        return counts

    @classmethod
    def write_fixture_catalog(cls, output_dir: Optional[Path] = None) -> Dict[str, Any]:
        """
        Writes fictional .eml, PDF, and marketing .docx files to the test fixtures directory.
        Never contains real patient information.
        """
        root = Path(output_dir) if output_dir else SYNTHETIC_FIXTURES_DIR
        emails_dir = root / "emails"
        pdf_dirs = {
            "digital": root / "pdfs" / "digital",
            "scanned": root / "pdfs" / "scanned",
            "article": root / "pdfs" / "articles",
            "non_english": root / "pdfs" / "non_english",
        }
        other_dir = root / "other"
        for d in [emails_dir, other_dir, *pdf_dirs.values()]:
            d.mkdir(parents=True, exist_ok=True)

        written: List[Dict[str, Any]] = []
        for idx, case in enumerate(cls._synthetic_cases(), start=1):
            pdf_bytes = None
            pdf_rel = None
            if case.get("pdf_filename"):
                pdf_type = case.get("pdf_type", "digital")
                dest_dir = pdf_dirs["scanned"] if pdf_type == "scanned" else (
                    pdf_dirs["article"] if pdf_type == "article" else pdf_dirs["digital"]
                )
                if "non_english" in case.get("tags", []):
                    dest_dir = pdf_dirs["non_english"]
                pdf_path = dest_dir / case["pdf_filename"]
                cls._write_case_pdf(pdf_path, case)
                pdf_bytes = pdf_path.read_bytes()
                pdf_rel = str(pdf_path.relative_to(root)).replace("\\", "/")

            docx_rel = None
            docx_bytes = None
            if case.get("docx_filename"):
                docx_path = other_dir / case["docx_filename"]
                cls._create_docx(docx_path, case.get("docx_title", "Brochure"), case.get("docx_text", ""))
                docx_bytes = docx_path.read_bytes()
                docx_rel = str(docx_path.relative_to(root)).replace("\\", "/")

            msg = MIMEMultipart()
            msg["From"] = case["sender"]
            msg["To"] = "safety-inbox@smart-inbox.syn"
            msg["Subject"] = case["subject"]
            msg["Date"] = format_datetime(case["date"])
            msg["Message-ID"] = case["msg_id"]
            msg.attach(MIMEText(case["body"], "plain", "utf-8"))
            if pdf_bytes and case.get("pdf_filename"):
                part = MIMEApplication(pdf_bytes, _subtype="pdf")
                part.add_header("Content-Disposition", "attachment", filename=case["pdf_filename"])
                msg.attach(part)
            if docx_bytes and case.get("docx_filename"):
                part = MIMEApplication(docx_bytes, _subtype="vnd.openxmlformats-officedocument.wordprocessingml.document")
                part.add_header("Content-Disposition", "attachment", filename=case["docx_filename"])
                msg.attach(part)

            eml_name = f"{idx:02d}_{case['msg_id'].strip('<>').split('@')[0]}.eml"
            eml_path = emails_dir / eml_name
            eml_path.write_bytes(msg.as_bytes())

            written.append({
                "index": idx,
                "message_id": case["msg_id"],
                "sender": case["sender"],
                "subject": case["subject"],
                "tags": case.get("tags", []),
                "email_file": f"emails/{eml_name}",
                "pdf_file": pdf_rel,
                "docx_file": docx_rel,
            })

        manifest = {
            "disclaimer": "ALL DATA IS 100% FICTIONAL. No real patient information.",
            "coverage": cls.coverage_counts(),
            "files": written,
        }
        (root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return {"success": True, "root": str(root), "emails": len(written), "coverage": manifest["coverage"]}

    @classmethod
    def generate_full_synthetic_suite(cls, db: Session) -> Dict[str, Any]:
        """
        Populates database with synthetic cases (emails + PDFs) across all required categories.
        """
        ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
        synthetic_cases = cls._synthetic_cases()

        ingested_count = 0
        docs_created = 0
        skipped_count = 0
        run_id = uuid.uuid4().hex[:8]

        for case in synthetic_cases:
            original_msg_id = case["msg_id"]
            unique_msg_id = original_msg_id.replace("@", f"-{run_id}@")

            existing = InboxRepository.get_email_by_message_id(db, unique_msg_id)
            if existing:
                skipped_count += 1
                continue

            email_rec = InboxRepository.create_email(
                db=db,
                sender=case["sender"],
                subject=case["subject"],
                body=case["body"],
                received_date=case["date"],
                message_id=unique_msg_id,
                status=ProcessingStatus.PENDING,
            )
            ingested_count += 1

            pdf_filename = case.get("pdf_filename")
            if pdf_filename:
                target_path = ATTACHMENTS_DIR / f"syn_{run_id}_{email_rec.id}_{pdf_filename}"
                doc_type = cls._write_case_pdf(target_path, case)
                InboxRepository.create_document(
                    db=db,
                    email_id=email_rec.id,
                    filename=pdf_filename,
                    file_path=str(target_path),
                    document_type=doc_type,
                    status=ProcessingStatus.PENDING,
                )
                docs_created += 1

            if case.get("docx_filename"):
                cls._create_docx(
                    ATTACHMENTS_DIR / f"syn_{run_id}_{email_rec.id}_{case['docx_filename']}",
                    case.get("docx_title", "Brochure"),
                    case.get("docx_text", ""),
                )

        return {
            "success": True,
            "emails_created": ingested_count,
            "emails_skipped": skipped_count,
            "documents_created": docs_created,
            "coverage": cls.coverage_counts(),
            "message": (
                f"Successfully generated synthetic test suite "
                f"({ingested_count} emails, {docs_created} PDFs, {skipped_count} skipped)."
            ),
        }

