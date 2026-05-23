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


SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<results>
  <investigations>
    <investigation>
      <investigationNumber>337-TA-1234</investigationNumber>
      <investigationPhase>Final</investigationPhase>
      <investigationStatus>Active</investigationStatus>
      <investigationTitle>Certain Apple devices and related products</investigationTitle>
      <investigationType>Section 337</investigationType>
    </investigation>
    <investigation>
      <investigationNumber>1205-007</investigationNumber>
      <investigationStatus>Active</investigationStatus>
      <investigationTitle>Proposed Modifications to the Harmonized Tariff Schedule</investigationTitle>
      <investigationType>Tariff Affairs &amp; Trade Agreements</investigationType>
    </investigation>
  </investigations>
</results>
"""


class _FakeXmlResp:
    def __init__(self, text, status=200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_fetch_337_returns_investigations_matching_party(monkeypatch):
    monkeypatch.setattr(
        "src.data.itc_edis.httpx.get",
        lambda *a, **k: _FakeXmlResp(SAMPLE_XML),
    )
    out = fetch_337_investigations_for_party("Apple")
    # Only the Section 337 investigation matching "Apple" in the title
    assert len(out) == 1
    assert out[0]["investigation_number"] == "337-TA-1234"
    assert out[0]["status"] == "Active"
    assert "Apple" in out[0]["title"]
    assert out[0]["party_name"] == "Apple"
    assert out[0]["party_role"] == "unknown"


def test_fetch_337_filters_out_non_section_337(monkeypatch):
    monkeypatch.setattr(
        "src.data.itc_edis.httpx.get",
        lambda *a, **k: _FakeXmlResp(SAMPLE_XML),
    )
    out = fetch_337_investigations_for_party("Modifications")
    # 1205-007 is in the XML and the title matches, but it's NOT Section 337 — filter out
    assert out == []


def test_fetch_337_returns_empty_on_network_error(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr("src.data.itc_edis.httpx.get", _boom)
    assert fetch_337_investigations_for_party("Apple") == []
