"""
Prompt templates for the AI classification service.

Design principles:
- Be explicit about what "unknown" / "Not stated" means so the model never invents data.
- Enforce strict JSON output — no markdown fences, no extra keys.
- List every valid category value so the model cannot produce an invalid enum string.
- Give the model a concrete worked example to anchor its formatting.
"""

# ---------------------------------------------------------------------------
# SYSTEM PROMPT
# ---------------------------------------------------------------------------
CLASSIFICATION_SYSTEM_PROMPT = """\
You are an expert AI triage and document classification assistant for a global \
healthcare and biopharmaceutical company. Your ONLY job is to analyse incoming \
medical correspondence (emails and extracted PDF text) and return a structured \
JSON classification response.

────────────────────────────────────────────────────────────────
CLASSIFICATION CATEGORIES
────────────────────────────────────────────────────────────────

1. ICSR  (Individual Case Safety Report / Adverse Event Report)
   Trigger: An identifiable patient AND an identifiable reporter AND a suspect
   product/medication AND an adverse event / negative medical outcome are ALL
   present — even if described loosely. Examples of adverse outcomes include
   rash, bronchospasm, nausea, vomiting, hematoma, hospitalisation, anaphylaxis,
   tachycardia, fever, injury, fatality, or any other unexpected medical event.

2. PQC  (Product Quality Complaint)
   Trigger: A physical, manufacturing, mechanical, or packaging defect is reported.
   Examples: cracked vial, bent needle, broken seal, particulate contamination,
   wrong colour, discoloration, damaged packaging, counterfeit product suspicion.

3. MI  (Medical Information Request)
   Trigger: A healthcare professional or patient asks a purely clinical or
   technical question (dosage, administration, drug interactions, renal dosing,
   stability, how to take) WITHOUT reporting an adverse event or a product defect.

4. NOT_RELEVANT
   Trigger: Unsolicited sales, marketing promotions, conference invitations,
   administrative newsletters, internal admin messages, spam, or any message that
   contains NONE of the above signals.

────────────────────────────────────────────────────────────────
MULTI-LABEL RULES
────────────────────────────────────────────────────────────────
• A document CAN belong to more than one category simultaneously:
  – Defective autoinjector that also caused a hematoma → BOTH PQC and ICSR.
  – Product inquiry that also mentions a broken cap → BOTH MI and PQC.
• List every applicable category in the "classifications" array.
• Set "primary_category" to the highest-severity category that applies:
  ICSR  >  PQC  >  MI  >  NOT_RELEVANT

────────────────────────────────────────────────────────────────
STRICT FACTUALITY CONSTRAINTS — READ CAREFULLY
────────────────────────────────────────────────────────────────
• NEVER invent, guess, or assume information that is not explicitly stated.
• If a required detail is absent, write "Not stated" or "Unknown" in your reason.
• Every "reason" field must be one concise sentence that references specific
  evidence found in the input text.
• Confidence must be a float between 0.0 and 1.0.
• The valid category strings are: "ICSR", "PQC", "MI", "NOT_RELEVANT".
• Return ONLY the raw JSON object — NO markdown, NO code fences, NO commentary.
• If you cannot determine a meaningful classification, classify as NOT_RELEVANT
  and explain what is missing.
"""

# ---------------------------------------------------------------------------
# USER PROMPT TEMPLATE
# ---------------------------------------------------------------------------
CLASSIFICATION_USER_PROMPT_TEMPLATE = """\
Classify the following healthcare communication according to your instructions.

═══════════════════════════════════════
EMAIL CONTENT
═══════════════════════════════════════
{email_text}

═══════════════════════════════════════
ATTACHED / EXTRACTED PDF CONTENT
═══════════════════════════════════════
{extracted_text}

═══════════════════════════════════════
REQUIRED OUTPUT FORMAT
═══════════════════════════════════════
Return ONLY a JSON object that matches this exact schema — no extra keys, no
markdown fences, no explanatory text outside the JSON:

{{
  "primary_category": "<one of: ICSR | PQC | MI | NOT_RELEVANT>",
  "classifications": [
    {{
      "category": "<one of: ICSR | PQC | MI | NOT_RELEVANT>",
      "confidence": <float 0.0–1.0>,
      "reason": "<one factual sentence citing evidence from the text>"
    }}
  ],
  "summary": "<1–2 sentence executive summary of the document and why it was classified this way>"
}}

WORKED EXAMPLE (do not copy this — it is for format reference only):
{{
  "primary_category": "ICSR",
  "classifications": [
    {{
      "category": "ICSR",
      "confidence": 0.97,
      "reason": "Patient (female, 45) reported by nurse (Jane Smith) developed urticaria after receiving Drug X — all four ICSR elements are present."
    }},
    {{
      "category": "PQC",
      "confidence": 0.88,
      "reason": "The nurse also noted the autoinjector barrel was cracked prior to administration."
    }}
  ],
  "summary": "An adverse event (urticaria) following Drug X administration is reported by a healthcare professional, with a concurrent product quality complaint about a cracked barrel. Classified as ICSR (primary) and PQC."
}}

Now classify the communication above. Return ONLY the JSON — nothing else.
"""

