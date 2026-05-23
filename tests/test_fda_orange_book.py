"""Tests for FDA Orange Book fetcher (Patent Events card)."""
from __future__ import annotations

import pytest

from src.data.fda_orange_book import fetch_patents_for_sponsor
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


def test_fetch_patents_returns_flattened_list(monkeypatch):
    """2 products * 2 patents each => 4 normalized rows."""
    fake = {
        "results": [
            {
                "application_number": "NDA207103",
                "sponsor_name": "PFIZER INC",
                "products": [
                    {"brand_name": "IBRANCE", "active_ingredients": []}
                ],
                "openfda": {
                    "brand_name": ["IBRANCE"],
                    "manufacturer_name": ["PFIZER INC"],
                },
                "patents": [
                    {
                        "patent_number": "8685975",
                        "patent_expire_date": "2028-08-15",
                        "drug_substance_flag": "Y",
                        "drug_product_flag": "N",
                        "patent_use_code": "U-1234",
                    },
                    {
                        "patent_number": "9018225",
                        "patent_expire_date": "2030-03-20",
                        "drug_substance_flag": "N",
                        "drug_product_flag": "Y",
                        "patent_use_code": "U-5678",
                    },
                ],
            },
            {
                "application_number": "NDA210259",
                "sponsor_name": "PFIZER INC",
                "products": [
                    {"brand_name": "VYNDAQEL", "active_ingredients": []}
                ],
                "openfda": {
                    "brand_name": ["VYNDAQEL"],
                    "manufacturer_name": ["PFIZER INC"],
                },
                "patents": [
                    {
                        "patent_number": "7560488",
                        "patent_expire_date": "2026-12-01",
                        "drug_substance_flag": "Y",
                        "drug_product_flag": "N",
                    },
                    {
                        "patent_number": "9770441",
                        "patent_expire_date": "2031-05-10",
                        "drug_substance_flag": "N",
                        "drug_product_flag": "Y",
                    },
                ],
            },
        ],
        "meta": {"results": {"total": 2}},
    }
    monkeypatch.setattr(
        "src.data.fda_orange_book.httpx.get",
        lambda *a, **k: _FakeResp(fake),
    )

    out = fetch_patents_for_sponsor("PFIZER INC")

    assert len(out) == 4
    # First product, first patent
    assert out[0]["application_number"] == "NDA207103"
    assert out[0]["patent_number"] == "8685975"
    assert out[0]["patent_expire_date"] == "2028-08-15"
    assert out[0]["drug_substance_flag"] is True
    assert out[0]["drug_product_flag"] is False
    assert out[0]["use_code"] == "U-1234"
    assert out[0]["sponsor_name"] == "PFIZER INC"
    assert out[0]["trade_name"] == "IBRANCE"
    # Second product, second patent
    assert out[3]["application_number"] == "NDA210259"
    assert out[3]["patent_number"] == "9770441"
    assert out[3]["patent_expire_date"] == "2031-05-10"
    assert out[3]["drug_substance_flag"] is False
    assert out[3]["drug_product_flag"] is True
    assert out[3]["trade_name"] == "VYNDAQEL"


def test_fetch_patents_returns_empty_on_no_results(monkeypatch):
    monkeypatch.setattr(
        "src.data.fda_orange_book.httpx.get",
        lambda *a, **k: _FakeResp({"results": [], "meta": {"results": {"total": 0}}}),
    )
    out = fetch_patents_for_sponsor("Nonexistent Pharma")
    assert out == []


def test_fetch_patents_returns_empty_on_network_error(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr("src.data.fda_orange_book.httpx.get", _boom)
    out = fetch_patents_for_sponsor("PFIZER INC")
    assert out == []  # silent [] on failure, logged via log_api_call
