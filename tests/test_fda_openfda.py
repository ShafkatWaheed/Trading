"""Tests for openFDA fetcher (Wave 2, Phase D)."""
from __future__ import annotations

import pytest

from src.data.fda_openfda import fetch_fda_applications_for_sponsor
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


def test_fetch_fda_applications_returns_normalized_list(monkeypatch):
    fake = {
        "results": [
            {
                "application_number": "NDA022345",
                "sponsor_name": "PFIZER INC",
                "submissions": [
                    {
                        "submission_type": "ORIG",
                        "submission_status": "AP",
                        "submission_status_date": "20260115",
                    }
                ],
            },
            {
                "application_number": "BLA125678",
                "sponsor_name": "PFIZER INC",
                "submissions": [
                    {
                        "submission_type": "SUPPL",
                        "submission_status": "TA",
                        "submission_status_date": "20260220",
                    }
                ],
            },
        ],
        "meta": {"results": {"total": 2}},
    }
    monkeypatch.setattr(
        "src.data.fda_openfda.httpx.get",
        lambda *a, **k: _FakeResp(fake),
    )
    out = fetch_fda_applications_for_sponsor("PFIZER INC")
    assert len(out) == 2
    assert out[0]["application_number"] == "NDA022345"
    assert out[0]["sponsor_name"] == "PFIZER INC"
    assert out[0]["submission_type"] == "ORIG"
    assert out[0]["submission_status"] == "AP"
    assert out[0]["action_date"] == "20260115"


def test_fetch_fda_applications_returns_empty_on_no_results(monkeypatch):
    monkeypatch.setattr(
        "src.data.fda_openfda.httpx.get",
        lambda *a, **k: _FakeResp({"results": [], "meta": {"results": {"total": 0}}}),
    )
    out = fetch_fda_applications_for_sponsor("Nonexistent Pharma")
    assert out == []


def test_fetch_fda_applications_returns_empty_on_network_error(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr("src.data.fda_openfda.httpx.get", _boom)
    out = fetch_fda_applications_for_sponsor("PFIZER INC")
    assert out == []  # silent [] on failure, logged via log_api_call
