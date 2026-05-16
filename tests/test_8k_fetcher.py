"""Tests for SEC EDGAR fetch_recent_8ks helper (Wave 2, Phase G.1)."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src.data import sec_edgar
from src.data.sec_edgar import fetch_recent_8ks
from src.utils.db import init_db


@pytest.fixture(autouse=True)
def _ensure_db():
    """log_api_call writes to api_log; tests use the session temp DB."""
    init_db()
    yield


class _FakeResp:
    def __init__(self, payload=None, text="", status=200):
        self._payload = payload
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def test_fetch_recent_8ks_happy_path_filters_to_8k_within_window(monkeypatch):
    today = datetime.utcnow().date()
    recent_date = (today - timedelta(days=10)).isoformat()
    old_date = (today - timedelta(days=400)).isoformat()
    submissions = {
        "filings": {
            "recent": {
                "accessionNumber": [
                    "0001000000-26-000001",
                    "0001000000-26-000002",
                    "0001000000-26-000003",
                ],
                "form": ["8-K", "10-Q", "8-K"],
                "filingDate": [recent_date, recent_date, old_date],
                "primaryDocument": ["doc1.htm", "doc2.htm", "doc3.htm"],
            }
        }
    }

    submissions_url = "https://data.sec.gov/submissions/CIK0000320193.json"
    primary_doc_text = "ITEM 5.02 — CFO resigns effective immediately."

    def _fake_get(url, headers=None, timeout=30.0, **kwargs):
        if url == submissions_url:
            return _FakeResp(payload=submissions)
        # Otherwise treat as raw-text fetch
        return _FakeResp(text=primary_doc_text)

    monkeypatch.setattr("src.data.sec_edgar.httpx.get", _fake_get)

    out = fetch_recent_8ks("320193", days=180)
    # Only the one 8-K within the window survives (the second 8-K is too old)
    assert len(out) == 1
    row = out[0]
    assert row["form"] == "8-K"
    assert row["accession_number"] == "0001000000-26-000001"
    assert row["filing_date"] == recent_date
    assert (
        "https://www.sec.gov/Archives/edgar/data/320193/000100000026000001/doc1.htm"
        == row["primary_document_url"]
    )
    assert row["raw_text"] == primary_doc_text


def test_fetch_recent_8ks_all_too_old_returns_empty(monkeypatch):
    today = datetime.utcnow().date()
    old_date = (today - timedelta(days=400)).isoformat()
    submissions = {
        "filings": {
            "recent": {
                "accessionNumber": ["0001-1", "0001-2"],
                "form": ["8-K", "8-K"],
                "filingDate": [old_date, old_date],
                "primaryDocument": ["d1.htm", "d2.htm"],
            }
        }
    }

    submissions_url = "https://data.sec.gov/submissions/CIK0000320193.json"

    def _fake_get(url, headers=None, timeout=30.0, **kwargs):
        if url == submissions_url:
            return _FakeResp(payload=submissions)
        return _FakeResp(text="should not be called")

    monkeypatch.setattr("src.data.sec_edgar.httpx.get", _fake_get)

    out = fetch_recent_8ks("320193", days=180)
    assert out == []


def test_fetch_recent_8ks_network_error_returns_empty(monkeypatch):
    def _boom(*a, **kw):
        raise RuntimeError("network down")

    monkeypatch.setattr("src.data.sec_edgar.httpx.get", _boom)

    out = fetch_recent_8ks("320193", days=180)
    assert out == []
