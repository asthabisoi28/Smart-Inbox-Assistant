import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { DocumentService } from '../../services/document.service';
import { DocumentListItem, ClassificationCategory, ReviewStatus } from '../../models/document.model';

@Component({
  selector: 'app-document-queue',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './document-queue.component.html',
  styleUrl: './document-queue.component.css'
})
export class DocumentQueueComponent implements OnInit {
  private documentService = inject(DocumentService);
  private router = inject(Router);

  documents: DocumentListItem[] = [];
  filteredDocuments: DocumentListItem[] = [];

  isLoading = false;
  errorMessage = '';

  // Filter criteria
  searchQuery = '';
  selectedCategory: string = 'ALL';
  selectedReviewStatus: string = 'ALL';

  readonly categoryOptions: { label: string; value: string }[] = [
    { label: 'All Categories', value: 'ALL' },
    { label: 'ICSR / Safety Report', value: 'ICSR' },
    { label: 'PQC / Quality Complaint', value: 'PQC' },
    { label: 'MI / Info Request', value: 'MI' },
    { label: 'Not Relevant', value: 'NOT_RELEVANT' }
  ];

  readonly reviewStatusOptions: { label: string; value: string }[] = [
    { label: 'All Review Statuses', value: 'ALL' },
    { label: 'Pending Review', value: 'PENDING_REVIEW' },
    { label: 'Accepted', value: 'ACCEPTED' },
    { label: 'Overridden', value: 'OVERRIDDEN' }
  ];

  totalDocs = 0;
  pendingCount = 0;
  acceptedCount = 0;
  overriddenCount = 0;

  ngOnInit(): void {
    this.loadDocuments();
  }

  loadDocuments(): void {
    this.isLoading = true;
    this.errorMessage = '';

    this.documentService.getDocuments({ limit: 100 }).subscribe({
      next: (data) => {
        this.documents = data;
        this.updateMetricCounters();
        this.applyLocalFilters();
        this.isLoading = false;
      },
      error: (err) => {
        this.errorMessage = err.message || 'Failed to load document queue.';
        this.isLoading = false;
      }
    });
  }

  private updateMetricCounters(): void {
    this.totalDocs = this.documents.length;
    this.pendingCount = this.documents.filter(d => (d.review_status || 'PENDING_REVIEW') === 'PENDING_REVIEW').length;
    this.acceptedCount = this.documents.filter(d => d.review_status === 'ACCEPTED').length;
    this.overriddenCount = this.documents.filter(d => d.review_status === 'OVERRIDDEN').length;
  }

  onFilterChange(): void {
    this.applyLocalFilters();
  }

  private applyLocalFilters(): void {
    let result = [...this.documents];

    if (this.selectedCategory !== 'ALL') {
      result = result.filter(doc => doc.primary_category === this.selectedCategory);
    }

    if (this.selectedReviewStatus !== 'ALL') {
      result = result.filter(doc => (doc.review_status || 'PENDING_REVIEW') === this.selectedReviewStatus);
    }

    if (this.searchQuery.trim()) {
      const q = this.searchQuery.trim().toLowerCase();
      result = result.filter(doc =>
        (doc.subject && doc.subject.toLowerCase().includes(q)) ||
        (doc.sender && doc.sender.toLowerCase().includes(q)) ||
        (doc.filename && doc.filename.toLowerCase().includes(q)) ||
        `doc-00${doc.id}`.includes(q)
      );
    }

    this.filteredDocuments = result;
  }

  openReview(doc: DocumentListItem): void {
    this.router.navigate(['/review', doc.id]);
  }

  formatConfidence(conf: number | null | undefined): string {
    if (conf === null || conf === undefined) return '-';
    return conf.toFixed(2);
  }

  getCategoryLabel(category: string | null | undefined): string {
    switch (category) {
      case 'ICSR': return 'ICSR';
      case 'PQC': return 'PQC';
      case 'MI': return 'MI';
      case 'NOT_RELEVANT': return 'NOT_RELEVANT';
      default: return category || 'UNASSIGNED';
    }
  }

  formatReviewStatus(status: string | null | undefined): string {
    switch (status) {
      case 'ACCEPTED': return 'Accepted';
      case 'OVERRIDDEN': return 'Overridden';
      case 'PENDING_REVIEW':
      default: return 'Pending';
    }
  }

  formatDate(dateStr: string | null | undefined): string {
    if (!dateStr) return 'Not stated';
    try {
      const d = new Date(dateStr);
      if (isNaN(d.getTime())) return dateStr;
      return d.toLocaleString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: 'numeric',
        minute: 'numeric',
        hour12: true
      });
    } catch {
      return dateStr;
    }
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

  getReviewStatusBadgeClass(status: string | null | undefined): string {
    switch (status) {
      case 'ACCEPTED': return 'badge-status accepted';
      case 'OVERRIDDEN': return 'badge-status overridden';
      case 'PENDING_REVIEW':
      default: return 'badge-status pending';
    }
  }

  getProcessingStatusBadgeClass(status: string | null | undefined): string {
    switch (status?.toUpperCase()) {
      case 'COMPLETED':
      case 'PROCESSED':
        return 'badge-proc completed';
      case 'FAILED':
      case 'ERROR':
        return 'badge-proc failed';
      case 'PROCESSING':
        return 'badge-proc processing';
      default:
        return 'badge-proc pending';
    }
  }
}
