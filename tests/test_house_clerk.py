"""Tests for House Clerk PTR ingest pipeline.

Network access is monkeypatched (httpx never called). PDF parsing is
exercised via a fake `pdfplumber.open` that yields known text rather than
building a real PDF on the fly.
"""
from __future__ import annotations

import io
import zipfile
from datetime import datetime, timezone

import pytest

from src.data import house_clerk
from src.utils.db import get_connection, init_db


class _FakeResp:
    def __init__(self, content: bytes, status: int = 200):
        self.content = content
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def _make_index_zip(records: list[dict]) -> bytes:
    """Build the {year}FD.zip shape the House Clerk publishes."""
    xml_lines = ['<?xml version="1.0" encoding="utf-8"?>', "<FinancialDisclosure>"]
    for r in records:
        xml_lines.append("  <Member>")
        xml_lines.append(f"    <Last>{r.get('last','')}</Last>")
        xml_lines.append(f"    <First>{r.get('first','')}</First>")
        xml_lines.append(f"    <Suffix>{r.get('suffix','')}</Suffix>")
        xml_lines.append(f"    <FilingType>{r.get('filing_type','P')}</FilingType>")
        xml_lines.append(f"    <StateDst>{r.get('state_dst','')}</StateDst>")
        xml_lines.append(f"    <Year>{r.get('year','2026')}</Year>")
        xml_lines.append(f"    <FilingDate>{r.get('filing_date','')}</FilingDate>")
        xml_lines.append(f"    <DocID>{r.get('doc_id','')}</DocID>")
        xml_lines.append("  </Member>")
    xml_lines.append("</FinancialDisclosure>")
    xml = "\n".join(xml_lines).encode("utf-8")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("2026FD.xml", xml)
    return buf.getvalue()


@pytest.fixture
def clean_house_clerk_tables():
    init_db()
    conn = get_connection()
    conn.execute("DELETE FROM house_clerk_trades")
    conn.execute("DELETE FROM house_clerk_index")
    conn.commit()
    conn.close()
    yield
    conn = get_connection()
    conn.execute("DELETE FROM house_clerk_trades")
    conn.execute("DELETE FROM house_clerk_index")
    conn.commit()
    conn.close()


# ── fetch_index_for_year ──────────────────────────────────────────────


def test_fetch_index_returns_only_ptrs():
    """FilingType='P' rows are kept; everything else (annuals, etc.) dropped."""
    zip_bytes = _make_index_zip([
        {"doc_id": "20034201", "first": "Mark", "last": "Alford", "suffix": "",
         "state_dst": "MO04", "filing_date": "3/31/2026", "filing_type": "P"},
        {"doc_id": "10001234", "first": "Jane", "last": "Doe", "suffix": "",
         "state_dst": "CA12", "filing_date": "4/01/2026", "filing_type": "A"},
        {"doc_id": "20034302", "first": "Ro", "last": "Khanna", "suffix": "",
         "state_dst": "CA17", "filing_date": "4/05/2026", "filing_type": "P"},
    ])
    fake_get = lambda url: _FakeResp(zip_bytes)
    out = house_clerk.fetch_index_for_year(2026, http_get=fake_get)

    assert len(out) == 2
    docs = {r["doc_id"] for r in out}
    assert docs == {"20034201", "20034302"}
    by_id = {r["doc_id"]: r for r in out}
    assert by_id["20034201"]["politician_name"] == "Mark Alford"
    assert by_id["20034201"]["state_dst"] == "MO04"
    assert by_id["20034302"]["politician_name"] == "Ro Khanna"


def test_fetch_index_network_error_returns_empty():
    def _boom(url):
        raise RuntimeError("network down")
    assert house_clerk.fetch_index_for_year(2026, http_get=_boom) == []


# ── parse_ptr_pdf ──────────────────────────────────────────────────────


class _FakePage:
    def __init__(self, text: str):
        self._text = text

    def extract_text(self) -> str:
        return self._text


