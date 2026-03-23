"""API endpoint tests using FastAPI TestClient."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from src.app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


def test_list_reports(client):
    resp = client.get("/reports")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_watchlist_crud(client):
    # Add to watchlist
    resp = client.post("/watchlist", json={"symbol": "TEST"})
    assert resp.status_code == 200

    # List watchlist
    resp = client.get("/watchlist")
    assert resp.status_code == 200
    symbols = [w["symbol"] for w in resp.json()]
    assert "TEST" in symbols

    # Remove from watchlist
    resp = client.delete("/watchlist/TEST")
    assert resp.status_code == 200


def test_get_nonexistent_report(client):
    resp = client.get("/reports/99999")
    assert resp.status_code in (200, 404)
