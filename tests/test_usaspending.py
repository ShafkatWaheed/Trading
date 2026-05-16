"""Tests for USAspending fetcher (Wave 2, Phase E.1)."""
from __future__ import annotations

import pytest

from src.data.usaspending import fetch_contracts_for_uei
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


def test_fetch_contracts_returns_list_with_required_fields(monkeypatch):
    fake = {
        "results": [
            {
                "Award ID": "W56HZV-23-C-0001",
                "Recipient Name": "LOCKHEED MARTIN CORPORATION",
                "Award Amount": 4200000000,
                "Award Type": "BPA Call",
                "Action Date": "2026-01-15",
                "Awarding Agency": "Department of Defense",
            },
            {
                "Award ID": "FA8650-24-C-0042",
                "Recipient Name": "LOCKHEED MARTIN CORPORATION",
                "Award Amount": 850000000,
                "Award Type": "Definitive Contract",
                "Action Date": "2026-03-02",
                "Awarding Agency": "Department of the Air Force",
            },
        ],
        "page_metadata": {"page": 1, "hasNext": False},
    }
    monkeypatch.setattr(
        "src.data.usaspending.httpx.post",
        lambda *a, **k: _FakeResp(fake),
    )
    out = fetch_contracts_for_uei("ABCD1234EFGH", since_date="2025-05-15")
    assert len(out) == 2
    assert out[0]["award_id"] == "W56HZV-23-C-0001"
    assert out[0]["award_amount"] == 4200000000
    assert out[0]["awarding_agency"] == "Department of Defense"
    assert out[0]["action_date"] == "2026-01-15"


def test_fetch_contracts_returns_empty_on_no_results(monkeypatch):
    monkeypatch.setattr(
        "src.data.usaspending.httpx.post",
        lambda *a, **k: _FakeResp({"results": [], "page_metadata": {}}),
    )
    out = fetch_contracts_for_uei("ZZZZNOPEZZZZ", since_date="2025-05-15")
    assert out == []


def test_fetch_contracts_returns_empty_on_network_error(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("network down")
    monkeypatch.setattr("src.data.usaspending.httpx.post", _boom)
    out = fetch_contracts_for_uei("ABCD1234EFGH", since_date="2025-05-15")
    assert out == []  # silent [] on failure, logged via log_api_call
