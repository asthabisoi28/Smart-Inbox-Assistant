from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data == {
        "status": "ok",
        "service": "smart-inbox-assistant"
    }


def test_db_health_endpoint():
    response = client.get("/api/health/db")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "database_connected" in data
    assert data["service"] == "smart-inbox-assistant"
