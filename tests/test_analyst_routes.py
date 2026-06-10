from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


def test_analyst_playbook_route():
    r = client.get("/predictions/analyst/playbook")
    assert r.status_code == 200
    assert "playbook" in r.json()


def test_bootstrap_status_route():
    r = client.get("/predictions/bootstrap/status")
    assert r.status_code == 200
    body = r.json()
    assert "predicted_days" in body and "hit_rate" in body
