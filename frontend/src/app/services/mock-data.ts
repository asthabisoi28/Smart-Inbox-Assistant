import {
  DocumentListItem,
  DocumentDetail,
  ClassificationItem,
  ExtractedFactItem,
  DocumentAuditHistory
} from '../models/document.model';

export const MOCK_DOCUMENTS: DocumentListItem[] = [
  {
    id: 1,
    email_id: 101,
    filename: 'safety_report_001.pdf',
    file_path: 'storage/attachments/safety_report_001.pdf',
    document_type: 'PDF',
    processing_status: 'Processed',
    language: 'en',
    ocr_confidence: 0.96,
    processing_time: 42.6,
    primary_category: 'ICSR',
    confidence: 0.92,
    subject: 'Adverse reaction report',
    sender: 'dr.smith@hospital.com',
    received_date: '2025-04-21T10:24:00Z',
    review_status: 'PENDING_REVIEW',
    classifications_count: 2,
    facts_count: 5,
    created_at: '2025-04-21T10:25:00Z'
  },
  {
    id: 2,
    email_id: 102,
    filename: 'quality_issue_002.pdf',
    file_path: 'storage/attachments/quality_issue_002.pdf',
    document_type: 'PDF',
    processing_status: 'Processed',
    language: 'en',
    ocr_confidence: 0.98,
    processing_time: 18.2,
    primary_category: 'PQC',
    confidence: 0.87,
    subject: 'Product quality issue',
    sender: 'patient@domain.com',
    received_date: '2025-04-21T09:15:00Z',
    review_status: 'PENDING_REVIEW',
    classifications_count: 1,
    facts_count: 4,
    created_at: '2025-04-21T09:16:00Z'
  },
  {
    id: 3,
    email_id: 103,
    filename: 'dosage_question_003.pdf',
    file_path: 'storage/attachments/dosage_question_003.pdf',
    document_type: 'PDF',
    processing_status: 'Processed',
    language: 'en',
    ocr_confidence: 0.95,
    processing_time: 12.4,
    primary_category: 'MI',
    confidence: 0.76,
    subject: 'Usage question',
    sender: 'pharmacist@clinic.com',
    received_date: '2025-04-20T16:40:00Z',
    review_status: 'PENDING_REVIEW',
    classifications_count: 1,
    facts_count: 3,
    created_at: '2025-04-20T16:41:00Z'
  },
  {
    id: 4,
    email_id: 104,
    filename: 'promo_flyer_004.pdf',
    file_path: 'storage/attachments/promo_flyer_004.pdf',
    document_type: 'PDF',
    processing_status: 'Processed',
    language: 'en',
    ocr_confidence: 0.99,
    processing_time: 8.1,
    primary_category: 'NOT_RELEVANT',
    confidence: 0.94,
    subject: 'Marketing email',
    sender: 'marketing@company.com',
    received_date: '2025-04-20T11:00:00Z',
    review_status: 'ACCEPTED',
    classifications_count: 1,
    facts_count: 1,
    created_at: '2025-04-20T11:01:00Z'
  },
  {
    id: 5,
    email_id: 105,
    filename: 'scanned_report_005.pdf',
    file_path: 'storage/attachments/scanned_report_005.pdf',
    document_type: 'PDF (Scanned)',
    processing_status: 'Processed',
    language: 'en',
    ocr_confidence: 0.82,
    processing_time: 35.8,
    primary_category: 'ICSR',
    confidence: 0.83,
    subject: 'Scanned report',
    sender: 'nurse@hospital.com',
    received_date: '2025-04-19T14:30:00Z',
    review_status: 'PENDING_REVIEW',
    classifications_count: 1,
    facts_count: 4,
    created_at: '2025-04-19T14:32:00Z'
  },
  {
    id: 6,
    email_id: 106,
    filename: 'damaged_product_006.pdf',
    file_path: 'storage/attachments/damaged_product_006.pdf',
    document_type: 'PDF',
    processing_status: 'Processed',
    language: 'en',
    ocr_confidence: 0.94,
    processing_time: 15.3,
    primary_category: 'PQC',
    confidence: 0.88,
    subject: 'Damaged product',
    sender: 'customer@retail.com',
    received_date: '2025-04-19T10:12:00Z',
    review_status: 'PENDING_REVIEW',
    classifications_count: 1,
    facts_count: 4,
    created_at: '2025-04-19T10:13:00Z'
  },
  {
    id: 7,
    email_id: 107,
    filename: 'research_article_007.pdf',
    file_path: 'storage/attachments/research_article_007.pdf',
    document_type: 'PDF (Article)',
    processing_status: 'Processed',
    language: 'en',
    ocr_confidence: 0.97,
    processing_time: 28.6,
    primary_category: 'MI',
    confidence: 0.72,
    subject: 'Research article',
    sender: 'research@university.edu',
    received_date: '2025-04-18T18:05:00Z',
    review_status: 'PENDING_REVIEW',
    classifications_count: 2,
    facts_count: 5,
    created_at: '2025-04-18T18:06:00Z'
  },
  {
    id: 8,
    email_id: 108,
    filename: 'informe_medico_008.pdf',
    file_path: 'storage/attachments/informe_medico_008.pdf',
    document_type: 'PDF (Spanish)',
    processing_status: 'Processed',
    language: 'es',
    ocr_confidence: 0.88,
    processing_time: 24.1,
    primary_category: 'ICSR',
    confidence: 0.81,
    subject: 'Non-English report',
    sender: 'medico@clinic.es',
    received_date: '2025-04-18T12:20:00Z',
    review_status: 'PENDING_REVIEW',
    classifications_count: 1,
    facts_count: 4,
    created_at: '2025-04-18T12:21:00Z'
  },
  {
    id: 9,
    email_id: 109,
    filename: 'handwritten_notes_009.pdf',
    file_path: 'storage/attachments/handwritten_notes_009.pdf',
    document_type: 'PDF (Handwritten)',
    processing_status: 'Processed',
    language: 'en',
    ocr_confidence: 0.75,
    processing_time: 41.2,
    primary_category: 'ICSR',
    confidence: 0.85,
    subject: 'Handwritten case summary',
    sender: 'clinic@health.org',
    received_date: '2025-04-17T15:45:00Z',
    review_status: 'OVERRIDDEN',
    classifications_count: 2,
    facts_count: 5,
    created_at: '2025-04-17T15:47:00Z'
  },
  {
    id: 10,
    email_id: 110,
    filename: 'dosage_cardlofix_010.pdf',
    file_path: 'storage/attachments/dosage_cardlofix_010.pdf',
    document_type: 'PDF',
    processing_status: 'Processed',
    language: 'en',
    ocr_confidence: 0.99,
    processing_time: 11.5,
    primary_category: 'MI',
    confidence: 0.91,
    subject: 'Dosage inquiry for CardioFix',
    sender: 'patient2@mail.com',
    received_date: '2025-04-17T09:30:00Z',
    review_status: 'ACCEPTED',
    classifications_count: 1,
    facts_count: 3,
    created_at: '2025-04-17T09:31:00Z'
  },
  {
    id: 11,
    email_id: 111,
    filename: 'batch_9842_complaint_011.pdf',
    file_path: 'storage/attachments/batch_9842_complaint_011.pdf',
    document_type: 'PDF',
    processing_status: 'Processed',
    language: 'en',
    ocr_confidence: 0.96,
    processing_time: 14.8,
    primary_category: 'PQC',
    confidence: 0.95,
    subject: 'Broken vial batch #9842',
    sender: 'pharmacy@med.com',
    received_date: '2025-04-16T14:10:00Z',
    review_status: 'ACCEPTED',
    classifications_count: 1,
    facts_count: 4,
    created_at: '2025-04-16T14:11:00Z'
  },
  {
    id: 12,
    email_id: 112,
    filename: 'rapport_pharmacovigilance_012.pdf',
    file_path: 'storage/attachments/rapport_pharmacovigilance_012.pdf',
    document_type: 'PDF (French)',
    processing_status: 'Processed',
    language: 'fr',
    ocr_confidence: 0.91,
    processing_time: 29.4,
    primary_category: 'ICSR',
    confidence: 0.89,
    subject: 'Rapport de cas de pharmacovigilance',
    sender: 'medecin@hopital.fr',
    received_date: '2025-04-16T08:50:00Z',
    review_status: 'ACCEPTED',
    classifications_count: 1,
    facts_count: 4,
    created_at: '2025-04-16T08:52:00Z'
  },
  {
    id: 13,
    email_id: 113,
    filename: 'newsletter_q2_013.pdf',
    file_path: 'storage/attachments/newsletter_q2_013.pdf',
    document_type: 'PDF',
    processing_status: 'Processed',
    language: 'en',
    ocr_confidence: 0.99,
    processing_time: 6.8,
    primary_category: 'NOT_RELEVANT',
    confidence: 0.98,
    subject: 'Quarterly newsletter',
    sender: 'news@pharma-today.com',
    received_date: '2025-04-15T17:00:00Z',
    review_status: 'ACCEPTED',
    classifications_count: 1,
    facts_count: 1,
    created_at: '2025-04-15T17:01:00Z'
  },
  {
    id: 14,
    email_id: 114,
    filename: 'liver_dysfunction_014.pdf',
    file_path: 'storage/attachments/liver_dysfunction_014.pdf',
    document_type: 'PDF',
    processing_status: 'Processed',
    language: 'en',
    ocr_confidence: 0.94,
    processing_time: 38.1,
    primary_category: 'ICSR',
    confidence: 0.93,
    subject: 'Suspected liver dysfunction case',
    sender: 'gastro@hospital.org',
    received_date: '2025-04-15T11:20:00Z',
    review_status: 'PENDING_REVIEW',
    classifications_count: 2,
    facts_count: 5,
    created_at: '2025-04-15T11:22:00Z'
  },
  {
    id: 15,
    email_id: 115,
    filename: 'packaging_notice_015.pdf',
    file_path: 'storage/attachments/packaging_notice_015.pdf',
    document_type: 'PDF',
    processing_status: 'Processed',
    language: 'en',
    ocr_confidence: 0.93,
    processing_time: 16.5,
    primary_category: 'PQC',
    confidence: 0.84,
    subject: 'Packaging discoloration notice',
    sender: 'qc@supply.com',
    received_date: '2025-04-14T09:10:00Z',
    review_status: 'OVERRIDDEN',
    classifications_count: 1,
    facts_count: 3,
    created_at: '2025-04-14T09:11:00Z'
  }
];

