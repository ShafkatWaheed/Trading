"""Tests for ITC EDIS §337 fetcher (Wave 2, Phase F)."""
from __future__ import annotations

import pytest

from src.data.itc_edis import fetch_337_investigations_for_party
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


def test_fetch_337_returns_list_with_complainant_and_respondent(monkeypatch):
    fake = {
        "investigations": [
            {
                "investigation_number": "337-TA-1234",
                "title": "Certain Mobile Devices and Components Thereof",
                "status": "Active",
                "filing_date": "2026-02-01",
                "parties": [
                    {"name": "Apple Inc.", "role": "Complainant"},
                    {"name": "Acme Imports LLC", "role": "Respondent"},
                ],
            },
            {
                "investigation_number": "337-TA-1235",
                "title": "Certain Wireless Audio Equipment",
                "status": "Active",
                "filing_date": "2026-03-15",
                "parties": [
                    {"name": "Foo Holdings", "role": "Complainant"},
                    {"name": "Apple Inc.", "role": "Respondent"},
                ],
            },
        ],
    }
    monkeypatch.setattr(
        "src.data.itc_edis.httpx.get",
        lambda *a, **k: _FakeResp(fake),
    )
    out = fetch_337_investigations_for_party("Apple Inc.")
    assert len(out) == 4  # 2 parties per investigation × 2 investigations
    roles = {row["party_role"] for row in out}
    assert "complainant" in roles
    assert "respondent" in roles
    # First investigation, first party
    assert out[0]["investigation_number"] == "337-TA-1234"
    assert out[0]["title"].startswith("Certain Mobile")
    assert out[0]["filing_date"] == "2026-02-01"


def test_fetch_337_returns_empty_on_no_results(monkeypatch):
    monkeypatch.setattr(
        "src.data.itc_edis.httpx.get",
        lambda *a, **k: _FakeResp({"investigations": []}),
    )
    out = fetch_337_investigations_for_party("Nonexistent Co")
    assert out == []


def test_fetch_337_returns_empty_on_network_error(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("network down")
    monkeypatch.setattr("src.data.itc_edis.httpx.get", _boom)
    out = fetch_337_investigations_for_party("Apple Inc.")
    assert out == []  # silent [] on failure, logged via log_api_call
