"""Tests for USPTO PatentsView fetcher (Wave 2)."""
from __future__ import annotations

import json

import pytest

from src.data.uspto_patentsview import fetch_patents_for_assignee
from src.utils.db import init_db


@pytest.fixture(autouse=True)
def _ensure_api_log_table():
    """log_api_call writes to the api_log table; tests use the session temp DB."""
    init_db()
    yield


class _FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")
    def json(self):
        return self._payload


def test_fetch_patents_returns_list_with_required_fields(monkeypatch):
    fake = {
        "patents": [
            {
                "patent_id": "11234567",
                "patent_title": "Method for on-device machine learning",
                "patent_date": "2026-01-15",
                "assignees": [{"assignee_organization": "Apple Inc."}],
                "cpc_at_issue": [{"cpc_subclass_id": "G06N"}],
            },
            {
                "patent_id": "11234568",
                "patent_title": "Wireless display optics",
                "patent_date": "2026-02-20",
                "assignees": [{"assignee_organization": "Apple Inc."}],
                "cpc_at_issue": [{"cpc_subclass_id": "H04W"}],
            },
        ],
        "count": 2,
        "total_hits": 2,
    }
    monkeypatch.setattr(
        "src.data.uspto_patentsview.httpx.post",
        lambda *a, **k: _FakeResp(fake),
    )
    out = fetch_patents_for_assignee("Apple Inc.", since_date="2025-05-15")
    assert len(out) == 2
    assert out[0]["patent_id"] == "11234567"
    assert out[0]["cpc_class"] == "G06N"
    assert out[0]["date"] == "2026-01-15"


def test_fetch_patents_returns_empty_on_no_results(monkeypatch):
    monkeypatch.setattr(
        "src.data.uspto_patentsview.httpx.post",
        lambda *a, **k: _FakeResp({"patents": [], "count": 0, "total_hits": 0}),
    )
    out = fetch_patents_for_assignee("Nonexistent Co", since_date="2025-05-15")
    assert out == []


def test_fetch_patents_returns_empty_on_network_error(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("network down")
    monkeypatch.setattr("src.data.uspto_patentsview.httpx.post", _boom)
    out = fetch_patents_for_assignee("Apple Inc.", since_date="2025-05-15")
    assert out == []  # silent {} on failure, logged via log_api_call
