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


def test_fetch_fda_normalizes_sponsor_name_and_queries_correct_field(monkeypatch):
    """Regression: 'Pfizer Inc.' must be normalized before hitting openFDA.

    The raw user-supplied name with punctuation/suffixes 404s against
    openFDA's exact-phrase indices. We strip them and try the
    `openfda.manufacturer_name` phrase plus `sponsor_name` first-token.
    """
    captured_urls: list[str] = []

    def _capture(url, *a, **k):
        captured_urls.append(url)
        return _FakeResp({"results": [], "meta": {"results": {"total": 0}}})

    monkeypatch.setattr("src.data.fda_openfda.httpx.get", _capture)
    fetch_fda_applications_for_sponsor("Pfizer Inc.")

    # Both query strategies should have been attempted; both should use the
    # uppercased, suffix-stripped name (PFIZER), never the raw "Pfizer Inc.".
    assert any("openfda.manufacturer_name" in u and "PFIZER" in u for u in captured_urls), captured_urls
    assert any("sponsor_name" in u and "PFIZER" in u for u in captured_urls), captured_urls
    assert not any("Pfizer%20Inc" in u or "Pfizer+Inc" in u or "Inc." in u for u in captured_urls), captured_urls


def test_fetch_fda_treats_openfda_404_as_empty_not_error(monkeypatch):
    """openFDA returns HTTP 404 for 'no results found' — must surface as []."""
    def _404(*a, **k):
        return _FakeResp({}, status=404)

    monkeypatch.setattr("src.data.fda_openfda.httpx.get", _404)
    out = fetch_fda_applications_for_sponsor("Nonexistent Sponsor")
    assert out == []
