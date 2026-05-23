"""Tests for FDA Orange Book bulk-download cache + sponsor query."""
from __future__ import annotations

import io
import zipfile

import pytest

from src.data.fda_orange_book import fetch_patents_for_sponsor
from src.utils.db import get_connection, init_db


def _make_orange_book_zip() -> bytes:
    """Build a tiny in-memory Orange Book ZIP matching the FDA file format."""
    # FDA uses tilde-delimited (~). Header line then 1+ data lines.
    products_txt = (
        "Ingredient~DF;Route~Trade_Name~Applicant~Strength~Appl_Type~Appl_No"
        "~Product_No~TE_Code~Approval_Date~RLD~RS~Type~Applicant_Full_Name\n"
        "PALBOCICLIB~CAPSULE;ORAL~IBRANCE~PFIZER~75MG~N~207103~001~~AP~Yes~Yes"
        "~RX~PFIZER INC\n"
        "ATORVASTATIN CALCIUM~TABLET;ORAL~LIPITOR OLD~PFIZER~10MG~N~020702~001"
        "~AB~AP~Yes~Yes~RX~PFIZER INC\n"
    )
    patent_txt = (
        "Appl_Type~Appl_No~Product_No~Patent_No~Patent_Expire_Date_Text"
        "~Drug_Substance_Flag~Drug_Product_Flag~Patent_Use_Code~Delist_Flag"
        "~Submission_Date\n"
        "N~207103~001~8685975~Aug 15, 2026~Y~~U-1234~~Feb 5, 2015\n"
        "N~207103~001~9381196~Aug 15, 2026~~Y~~~Mar 10, 2016\n"
        "N~020702~001~5273995~Mar 24, 2010~Y~~~~Jul 1, 2003\n"
    )
    exclusivity_txt = "Appl_Type~Appl_No~Product_No~Exclusivity_Code~Exclusivity_Date\n"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("products.txt", products_txt)
        z.writestr("patent.txt", patent_txt)
        z.writestr("exclusivity.txt", exclusivity_txt)
    return buf.getvalue()


class _FakeResp:
    def __init__(self, content: bytes, status: int = 200):
        self.content = content
        self.status_code = status
    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture(autouse=True)
def _clean_cache():
    init_db()
    conn = get_connection()
    conn.execute("DELETE FROM orange_book_patents")
    conn.commit()
    conn.close()
    yield
    conn = get_connection()
    conn.execute("DELETE FROM orange_book_patents")
    conn.commit()
    conn.close()


def test_fetch_patents_returns_normalized_rows_for_sponsor():
    fake_zip = _make_orange_book_zip()
    fake_get = lambda url: _FakeResp(fake_zip)
    out = fetch_patents_for_sponsor("PFIZER", http_get=fake_get)

    # All 3 patents in the fake fixture map to PFIZER applications
    assert len(out) == 3
    # Sorted by expire date ascending — 2010 first, then 2 from 2026
    assert out[0]["patent_number"] == "5273995"
    assert out[0]["trade_name"] == "LIPITOR OLD"
    assert out[1]["application_number"] == "207103"
    assert "IBRANCE" in out[1]["trade_name"]
    assert out[1]["drug_substance_flag"] is True
    assert out[2]["drug_product_flag"] is True
    assert out[1]["use_code"] == "U-1234"


def test_fetch_patents_filters_by_sponsor_name():
    fake_zip = _make_orange_book_zip()
    fake_get = lambda url: _FakeResp(fake_zip)
    out = fetch_patents_for_sponsor("LILLY", http_get=fake_get)
    # No LILLY applications in our fixture
    assert out == []


def test_fetch_patents_empty_sponsor_returns_empty():
    assert fetch_patents_for_sponsor("") == []
    assert fetch_patents_for_sponsor("   ") == []


def test_fetch_patents_network_error_returns_empty():
    def _boom(url):
        raise RuntimeError("network down")
    out = fetch_patents_for_sponsor("PFIZER", http_get=_boom)
    assert out == []


def test_fetch_patents_uses_cache_on_second_call():
    """Once the cache is fresh, subsequent calls don't refetch."""
    call_count = {"n": 0}
    fake_zip = _make_orange_book_zip()
    def counting_fetch(url):
        call_count["n"] += 1
        return _FakeResp(fake_zip)

    fetch_patents_for_sponsor("PFIZER", http_get=counting_fetch)
    fetch_patents_for_sponsor("PFIZER", http_get=counting_fetch)
    fetch_patents_for_sponsor("PFIZER", http_get=counting_fetch)
    # First call refreshed the cache; second + third hit the local cache
    assert call_count["n"] == 1
