import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

@Component({
  selector: 'app-settings',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './settings.component.html',
  styleUrl: './settings.component.css'
})
export class SettingsComponent {
  // Settings Form State
  apiEndpoint = 'http://localhost:8000/api';
  geminiModel = 'gemini-1.5-pro';
  autoTriageConfidence = 85;
  enableEmailIngestion = true;
  pollIntervalMinutes = 5;

  reviewerName = 'Reviewer';
  reviewerEmail = 'reviewer@company.com';
  reviewerRole = 'Lead Pharmacovigilance Specialist';

  showSavedAlert = false;

  saveSettings(): void {
    this.showSavedAlert = true;
    setTimeout(() => {
      this.showSavedAlert = false;
    }, 3000);
  }
}
