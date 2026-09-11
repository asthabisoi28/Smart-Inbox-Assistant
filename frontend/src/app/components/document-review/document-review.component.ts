import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { DocumentService } from '../../services/document.service';
import {
  DocumentDetail,
  ClassificationItem,
  ExtractedFactItem,
  EditableFactItem,
  ClassificationCategory,
  DocumentAuditHistory
} from '../../models/document.model';

@Component({
  selector: 'app-document-review',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './document-review.component.html',
  styleUrl: './document-review.component.css'
})
export class DocumentReviewComponent implements OnInit {
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private documentService = inject(DocumentService);

  documentId!: number;
  document: DocumentDetail | null = null;
  classifications: ClassificationItem[] = [];
  editableFacts: EditableFactItem[] = [];
  auditHistory: DocumentAuditHistory | null = null;

  activeTab: 'classification' | 'summary' | 'facts' | 'audit' = 'classification';

  isLoading = true;
  isSaving = false;
  isProcessingAction = false;
  errorMessage = '';
  successMessage = '';

  reviewerName = 'Reviewer';
  hasUnsavedFactChanges = false;

  showAcceptModal = false;
  showOverrideModal = false;

  acceptComments = '';
  overrideCategory: ClassificationCategory = 'ICSR';
  overrideReason = '';
  overrideComments = '';

  readonly categoryChoices: { label: string; value: ClassificationCategory }[] = [
    { label: 'ICSR / Safety Report', value: 'ICSR' },
    { label: 'PQC / Quality Complaint', value: 'PQC' },
    { label: 'MI / Info Request', value: 'MI' },
    { label: 'Not Relevant', value: 'NOT_RELEVANT' }
  ];

  ngOnInit(): void {
    const idParam = this.route.snapshot.paramMap.get('id');
    if (!idParam || isNaN(+idParam)) {
      this.errorMessage = 'Invalid document ID specified.';
      this.isLoading = false;
      return;
    }

    this.documentId = +idParam;
    this.loadDocumentData();
  }

  loadDocumentData(): void {
    this.isLoading = true;
    this.errorMessage = '';

    this.documentService.getDocument(this.documentId).subscribe({
      next: (doc) => {
        this.document = doc;
        this.loadClassificationsAndFacts();
        this.loadAuditHistory();
      },
      error: (err) => {
        this.errorMessage = err.message || 'Failed to load document details.';
        this.isLoading = false;
      }
    });
  }

  private loadClassificationsAndFacts(): void {
    this.documentService.getClassifications(this.documentId).subscribe({
      next: (cls) => {
        this.classifications = cls;
      },
      error: (err) => console.warn('Could not load classifications:', err)
    });

    this.documentService.getFacts(this.documentId).subscribe({
      next: (facts) => {
        this.editableFacts = facts.map(f => ({
          id: f.id,
          field_name: f.field_name,
          field_value: f.field_value,
          category: f.category,
          confidence: f.confidence ?? undefined,
          source_type: f.source_type ?? undefined,
          source_reference: f.source_reference ?? undefined,
          isModified: false
        }));
        this.hasUnsavedFactChanges = false;
        this.isLoading = false;
      },
      error: (err) => {
        console.warn('Could not load extracted facts:', err);
        this.editableFacts = [];
        this.isLoading = false;
      }
    });
  }

  private loadAuditHistory(): void {
    this.documentService.getAuditHistory(this.documentId).subscribe({
      next: (history) => {
        this.auditHistory = history;
      },
      error: (err) => console.warn('Could not load audit history:', err)
    });
  }

  onFactValueChanged(fact: EditableFactItem): void {
    fact.isModified = true;
    this.hasUnsavedFactChanges = true;
  }

  saveChanges(): void {
    if (!this.editableFacts.length) return;

    this.isSaving = true;
    this.errorMessage = '';
    this.successMessage = '';

    const payload = {
      reviewer: this.reviewerName.trim() || 'Reviewer',
      facts: this.editableFacts.map(f => ({
        id: f.id,
        field_name: f.field_name,
        field_value: f.field_value.trim() || 'Not stated',
        category: f.category,
        confidence: f.confidence,
        source_type: f.source_type || 'manual_review',
        source_reference: f.source_reference || 'Reviewer update'
      })),
      comments: 'Updated via Reviewer Dashboard'
    };

    this.documentService.updateFacts(this.documentId, payload).subscribe({
      next: (res) => {
        this.isSaving = false;
        this.hasUnsavedFactChanges = false;
        this.successMessage = `Saved ${res.updated_count} fact(s) successfully.`;
        this.editableFacts = res.facts.map(f => ({
          id: f.id,
          field_name: f.field_name,
          field_value: f.field_value,
          category: f.category,
          confidence: f.confidence ?? undefined,
          source_type: f.source_type ?? undefined,
          source_reference: f.source_reference ?? undefined,
          isModified: false
        }));
        this.clearMessagesAfterDelay();
      },
      error: (err) => {
        this.isSaving = false;
        this.errorMessage = err.message || 'Failed to save fact changes.';
      }
    });
  }

