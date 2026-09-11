/**
 * Models for the Document Reviewer Dashboard.
 * Aligns with backend FastAPI schemas in app/schemas/reviewer_schemas.py.
 */

export type ClassificationCategory = 'ICSR' | 'PQC' | 'MI' | 'NOT_RELEVANT';

export type ReviewStatus = 'PENDING_REVIEW' | 'ACCEPTED' | 'OVERRIDDEN' | 'REJECTED';

export interface DocumentListItem {
  id: number;
  email_id?: number | null;
  filename: string;
  file_path?: string | null;
  document_type: string;
  processing_status: string;
  language?: string | null;
  ocr_confidence?: number | null;
  processing_time?: number | null;
  primary_category?: string | null;
  confidence?: number | null;
  subject?: string | null;
  sender?: string | null;
  received_date?: string | null;
  review_status: ReviewStatus | string;
  classifications_count: number;
  facts_count: number;
  created_at: string;
}

export interface DocumentDetail {
  id: number;
  email_id?: number | null;
  filename: string;
  file_path?: string | null;
  document_type: string;
  extracted_text?: string | null;
  original_text?: string | null;
  language?: string | null;
  ocr_confidence?: number | null;
  tables_json?: string | null;
  images_json?: string | null;
  processing_status: string;
  processing_time?: number | null;
  primary_category?: string | null;
  confidence?: number | null;
  subject?: string | null;
  sender?: string | null;
  received_date?: string | null;
  email_body?: string | null;
  review_status: ReviewStatus | string;
  created_at: string;
}

export interface ClassificationItem {
  id: number;
  document_id?: number | null;
  email_id?: number | null;
  category: string;
  confidence?: number | null;
  reason?: string | null;
  created_at: string;
}

export interface ExtractedFactItem {
  id: number;
  document_id: number;
  category: string;
  field_name: string;
  field_value: string;
  confidence?: number | null;
  source_type?: string | null;
  source_reference?: string | null;
  created_at: string;
}

export interface EditableFactItem {
  id?: number;
  field_name: string;
  field_value: string;
  category?: ClassificationCategory | string;
  confidence?: number;
  source_type?: string;
  source_reference?: string;
  isModified?: boolean;
}

export interface UpdateFactsRequest {
  reviewer: string;
  facts: {
    id?: number;
    field_name: string;
    field_value: string;
    category?: string;
    confidence?: number;
    source_type?: string;
    source_reference?: string;
  }[];
  comments?: string;
}

export interface UpdateFactsResponse {
  success: boolean;
  document_id: number;
  reviewer: string;
  updated_count: number;
  facts: ExtractedFactItem[];
  timestamp: string;
  message: string;
}

export interface AcceptReviewRequest {
  reviewer: string;
  comments?: string;
}

export interface OverrideReviewRequest {
  reviewer: string;
  new_category: ClassificationCategory | string;
  reason: string;
  comments?: string;
}

export interface ReviewResultResponse {
  success: boolean;
  document_id: number;
  action: string;
  reviewer: string;
  comments?: string | null;
  current_category?: string | null;
  timestamp: string;
  message: string;
}

export interface AuditLogItem {
  id: number;
  email_id?: number | null;
  document_id?: number | null;
  event: string;
  details?: string | null;
  timestamp: string;
}

export interface ReviewActionItem {
  id: number;
  email_id?: number | null;
  document_id?: number | null;
  action: string;
  reviewer: string;
  comments?: string | null;
  timestamp: string;
}

export interface DocumentAuditHistory {
  document_id: number;
  audit_logs: AuditLogItem[];
  review_actions: ReviewActionItem[];
}