export const MOCK_DETAILS: Record<number, DocumentDetail> = {
  1: {
    id: 1,
    email_id: 101,
    filename: 'safety_report_001.pdf',
    file_path: 'storage/attachments/safety_report_001.pdf',
    document_type: 'Digital PDF',
    extracted_text: `ADVERSE EVENT REPORT - CONFIDENTIAL
Date: April 21, 2025
Reporter: Dr. Smith (Physician, USA)

PATIENT INFORMATION:
Patient Age: 52
Gender: Female
Medical History: Hypertension

PRODUCT INFORMATION:
Drug Name: CardioFix
Dose: 50 mg
Route: Oral
Start Date: 2025-04-01
Stop Date: 2025-04-10

REACTION DETAILS:
Reaction: Rash (maculopapular), moderate severity.
Start Date: 2025-04-05
Outcome: Hospitalization required on 2025-04-08. Currently recovering.`,
    original_text: 'Email message attached with safety_report_001.pdf',
    language: 'en',
    ocr_confidence: 0.96,
    processing_status: 'Processed',
    processing_time: 42.6,
    primary_category: 'ICSR',
    confidence: 0.92,
    subject: 'Adverse reaction report',
    sender: 'dr.smith@hospital.com',
    received_date: '2025-04-21T10:24:00Z',
    email_body: `Dear team,

We would like to report a suspected adverse reaction in a patient who was taking your product CardioFix. The patient developed a rash and required hospitalization.

Please see the attached report for full details.

Best regards,
Dr. Smith`,
    review_status: 'PENDING_REVIEW',
    created_at: '2025-04-21T10:25:00Z'
  }
};

