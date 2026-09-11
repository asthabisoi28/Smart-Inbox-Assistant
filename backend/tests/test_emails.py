def test_mock_email_ingestion_and_duplicate_prevention(client):
    # 1. First Ingestion Run
    response = client.post("/api/emails/mock-ingest")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["ingested_count"] == 5
    assert data["skipped_count"] == 0

    # 2. Verify Emails stored in database
    list_res = client.get("/api/emails")
    assert list_res.status_code == 200
    emails = list_res.json()
    assert len(emails) == 5

    # Check that PDF attachments are recorded and non-PDF attachment is ignored
    email_with_docx = next(e for e in emails if "Expo" in e["subject"])
    assert len(email_with_docx["documents"]) == 0  # .docx was ignored from documents table

    email_with_pdf = next(e for e in emails if "CardioVax" in e["subject"])
    assert len(email_with_pdf["documents"]) == 1
    assert email_with_pdf["documents"][0]["filename"] == "ICSR_Report_SYN_9021_CardioVax.pdf"

    # 3. Duplicate Prevention: Run second time
    dup_res = client.post("/api/emails/mock-ingest")
    assert dup_res.status_code == 200
    dup_data = dup_res.json()
    assert dup_data["ingested_count"] == 0
    assert dup_data["skipped_count"] == 5

    # Ensure total count remains 5
    list_after_dup = client.get("/api/emails")
    assert len(list_after_dup.json()) == 5


def test_get_single_email_details(client):
    client.post("/api/emails/mock-ingest")
    list_res = client.get("/api/emails")
    first_email = list_res.json()[0]
    email_id = first_email["id"]

    detail_res = client.get(f"/api/emails/{email_id}")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["id"] == email_id
    assert "sender" in detail
    assert "body" in detail


def test_sync_with_mock_query_param(client):
    sync_res = client.post("/api/emails/sync?use_mock=true")
    assert sync_res.status_code == 200
    data = sync_res.json()
    assert data["success"] is True
    assert data["ingested_count"] == 5


def test_non_pdf_audit_log_verification(client, db):
    from app.models.audit_log import AuditLog
    client.post("/api/emails/mock-ingest")

    # Verify audit logs for non-PDF attachment
    logs = db.query(AuditLog).filter(AuditLog.event == "NON_PDF_ATTACHMENT_IGNORED").all()
    assert len(logs) >= 1
    assert "conference_agenda_brochure.docx" in logs[0].details
