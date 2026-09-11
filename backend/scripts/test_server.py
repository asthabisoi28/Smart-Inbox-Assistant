import sys
import os
from fastapi.testclient import TestClient

# Ensure project root is in PYTHONPATH
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(project_root)

from app.main import app

client = TestClient(app)

def test_health():
    resp = client.get('/api/health')
    print('Health status:', resp.status_code, resp.json())

def test_documents_list():
    resp = client.get('/api/documents?skip=0&limit=10')
    print('Docs list status:', resp.status_code)
    try:
        print('Response:', resp.json())
    except Exception as e:
        print('Error parsing JSON:', e)

if __name__ == '__main__':
    test_health()
    test_documents_list()
