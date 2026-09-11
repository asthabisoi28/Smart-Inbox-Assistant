import { Routes } from '@angular/router';
import { HomeComponent } from './components/home/home.component';
import { DocumentQueueComponent } from './components/document-queue/document-queue.component';
import { ProcessedDocumentsComponent } from './components/processed-documents/processed-documents.component';
import { DocumentReviewComponent } from './components/document-review/document-review.component';
import { SettingsComponent } from './components/settings/settings.component';

export const routes: Routes = [
  { path: '', redirectTo: 'home', pathMatch: 'full' },
  { path: 'home', component: HomeComponent, title: 'Home - Smart Inbox Assistant' },
  { path: 'queue', component: DocumentQueueComponent, title: 'Document Queue - Smart Inbox Assistant' },
  { path: 'processed', component: ProcessedDocumentsComponent, title: 'Processed Archive - Smart Inbox Assistant' },
  { path: 'review/:id', component: DocumentReviewComponent, title: 'Document Review - Smart Inbox Assistant' },
  { path: 'settings', component: SettingsComponent, title: 'Settings - Smart Inbox Assistant' },
  { path: '**', redirectTo: 'home' }
];
