import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import {
  DocumentListItem,
  DocumentDetail,
  ClassificationItem,
  ExtractedFactItem,
  UpdateFactsRequest,
  UpdateFactsResponse,
  AcceptReviewRequest,
  OverrideReviewRequest,
  ReviewResultResponse,
  DocumentAuditHistory
} from '../models/document.model';

@Injectable({
  providedIn: 'root'
})
export class DocumentService {
  private readonly baseUrl = 'http://localhost:8000/api';

  constructor(private http: HttpClient) {}

  getDocuments(params?: {
    category?: string;
    status?: string;
    review_status?: string;
    search?: string;
    limit?: number;
    offset?: number;
  }): Observable<DocumentListItem[]> {
    let httpParams = new HttpParams();
    if (params) {
      if (params.category) httpParams = httpParams.set('category', params.category);
      if (params.status) httpParams = httpParams.set('status', params.status);
      if (params.review_status) httpParams = httpParams.set('review_status', params.review_status);
      if (params.search) httpParams = httpParams.set('search', params.search);
      if (params.limit !== undefined) httpParams = httpParams.set('limit', params.limit.toString());
      if (params.offset !== undefined) httpParams = httpParams.set('offset', params.offset.toString());
    }

    return this.http.get<DocumentListItem[]>(`${this.baseUrl}/documents`, { params: httpParams });
  }

  getDocument(id: number): Observable<DocumentDetail> {
    return this.http.get<DocumentDetail>(`${this.baseUrl}/documents/${id}`);
  }

  getClassifications(id: number): Observable<ClassificationItem[]> {
    return this.http.get<ClassificationItem[]>(`${this.baseUrl}/documents/${id}/classifications`);
  }

  getFacts(id: number): Observable<ExtractedFactItem[]> {
    return this.http.get<ExtractedFactItem[]>(`${this.baseUrl}/documents/${id}/facts`);
  }

  getAuditHistory(id: number): Observable<DocumentAuditHistory> {
    return this.http.get<DocumentAuditHistory>(`${this.baseUrl}/documents/${id}/audit`);
  }

  acceptReview(id: number, request: AcceptReviewRequest): Observable<ReviewResultResponse> {
    return this.http.post<ReviewResultResponse>(`${this.baseUrl}/documents/${id}/review/accept`, request);
  }

  overrideReview(id: number, request: OverrideReviewRequest): Observable<ReviewResultResponse> {
    return this.http.post<ReviewResultResponse>(`${this.baseUrl}/documents/${id}/review/override`, request);
  }

  updateFacts(id: number, request: UpdateFactsRequest): Observable<UpdateFactsResponse> {
    return this.http.put<UpdateFactsResponse>(`${this.baseUrl}/documents/${id}/facts`, request);
  }
}
