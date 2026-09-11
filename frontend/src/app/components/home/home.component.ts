import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink, Router } from '@angular/router';
import { DocumentService } from '../../services/document.service';
import { DocumentListItem } from '../../models/document.model';

@Component({
  selector: 'app-home',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './home.component.html',
  styleUrl: './home.component.css'
})
export class HomeComponent implements OnInit {
  private documentService = inject(DocumentService);
  private router = inject(Router);

  documents: DocumentListItem[] = [];
  isLoading = true;

  totalDocs = 15;
  pendingCount = 8;
  acceptedCount = 5;
  overriddenCount = 2;

  ngOnInit(): void {
    this.documentService.getDocuments({ limit: 100 }).subscribe({
      next: (docs) => {
        this.documents = docs;
        this.totalDocs = docs.length;
        this.pendingCount = docs.filter(d => d.review_status === 'PENDING_REVIEW' || !d.review_status).length;
        this.acceptedCount = docs.filter(d => d.review_status === 'ACCEPTED').length;
        this.overriddenCount = docs.filter(d => d.review_status === 'OVERRIDDEN').length;
        this.isLoading = false;
      },
      error: () => {
        this.isLoading = false;
      }
    });
  }

  openDocument(id: number): void {
    this.router.navigate(['/review', id]);
  }
}