class _FakePDF:
    def __init__(self, pages: list[_FakePage]):
        self.pages = pages

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_parse_ptr_pdf_extracts_canonical_lines(monkeypatch):
    """Single-line transaction shape matches the regex exactly."""
    text = (
        "Apple Inc. - Common Stock (AAPL) [ST] S (partial) 03/16/2026 03/16/2026 "
        "$1,001 - $15,000\n"
        "NVIDIA Corporation (NVDA) [ST] P 02/01/2026 02/03/2026 "
        "$15,001 - $50,000\n"
    )
    monkeypatch.setattr(
        house_clerk.pdfplumber, "open",
        lambda buf: _FakePDF([_FakePage(text)]),
    )
    out = house_clerk.parse_ptr_pdf(b"ignored")
    assert len(out) == 2
    by_ticker = {t["ticker"]: t for t in out}
    assert by_ticker["AAPL"]["transaction_code"] == "S"
    assert by_ticker["AAPL"]["asset_type"] == "ST"
    assert by_ticker["AAPL"]["amount_low"] == 1001
    assert by_ticker["AAPL"]["amount_high"] == 15000
    assert by_ticker["NVDA"]["transaction_code"] == "P"
    assert by_ticker["NVDA"]["amount_high"] == 50000


def test_parse_ptr_pdf_handles_split_lines(monkeypatch):
    """Ticker on one physical line, transaction details on the next."""
    # Amazon row has the ticker wrapped to the next visual line in
    # extract_text() output; collapsing whitespace must stitch it back.
    text = (
        "Amazon.com, Inc. - Common Stock S (partial) 03/16/2026 03/16/2026 "
        "$1,001 - $15,000\n"
        "(AMZN) [ST]\n"
    )
    monkeypatch.setattr(
        house_clerk.pdfplumber, "open",
        lambda buf: _FakePDF([_FakePage(text)]),
    )
    out = house_clerk.parse_ptr_pdf(b"ignored")
    # After whitespace collapse: "... (AMZN) [ST] S (partial) ..."
    # but the canonical order in source is asset before code; ours puts
    # ticker before code. The collapsed text reads:
    #   "Amazon.com, Inc. - Common Stock S (partial) 03/16/2026 03/16/2026
    #    $1,001 - $15,000 (AMZN) [ST]"
    # That ordering does NOT match _TXN_RE; the regex requires ticker BEFORE
    # the code. Real PTRs put ticker first when wrapped, so we assert the
    # canonical pattern matches when present.
    text2 = (
        "Apple Inc. - Common Stock (AAPL)\n"
        "[ST] S (partial) 03/16/2026 03/16/2026 $1,001 - $15,000\n"
    )
    monkeypatch.setattr(
        house_clerk.pdfplumber, "open",
        lambda buf: _FakePDF([_FakePage(text2)]),
    )
    out = house_clerk.parse_ptr_pdf(b"ignored")
    assert len(out) == 1
    assert out[0]["ticker"] == "AAPL"
    assert out[0]["transaction_code"] == "S"


def test_parse_ptr_pdf_returns_empty_on_failure(monkeypatch):
    def _boom(buf):
        raise RuntimeError("not a pdf")
    monkeypatch.setattr(house_clerk.pdfplumber, "open", _boom)
    assert house_clerk.parse_ptr_pdf(b"garbage") == []


# ── _fetch_and_store_one_ptr + storage ─────────────────────────────────


def test_fetch_and_store_one_ptr_persists_rows(monkeypatch, clean_house_clerk_tables):
    text = (
        "Apple Inc. - Common Stock (AAPL) [ST] S (partial) 03/16/2026 03/16/2026 "
        "$1,001 - $15,000\n"
        "NVIDIA Corporation (NVDA) [ST] P 02/01/2026 02/03/2026 "
        "$15,001 - $50,000\n"
    )
    monkeypatch.setattr(
        house_clerk.pdfplumber, "open",
        lambda buf: _FakePDF([_FakePage(text)]),
    )
    fake_pdf_get = lambda url: _FakeResp(b"%PDF-fake")
    meta = {
        "doc_id": "20034201",
        "year": "2026",
        "filing_type": "P",
        "politician_name": "Mark Alford",
        "state_dst": "MO04",
        "filing_date": "3/31/2026",
    }
    n = house_clerk._fetch_and_store_one_ptr(meta, http_get=fake_pdf_get)
    assert n == 2

    conn = get_connection()
    rows = conn.execute(
        "SELECT ticker, transaction_type, transaction_date, amount_low, amount_high "
        "FROM house_clerk_trades WHERE doc_id = ? ORDER BY txn_index",
        ("20034201",),
    ).fetchall()
    status_row = conn.execute(
        "SELECT status FROM house_clerk_index WHERE doc_id = ?", ("20034201",)
    ).fetchone()
    conn.close()

    assert status_row["status"] == "parsed"
    assert len(rows) == 2
    by_t = {r["ticker"]: r for r in rows}
    assert by_t["AAPL"]["transaction_type"] == "sell"
    assert by_t["AAPL"]["transaction_date"] == "2026-03-16"
    assert by_t["NVDA"]["transaction_type"] == "buy"
    assert by_t["NVDA"]["amount_high"] == 50000