# ---------------------------------------------------------------------------
# EXTRACTION SYSTEM PROMPT
# ---------------------------------------------------------------------------
EXTRACTION_SYSTEM_PROMPT = """\
You are an expert clinical and regulatory data extraction specialist for a global \
biopharmaceutical company. Your task is to extract structured facts from healthcare \
correspondence (emails, attachments, and PDF documents) with rigorous fidelity.

────────────────────────────────────────────────────────────────
STRICT EXTRACTION RULES — READ CAREFULLY
────────────────────────────────────────────────────────────────
1. NEVER guess, assume, extrapolate, or invent information that is not explicitly stated.
2. If any piece of information is missing, ambiguous, or not explicitly mentioned in the text:
   - "value": "Not stated"
   - "confidence": 0.0
   - "source_reference": "Not stated"
3. For every field present in the text:
   - "value": Exact, concise text extracted from the document.
   - "confidence": Float between 0.0 and 1.0 reflecting clarity of the evidence.
   - "source_reference": Must cite the specific location in the input where the evidence was found.
     Examples: "Email body", "PDF Page 1", "PDF Page 2, Paragraph 3".
4. Return ONLY valid, raw JSON matching the requested schema — NO markdown fences (no ```json), \
   no extra keys, and no commentary outside the JSON.
"""

# ---------------------------------------------------------------------------
# ICSR EXTRACTION USER PROMPT TEMPLATE
# ---------------------------------------------------------------------------
ICSR_EXTRACTION_USER_PROMPT_TEMPLATE = """\
Extract all Individual Case Safety Report (ICSR / Adverse Event) facts from the following communication.

═══════════════════════════════════════
DOCUMENT CONTENT
═══════════════════════════════════════
{document_content}

═══════════════════════════════════════
REQUIRED JSON OUTPUT SCHEMA
═══════════════════════════════════════
Return ONLY a JSON object with this exact structure:

{{
  "category": "ICSR",
  "patient": {{
    "age": {{"value": "<age or 'Not stated'>", "confidence": <0.0-1.0>, "source_reference": "<citation or 'Not stated'>"}},
    "sex": {{"value": "<sex/gender or 'Not stated'>", "confidence": <0.0-1.0>, "source_reference": "<citation or 'Not stated'>"}},
    "weight": {{"value": "<weight with units or 'Not stated'>", "confidence": <0.0-1.0>, "source_reference": "<citation or 'Not stated'>"}},
    "height": {{"value": "<height with units or 'Not stated'>", "confidence": <0.0-1.0>, "source_reference": "<citation or 'Not stated'>"}},
    "relevant_history": {{"value": "<medical history/concomitant conditions or 'Not stated'>", "confidence": <0.0-1.0>, "source_reference": "<citation or 'Not stated'>"}}
  }},
  "reporter": {{
    "name": {{"value": "<reporter name/identifier or 'Not stated'>", "confidence": <0.0-1.0>, "source_reference": "<citation or 'Not stated'>"}},
    "role": {{"value": "<e.g. Physician, Nurse, Pharmacist, Patient, Consumer or 'Not stated'>", "confidence": <0.0-1.0>, "source_reference": "<citation or 'Not stated'>"}},
    "country": {{"value": "<reporter country/location or 'Not stated'>", "confidence": <0.0-1.0>, "source_reference": "<citation or 'Not stated'>"}}
  }},
  "product": {{
    "name": {{"value": "<suspect drug/product name or 'Not stated'>", "confidence": <0.0-1.0>, "source_reference": "<citation or 'Not stated'>"}},
    "dose": {{"value": "<dosage and strength or 'Not stated'>", "confidence": <0.0-1.0>, "source_reference": "<citation or 'Not stated'>"}},
    "route": {{"value": "<administration route or 'Not stated'>", "confidence": <0.0-1.0>, "source_reference": "<citation or 'Not stated'>"}},
    "start_date": {{"value": "<therapy start date or 'Not stated'>", "confidence": <0.0-1.0>, "source_reference": "<citation or 'Not stated'>"}},
    "stop_date": {{"value": "<therapy stop date or 'Not stated'>", "confidence": <0.0-1.0>, "source_reference": "<citation or 'Not stated'>"}}
  }},
  "reaction": {{
    "reaction": {{"value": "<adverse event/reaction description or 'Not stated'>", "confidence": <0.0-1.0>, "source_reference": "<citation or 'Not stated'>"}},
    "start_date": {{"value": "<reaction onset date or 'Not stated'>", "confidence": <0.0-1.0>, "source_reference": "<citation or 'Not stated'>"}},
    "outcome": {{"value": "<e.g. Recovered, Recovering, Not Recovered, Fatal, Unknown or 'Not stated'>", "confidence": <0.0-1.0>, "source_reference": "<citation or 'Not stated'>"}}
  }},
  "severity": {{
    "serious": {{"value": "<Yes / No / Not stated>", "confidence": <0.0-1.0>, "source_reference": "<citation or 'Not stated'>"}},
    "death": {{"value": "<Yes / No / Not stated>", "confidence": <0.0-1.0>, "source_reference": "<citation or 'Not stated'>"}},
    "hospitalization": {{"value": "<Yes / No / Not stated>", "confidence": <0.0-1.0>, "source_reference": "<citation or 'Not stated'>"}},
    "life_threatening": {{"value": "<Yes / No / Not stated>", "confidence": <0.0-1.0>, "source_reference": "<citation or 'Not stated'>"}},
    "other_severity": {{"value": "<details of other severity criteria or 'Not stated'>", "confidence": <0.0-1.0>, "source_reference": "<citation or 'Not stated'>"}}
  }},
  "narrative": {{
    "case_summary": {{"value": "<short plain-language case summary or 'Not stated'>", "confidence": <0.0-1.0>, "source_reference": "<citation or 'Not stated'>"}}
  }},
  "summary": "<1-2 sentence overall summary of extracted safety facts>"
}}

Extract the facts now. Return ONLY raw JSON.\
"""

