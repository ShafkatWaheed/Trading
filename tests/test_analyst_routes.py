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


def test_long_post_kicks_background_job_and_returns_fast(monkeypatch):
    """The long Opus POSTs kick a background job and return immediately
    (no synchronous Opus call) — verified without spawning a real job."""
    from api.services import _background_jobs
    kicked = []
    monkeypatch.setattr(_background_jobs, "kick", lambda key, fn: (kicked.append(key) or True))
    monkeypatch.setattr(_background_jobs, "get_job_status", lambda key: {"status": "running"})
    r = client.post("/predictions/analyst/playbook/refresh")
    assert r.status_code == 200
    body = r.json()
    assert body["key"] == "analyst_playbook_refresh" and body["started"] is True
    assert kicked == ["analyst_playbook_refresh"]


def test_job_status_route(monkeypatch):
    from api.services import _background_jobs
    monkeypatch.setattr(_background_jobs, "get_job_status",
                        lambda key: {"status": "done", "progress_pct": 100})
    r = client.get("/predictions/jobs/analyst_playbook_refresh")
    assert r.status_code == 200
    assert r.json()["status"]["status"] == "done"