  openAcceptModal(): void {
    this.acceptComments = '';
    this.showAcceptModal = true;
  }

  confirmAccept(): void {
    this.isProcessingAction = true;
    this.errorMessage = '';

    const payload = {
      reviewer: this.reviewerName.trim() || 'Reviewer',
      comments: this.acceptComments.trim() || undefined
    };

    this.documentService.acceptReview(this.documentId, payload).subscribe({
      next: (res) => {
        this.isProcessingAction = false;
        this.showAcceptModal = false;
        if (this.document) {
          this.document.review_status = 'ACCEPTED';
        }
        this.successMessage = 'AI classification and facts accepted successfully.';
        this.loadAuditHistory();
        this.clearMessagesAfterDelay();
      },
      error: (err) => {
        this.isProcessingAction = false;
        this.errorMessage = err.message || 'Failed to accept AI result.';
      }
    });
  }

  openOverrideModal(): void {
    this.overrideCategory = (this.document?.primary_category as ClassificationCategory) || 'ICSR';
    this.overrideReason = '';
    this.overrideComments = '';
    this.showOverrideModal = true;
  }

  confirmOverride(): void {
    if (!this.overrideReason.trim()) {
      this.errorMessage = 'Please provide a reason for the classification override.';
      return;
    }

    this.isProcessingAction = true;
    this.errorMessage = '';

    const payload = {
      reviewer: this.reviewerName.trim() || 'Reviewer',
      new_category: this.overrideCategory,
      reason: this.overrideReason.trim(),
      comments: this.overrideComments.trim() || undefined
    };

    this.documentService.overrideReview(this.documentId, payload).subscribe({
      next: (res) => {
        this.isProcessingAction = false;
        this.showOverrideModal = false;
        if (this.document) {
          this.document.review_status = 'OVERRIDDEN';
          this.document.primary_category = res.current_category || this.overrideCategory;
        }
        this.successMessage = `Classification overridden to ${this.overrideCategory} successfully.`;
        this.loadAuditHistory();
        this.clearMessagesAfterDelay();
      },
      error: (err) => {
        this.isProcessingAction = false;
        this.errorMessage = err.message || 'Failed to override classification.';
      }
    });
  }

  goBack(): void {
    this.router.navigate(['/queue']);
  }

  formatConfidence(conf: number | null | undefined): string {
    if (conf === null || conf === undefined) return '-';
    return conf.toFixed(2);
  }

  formatDate(dateStr: string | null | undefined): string {
    if (!dateStr) return 'Not stated';
    try {
      const d = new Date(dateStr);
      if (isNaN(d.getTime())) return dateStr;
      return d.toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });
    } catch {
      return dateStr;
    }
  }

  formatFieldName(raw: string): string {
    if (!raw) return '';
    return raw
      .replace(/\./g, ' › ')
      .replace(/_/g, ' ')
      .replace(/\b\w/g, char => char.toUpperCase());
  }

  isNotStated(val: string | null | undefined): boolean {
    if (!val) return true;
    const lower = val.trim().toLowerCase();
    return lower === 'not stated' || lower === 'none' || lower === 'n/a' || lower === 'unknown';
  }

  getCategoryBadgeClass(category: string | null | undefined): string {
    switch (category) {
      case 'ICSR': return 'badge-category icsr';
      case 'PQC': return 'badge-category pqc';
      case 'MI': return 'badge-category mi';
      case 'NOT_RELEVANT': return 'badge-category not-relevant';
      default: return 'badge-category unassigned';
    }
  }

  getCategoryLabel(category: string | null | undefined): string {
    switch (category) {
      case 'ICSR': return 'ICSR / Safety Report';
      case 'PQC': return 'PQC / Quality Complaint';
      case 'MI': return 'MI / Info Request';
      case 'NOT_RELEVANT': return 'Not Relevant';
      default: return category || 'UNASSIGNED';
    }
  }

  getReviewStatusBadgeClass(status: string | null | undefined): string {
    switch (status) {
      case 'ACCEPTED': return 'badge-status accepted';
      case 'OVERRIDDEN': return 'badge-status overridden';
      case 'PENDING_REVIEW':
      default: return 'badge-status pending';
    }
  }

  private clearMessagesAfterDelay(): void {
    setTimeout(() => {
      this.successMessage = '';
    }, 4000);
  }
}