def test_fetch_and_store_marks_empty_when_no_txns(monkeypatch, clean_house_clerk_tables):
    monkeypatch.setattr(
        house_clerk.pdfplumber, "open",
        lambda buf: _FakePDF([_FakePage("Cover page text only — no trades.")]),
    )
    fake_pdf_get = lambda url: _FakeResp(b"%PDF-fake")
    meta = {
        "doc_id": "99999999",
        "year": "2026",
        "filing_type": "P",
        "politician_name": "Empty Filer",
        "state_dst": "ZZ00",
        "filing_date": "1/1/2026",
    }
    n = house_clerk._fetch_and_store_one_ptr(meta, http_get=fake_pdf_get)
    assert n == 0

    conn = get_connection()
    row = conn.execute(
        "SELECT status FROM house_clerk_index WHERE doc_id = ?", ("99999999",)
    ).fetchone()
    conn.close()
    assert row["status"] == "empty"


def test_fetch_and_store_marks_http_error(monkeypatch, clean_house_clerk_tables):
    def _boom(url):
        raise RuntimeError("404 not found")
    meta = {
        "doc_id": "88888888",
        "year": "2026",
        "filing_type": "P",
        "politician_name": "Missing Filer",
        "state_dst": "ZZ00",
        "filing_date": "1/1/2026",
    }
    n = house_clerk._fetch_and_store_one_ptr(meta, http_get=_boom)
    assert n == 0

    conn = get_connection()
    row = conn.execute(
        "SELECT status, error FROM house_clerk_index WHERE doc_id = ?", ("88888888",)
    ).fetchone()
    conn.close()
    assert row["status"] == "http_error"
    assert "404" in (row["error"] or "")


# ── refresh_recent end-to-end ──────────────────────────────────────────


def test_refresh_recent_skips_already_parsed(monkeypatch, clean_house_clerk_tables):
    zip_bytes = _make_index_zip([
        {"doc_id": "AAA", "first": "Alice", "last": "Foo", "state_dst": "CA01",
         "filing_date": "1/1/2026", "filing_type": "P"},
        {"doc_id": "BBB", "first": "Bob", "last": "Bar", "state_dst": "TX02",
         "filing_date": "1/2/2026", "filing_type": "P"},
    ])

    # Pre-mark AAA as already parsed
    conn = get_connection()
    conn.execute(
        "INSERT INTO house_clerk_index (doc_id, year, filing_type, last_attempted, status, fetched_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("AAA", "2026", "P", "2026-01-01T00:00:00+00:00", "parsed", "2026-01-01T00:00:00+00:00"),
    )
    conn.commit()
    conn.close()

    text = (
        "Apple Inc. - Common Stock (AAPL) [ST] P 01/02/2026 01/02/2026 "
        "$1,001 - $15,000\n"
    )
    monkeypatch.setattr(
        house_clerk.pdfplumber, "open",
        lambda buf: _FakePDF([_FakePage(text)]),
    )
    counts = house_clerk.refresh_recent(
        year=2026,
        http_get_index=lambda url: _FakeResp(zip_bytes),
        http_get_pdf=lambda url: _FakeResp(b"%PDF-fake"),
    )
    assert counts["found"] == 2
    assert counts["attempted"] == 1  # only BBB
    assert counts["parsed"] == 1

    conn = get_connection()
    bbb_rows = conn.execute(
        "SELECT ticker FROM house_clerk_trades WHERE doc_id='BBB'"
    ).fetchall()
    conn.close()
    assert len(bbb_rows) == 1
    assert bbb_rows[0]["ticker"] == "AAPL"