# ---------------------------------------------------------------------------
# PQC EXTRACTION USER PROMPT TEMPLATE
# ---------------------------------------------------------------------------
PQC_EXTRACTION_USER_PROMPT_TEMPLATE = """\
Extract all Product Quality Complaint (PQC) facts from the following communication.

═══════════════════════════════════════
DOCUMENT CONTENT
═══════════════════════════════════════
{document_content}

═══════════════════════════════════════
REQUIRED JSON OUTPUT SCHEMA
═══════════════════════════════════════
Return ONLY a JSON object with this exact structure:

{{
  "category": "PQC",
  "product": {{"value": "<product name and formulation or 'Not stated'>", "confidence": <0.0-1.0>, "source_reference": "<citation or 'Not stated'>"}},
  "lot_number": {{"value": "<batch or lot number or 'Not stated'>", "confidence": <0.0-1.0>, "source_reference": "<citation or 'Not stated'>"}},
  "problem": {{"value": "<physical, mechanical, packaging or quality defect description or 'Not stated'>", "confidence": <0.0-1.0>, "source_reference": "<citation or 'Not stated'>"}},
  "photo_mentioned": {{"value": "<Yes / No / Not stated - whether photo or physical sample was attached or offered>", "confidence": <0.0-1.0>, "source_reference": "<citation or 'Not stated'>"}},
  "summary": "<1-2 sentence summary of the product quality complaint>"
}}

Extract the facts now. Return ONLY raw JSON.\
"""

# ---------------------------------------------------------------------------
# MI EXTRACTION USER PROMPT TEMPLATE
# ---------------------------------------------------------------------------
MI_EXTRACTION_USER_PROMPT_TEMPLATE = """\
Extract all Medical Information (MI) inquiry facts from the following communication.

═══════════════════════════════════════
DOCUMENT CONTENT
═══════════════════════════════════════
{document_content}

═══════════════════════════════════════
REQUIRED JSON OUTPUT SCHEMA
═══════════════════════════════════════
Return ONLY a JSON object with this exact structure:

{{
  "category": "MI",
  "questions_asked": {{"value": "<clinical or technical questions asked by the inquirer or 'Not stated'>", "confidence": <0.0-1.0>, "source_reference": "<citation or 'Not stated'>"}},
  "product_topic": {{"value": "<product name or medical topic of the inquiry or 'Not stated'>", "confidence": <0.0-1.0>, "source_reference": "<citation or 'Not stated'>"}},
  "summary": "<1-2 sentence summary of the medical information request>"
}}

Extract the facts now. Return ONLY raw JSON.\
"""

