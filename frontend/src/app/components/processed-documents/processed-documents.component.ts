import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { DocumentService } from '../../services/document.service';
import { DocumentListItem } from '../../models/document.model';

@Component({
  selector: 'app-processed-documents',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './processed-documents.component.html',
  styleUrl: './processed-documents.component.css'
})
export class ProcessedDocumentsComponent implements OnInit {
  private documentService = inject(DocumentService);
  private router = inject(Router);

  documents: DocumentListItem[] = [];
  isLoading = true;

  ngOnInit(): void {
    this.documentService.getDocuments({ limit: 100 }).subscribe({
      next: (docs) => {
        // Filter accepted or overridden
        this.documents = docs.filter(d => d.review_status === 'ACCEPTED' || d.review_status === 'OVERRIDDEN');
        this.isLoading = false;
      },
      error: () => {
        this.isLoading = false;
      }
    });
  }

  openReview(doc: DocumentListItem): void {
    this.router.navigate(['/review', doc.id]);
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
      default: return 'badge-status pending';
    }
  }
}