export const MOCK_CLASSIFICATIONS: Record<number, ClassificationItem[]> = {
  1: [
    {
      id: 1,
      document_id: 1,
      category: 'ICSR / Safety Report',
      confidence: 0.92,
      reason: 'Contains patient demographic details, drug name (CardioFix), and adverse reaction details (maculopapular rash requiring hospitalization).',
      created_at: '2025-04-21T10:25:00Z'
    },
    {
      id: 2,
      document_id: 1,
      category: 'MI / Info Request',
      confidence: 0.56,
      reason: 'Includes minor question about dosage interactions.',
      created_at: '2025-04-21T10:25:00Z'
    }
  ]
};

export const MOCK_FACTS: Record<number, ExtractedFactItem[]> = {
  1: [
    {
      id: 101,
      document_id: 1,
      category: 'ICSR',
      field_name: 'Patient Age',
      field_value: '52',
      confidence: 0.94,
      source_type: 'PDF',
      source_reference: 'PDF p.2',
      created_at: '2025-04-21T10:25:00Z'
    },
    {
      id: 102,
      document_id: 1,
      category: 'ICSR',
      field_name: 'Patient Gender',
      field_value: 'Female',
      confidence: 0.93,
      source_type: 'PDF',
      source_reference: 'PDF p.2',
      created_at: '2025-04-21T10:25:00Z'
    },
    {
      id: 103,
      document_id: 1,
      category: 'ICSR',
      field_name: 'Reaction',
      field_value: 'Rash',
      confidence: 0.91,
      source_type: 'PDF',
      source_reference: 'PDF p.2',
      created_at: '2025-04-21T10:25:00Z'
    },
    {
      id: 104,
      document_id: 1,
      category: 'ICSR',
      field_name: 'Severity',
      field_value: 'Hospitalization',
      confidence: 0.87,
      source_type: 'PDF',
      source_reference: 'PDF p.2-3',
      created_at: '2025-04-21T10:25:00Z'
    },
    {
      id: 105,
      document_id: 1,
      category: 'ICSR',
      field_name: 'Suspect Drug',
      field_value: 'CardioFix 50mg',
      confidence: 0.95,
      source_type: 'PDF',
      source_reference: 'PDF p.1',
      created_at: '2025-04-21T10:25:00Z'
    }
  ]
};

export const MOCK_AUDIT_LOGS: Record<number, DocumentAuditHistory> = {
  1: {
    document_id: 1,
    audit_logs: [
      {
        id: 1,
        document_id: 1,
        event: 'EMAIL_INGESTED',
        details: 'Received email from dr.smith@hospital.com',
        timestamp: '2025-04-21T10:24:00Z'
      },
      {
        id: 2,
        document_id: 1,
        event: 'PDF_EXTRACTED',
        details: 'Extracted safety_report_001.pdf (3 pages, 96% OCR confidence)',
        timestamp: '2025-04-21T10:24:30Z'
      },
      {
        id: 3,
        document_id: 1,
        event: 'AI_CLASSIFIED',
        details: 'Primary category ICSR (Confidence 0.92)',
        timestamp: '2025-04-21T10:25:00Z'
      }
    ],
    review_actions: []
  }
};
