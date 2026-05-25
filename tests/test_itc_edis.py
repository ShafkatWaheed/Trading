"""Tests for ITC EDIS §337 fetcher (Wave 2, Phase F).

The fetcher pages through https://edis.usitc.gov/data/document with
`investigationType=Sec 337&investigationStatus=Active`, then aggregates
documents per investigation so we can match the requested party name
against the `<onBehalfOf>` strings. Tests monkeypatch `httpx.get` to
return canned EDIS-shaped XML and assert the normalized dict shape.
"""
from __future__ import annotations

import pytest

from src.data import itc_edis
from src.data.itc_edis import fetch_337_investigations_for_party
from src.utils.db import init_db


@pytest.fixture(autouse=True)
def _isolated_fetch_state():
    """Ensure schema is bootstrapped and the cached active-§337 index is empty.

    The fetcher caches its aggregated index in the SQLite `cache` table —
    that table must exist (init_db) and must not retain rows between tests.
    """
    init_db()
    from src.utils.db import cache_delete
    cache_delete(itc_edis._CACHE_KEY)
    yield
    cache_delete(itc_edis._CACHE_KEY)


# Single-page response (fewer than _PAGE_SIZE rows so the pager stops after page 1).
SAMPLE_DOCS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<results>
  <documents>
    <document>
      <id>1</id>
      <documentType>Motion</documentType>
      <documentTitle>Respondent Apple Inc.'s Motion to Dismiss</documentTitle>
      <onBehalfOf>Apple Inc.</onBehalfOf>
      <investigationNumber>337-1234</investigationNumber>
      <investigationType>Sec 337</investigationType>
      <investigationStatus>Active</investigationStatus>
      <investigationTitle>Certain Mobile Communications Devices; Inv. No. 337-TA-1234</investigationTitle>
      <documentDate>2026/03/15 00:00:00</documentDate>
    </document>
    <document>
      <id>2</id>
      <documentType>Notice</documentType>
      <documentTitle>Complainants' Notice of Prior Art</documentTitle>
      <onBehalfOf>UnaliWear, Inc.</onBehalfOf>
      <investigationNumber>337-1234</investigationNumber>
      <investigationType>Sec 337</investigationType>
      <investigationStatus>Active</investigationStatus>
      <investigationTitle>Certain Mobile Communications Devices; Inv. No. 337-TA-1234</investigationTitle>
      <documentDate>2026/02/01 00:00:00</documentDate>
    </document>
    <document>
      <id>3</id>
      <documentType>Order</documentType>
      <documentTitle>Final Determination</documentTitle>
      <onBehalfOf>Office of the Secretary</onBehalfOf>
      <investigationNumber>701-999</investigationNumber>
      <investigationType>Import Injury</investigationType>
      <investigationStatus>Active</investigationStatus>
      <investigationTitle>Some non-337 import-injury case</investigationTitle>
      <documentDate>2026/04/01 00:00:00</documentDate>
    </document>
  </documents>
</results>
"""


class _FakeXmlResp:
    def __init__(self, text, status=200):
        self.text = text
        self.status_code = status


def _stub_httpx_get(body: str):
    def _stub(*a, **k):
        return _FakeXmlResp(body)
    return _stub


def test_fetch_337_returns_investigations_matching_party(monkeypatch):
    monkeypatch.setattr(itc_edis.httpx, "get", _stub_httpx_get(SAMPLE_DOCS_XML))
    monkeypatch.setattr(itc_edis.time, "sleep", lambda *a, **k: None)

    out = fetch_337_investigations_for_party("Apple")

    # One §337 investigation matched; the 701-999 import-injury row is filtered.
    assert len(out) == 1
    row = out[0]
    assert row["investigation_number"] == "337-1234"
    assert row["status"] == "Active"
    assert "Mobile Communications" in row["title"]
    assert row["party_name"] == "Apple"
    # Document title "Respondent Apple Inc.'s Motion..." → role inferred as respondent.
    assert row["party_role"] == "respondent"
    # filing_date is the earliest documentDate seen in the investigation.
    assert row["filing_date"] == "2026-02-01"


def test_fetch_337_word_boundary_filters_substring_false_positive(monkeypatch):
    """'Intel' must not match 'CCC Intelligent Solutions Inc.'."""
    body = SAMPLE_DOCS_XML.replace(
        "<onBehalfOf>Apple Inc.</onBehalfOf>",
        "<onBehalfOf>CCC Intelligent Solutions Inc.</onBehalfOf>",
    )
    monkeypatch.setattr(itc_edis.httpx, "get", _stub_httpx_get(body))
    monkeypatch.setattr(itc_edis.time, "sleep", lambda *a, **k: None)

    out = fetch_337_investigations_for_party("Intel")
    assert out == []


def test_fetch_337_returns_empty_on_network_error(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(itc_edis.httpx, "get", _boom)
    monkeypatch.setattr(itc_edis.time, "sleep", lambda *a, **k: None)

    assert fetch_337_investigations_for_party("Apple") == []


def test_fetch_337_returns_empty_on_no_match(monkeypatch):
    monkeypatch.setattr(itc_edis.httpx, "get", _stub_httpx_get(SAMPLE_DOCS_XML))
    monkeypatch.setattr(itc_edis.time, "sleep", lambda *a, **k: None)

    # No active §337 investigation involves NotARealCompany.
    assert fetch_337_investigations_for_party("NotARealCompany") == []
