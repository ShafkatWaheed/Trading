"""Tests for USAspending name-based fetcher (fetch_contracts_for_recipient).

Mirrors tests/test_usaspending.py but exercises the name-search code path.
USAspending's `recipient_search_text` filter accepts arbitrary recipient
names (case-insensitive substring match), so we can query by company name
when UEI quality is uncertain.
"""
from __future__ import annotations

import pytest

from src.data.usaspending import fetch_contracts_for_recipient
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


def test_fetch_contracts_for_recipient_returns_normalized_list(monkeypatch):
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
                "Recipient Name": "SIKORSKY SUPPORT SERVICES",
                "Award Amount": 850000000,
                "Award Type": "Definitive Contract",
                "Action Date": "2026-03-02",
                "Awarding Agency": "Department of the Air Force",
            },
        ],
        "page_metadata": {"page": 1, "hasNext": False},
    }

    captured: dict = {}

    def _fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["body"] = json
        return _FakeResp(fake)

    monkeypatch.setattr("src.data.usaspending.httpx.post", _fake_post)
    out = fetch_contracts_for_recipient(
        "Lockheed Martin Corporation", since_date="2025-05-15"
    )

    # Body shape is correct: name lands in recipient_search_text.
    assert captured["body"]["filters"]["recipient_search_text"] == [
        "Lockheed Martin Corporation"
    ]
    assert "A" in captured["body"]["filters"]["award_type_codes"]

    # Normalization matches fetch_contracts_for_uei exactly.
    assert len(out) == 2
    assert out[0]["award_id"] == "W56HZV-23-C-0001"
    assert out[0]["recipient_name"] == "LOCKHEED MARTIN CORPORATION"
    assert out[0]["award_amount"] == 4200000000
    assert out[1]["awarding_agency"] == "Department of the Air Force"


def test_fetch_contracts_for_recipient_returns_empty_on_no_results(monkeypatch):
    monkeypatch.setattr(
        "src.data.usaspending.httpx.post",
        lambda *a, **k: _FakeResp({"results": [], "page_metadata": {}}),
    )
    out = fetch_contracts_for_recipient(
        "NoSuchCompanyXYZ", since_date="2025-05-15"
    )
    assert out == []


def test_fetch_contracts_for_recipient_returns_empty_on_network_error(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr("src.data.usaspending.httpx.post", _boom)
    out = fetch_contracts_for_recipient(
        "Lockheed Martin Corporation", since_date="2025-05-15"
    )
    assert out == []  # silent [] on failure, logged via log_api_call
