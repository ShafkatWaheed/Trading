"""Tests for Senate eFD PTR ingest pipeline.

Network access is dependency-injected (httpx never called). The DataTables
search JSON and the electronic-PTR HTML are fed as canned fixtures.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.data import senate_efd
from src.utils.db import get_connection, init_db


def test_init_db_creates_senate_tables():
    init_db()
    conn = get_connection()
    names = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name IN ('senate_efd_trades', 'senate_efd_index')"
        )
    }
    conn.close()
    assert names == {"senate_efd_trades", "senate_efd_index"}


def test_norm_txn_maps_senate_labels():
    assert senate_efd._norm_txn("Purchase") == "buy"
    assert senate_efd._norm_txn("Sale (Full)") == "sell"
    assert senate_efd._norm_txn("Sale (Partial)") == "sell"
    assert senate_efd._norm_txn("Exchange") == "exchange"
    assert senate_efd._norm_txn("weird") == "unknown"


def test_norm_date_and_amounts():
    assert senate_efd._norm_date("03/16/2026") == "2026-03-16"
    assert senate_efd._norm_date("garbage") == "garbage"
    assert senate_efd._parse_amount_range("$1,001 - $15,000") == (1001, 15000)
    assert senate_efd._parse_amount_range("no dollars here") == (0, 0)


def test_parse_amount_range_handles_endash():
    assert senate_efd._parse_amount_range("$1,001 – $15,000") == (1001, 15000)


# Captured shape of an electronic PTR transactions table (sanitized).
_PTR_HTML = """
<html><body>
<table class="table table-striped">
  <thead><tr>
    <th>#</th><th>Transaction Date</th><th>Owner</th><th>Ticker</th>
    <th>Asset Name</th><th>Asset Type</th><th>Type</th>
    <th>Amount</th><th>Comment</th>
  </tr></thead>
  <tbody>
    <tr>
      <td>1</td><td>03/16/2026</td><td>Self</td>
      <td><a href="/search/...">AAPL</a></td>
      <td>Apple Inc.</td><td>Stock</td><td>Purchase</td>
      <td>$1,001 - $15,000</td><td>--</td>
    </tr>
    <tr>
      <td>2</td><td>03/17/2026</td><td>Spouse</td>
      <td>NVDA</td>
      <td>NVIDIA Corp</td><td>Stock</td><td>Sale (Full)</td>
      <td>$15,001 - $50,000</td><td>--</td>
    </tr>
    <tr>
      <td>3</td><td>03/18/2026</td><td>Self</td>
      <td>--</td>
      <td>US Treasury Bond</td><td>Corporate Bond</td><td>Purchase</td>
      <td>$1,001 - $15,000</td><td>--</td>
    </tr>
  </tbody>
</table>
</body></html>
"""


def test_parse_ptr_html_extracts_tickered_rows():
    out = senate_efd.parse_ptr_html(_PTR_HTML)
    # The tickerless treasury row (ticker '--') is dropped.
    assert len(out) == 2
    by_t = {r["ticker"]: r for r in out}
    assert by_t["AAPL"]["transaction_code"] == "Purchase"
    assert by_t["AAPL"]["asset_type"] == "Stock"
    assert by_t["AAPL"]["transaction_date_raw"] == "03/16/2026"
    assert by_t["AAPL"]["amount_low"] == 1001
    assert by_t["AAPL"]["amount_high"] == 15000
    assert by_t["NVDA"]["transaction_code"] == "Sale (Full)"
    assert by_t["NVDA"]["amount_high"] == 50000


def test_parse_ptr_html_empty_when_no_table():
    assert senate_efd.parse_ptr_html("<html><body>No table</body></html>") == []


def _make_data_page(rows: list, total: int | None = None) -> dict:
    """Shape of the DataTables /report/data/ JSON response."""
    return {"data": rows, "recordsTotal": total if total is not None else len(rows),
            "recordsFiltered": total if total is not None else len(rows)}


def test_fetch_index_classifies_and_caps():
    # row = [first, last, office, report_link_html, date_received]
    page = _make_data_page([
        ["Mark", "Warner", "Warner, Mark R. (Senator)",
         '<a href="/search/view/ptr/aaa-111/" target="_blank">PTR</a>', "03/31/2026"],
        ["Jane", "Doe", "Doe, Jane (Senator)",
         '<a href="/search/view/paper/bbb-222/">PTR (paper)</a>', "03/30/2026"],
        ["Ron", "Roe", "Roe, Ron (Senator)",
         '<a href="/search/view/ptr/ccc-333/">PTR</a>', "03/29/2026"],
    ])
    calls = []

    def fake_search(start, length, start_date, end_date):
        calls.append((start, length))
        return page if start == 0 else _make_data_page([])

    out = senate_efd.fetch_index(days=30, max_docs=2, search_fn=fake_search)
    assert len(out) == 2  # capped at max_docs
    assert out[0]["filing_uuid"] == "aaa-111"
    assert out[0]["doc_kind"] == "electronic"
    assert out[0]["politician_name"] == "Mark Warner"
    assert out[0]["filing_date"] == "2026-03-31"
    assert out[1]["doc_kind"] == "paper"
    assert out[1]["filing_uuid"] == "bbb-222"


def test_fetch_index_search_error_returns_empty():
    def boom(start, length, start_date, end_date):
        raise RuntimeError("portal down")
    assert senate_efd.fetch_index(days=30, search_fn=boom) == []