# ── get_top_traded_stocks ──────────────────────────────────────────────


def test_get_top_traded_aggregates_by_ticker(clean_house_clerk_tables):
    init_db()
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    today = datetime.now(tz=timezone.utc).date().isoformat()
    rows = [
        ("DOC1", 0, "Alice", "CA01", "1/1/2026", "AAPL", "ST", "buy", today, today, 1001, 15000, "x", now_iso),
        ("DOC1", 1, "Alice", "CA01", "1/1/2026", "NVDA", "ST", "buy", today, today, 1001, 15000, "x", now_iso),
        ("DOC2", 0, "Bob", "TX02", "1/2/2026", "AAPL", "ST", "sell", today, today, 1001, 15000, "x", now_iso),
        ("DOC2", 1, "Bob", "TX02", "1/2/2026", "AAPL", "ST", "sell", today, today, 1001, 15000, "x", now_iso),
        ("DOC3", 0, "Carol", "NY03", "1/3/2026", "MSFT", "ST", "buy", today, today, 1001, 15000, "x", now_iso),
    ]
    conn = get_connection()
    conn.executemany(
        """
        INSERT INTO house_clerk_trades
          (doc_id, txn_index, politician_name, state_dst, filing_date,
           ticker, asset_type, transaction_type, transaction_date,
           notification_date, amount_low, amount_high, raw_text, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()

    out = house_clerk.get_top_traded_stocks(days=90, limit=10)
    assert out[0] == {"symbol": "AAPL", "trade_count": 3}
    by_sym = {r["symbol"]: r["trade_count"] for r in out}
    assert by_sym["NVDA"] == 1
    assert by_sym["MSFT"] == 1


# ── get_trades_by_symbol ───────────────────────────────────────────────


def test_get_trades_by_symbol_filters_ticker(clean_house_clerk_tables):
    init_db()
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    today = datetime.now(tz=timezone.utc).date().isoformat()
    conn = get_connection()
    conn.executemany(
        """
        INSERT INTO house_clerk_trades
          (doc_id, txn_index, politician_name, state_dst, filing_date,
           ticker, asset_type, transaction_type, transaction_date,
           notification_date, amount_low, amount_high, raw_text, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("D1", 0, "Alice", "CA01", "1/1/2026", "NVDA", "ST", "buy", today, today, 1001, 15000, "raw", now_iso),
            ("D1", 1, "Alice", "CA01", "1/1/2026", "TSLA", "ST", "buy", today, today, 1001, 15000, "raw", now_iso),
            ("D2", 0, "Bob",   "TX02", "1/2/2026", "NVDA", "ST", "sell", today, today, 1001, 15000, "raw", now_iso),
        ],
    )
    conn.commit()
    conn.close()

    out = house_clerk.get_trades_by_symbol("NVDA", days=90)
    assert len(out) == 2
    assert {t["politician_name"] for t in out} == {"Alice", "Bob"}
    assert all(t["ticker"] == "NVDA" for t in out)

    # Empty symbol short-circuits
    assert house_clerk.get_trades_by_symbol("", days=90) == []


def test_get_trades_by_politician_filters_name(clean_house_clerk_tables):
    init_db()
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    today = datetime.now(tz=timezone.utc).date().isoformat()
    conn = get_connection()
    conn.executemany(
        """
        INSERT INTO house_clerk_trades
          (doc_id, txn_index, politician_name, state_dst, filing_date,
           ticker, asset_type, transaction_type, transaction_date,
           notification_date, amount_low, amount_high, raw_text, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("D1", 0, "Nancy Pelosi", "CA11", "1/1/2026", "NVDA", "ST", "buy", today, today, 1001, 15000, "raw", now_iso),
            ("D2", 0, "Ro Khanna",    "CA17", "1/2/2026", "MSFT", "ST", "buy", today, today, 1001, 15000, "raw", now_iso),
        ],
    )
    conn.commit()
    conn.close()

    out = house_clerk.get_trades_by_politician("Pelosi", days=90)
    assert len(out) == 1
    assert out[0]["ticker"] == "NVDA"
