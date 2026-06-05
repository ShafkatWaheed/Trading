"""House Clerk PTR (Periodic Transaction Report) ingest pipeline.

Replaces Capitol Trades scraping (blocked by Vercel checkpoint).
Source: https://disclosures-clerk.house.gov/public_disc/

Pipeline:
  1. Download {year}FD.zip -> parse XML -> list of PTR DocIDs
  2. For each unparsed DocID: fetch PDF -> pdfplumber extract -> regex
  3. Store rows in house_clerk_trades; mark status in house_clerk_index
  4. Per-query: SELECT from cached table (fast)

Refresh cadence: nightly (or on-demand via ?force=true). PDFs don't change
once filed, so old entries are forever-cached.

Per CLAUDE.md: data layer. May call external APIs, read/write trading.db.
Returns empty lists on error -- no fake fallbacks.

Note: House-only. The Senate side (efdsearch.senate.gov) is not covered
here -- they publish a separate disclosure feed that would need its own
ingester. Senate-only signal is therefore empty for now.
"""
from __future__ import annotations

import io
import re
import zipfile
from datetime import datetime, timedelta, timezone

import httpx
import pdfplumber
import xml.etree.ElementTree as ET

from src.utils.db import get_connection, init_db, log_api_call


_INDEX_URL = "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{year}FD.zip"
_PDF_URL = "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{year}/{doc_id}.pdf"

# Polite UA -- House Clerk site is government, no scraping block, but identify
# ourselves anyway.
_HEADERS = {
    "User-Agent": "TradingAnalysis/1.0 (research; admin@tradinganalysis.local)"
}


# Transaction line shape (verified against PTR PDFs):
#   ... (TICKER) [ASSET_TYPE] S/P/E (partial|full)? MM/DD/YYYY MM/DD/YYYY $low - $high
_TXN_RE = re.compile(
    r"\(([A-Z][A-Z0-9.\-/]{0,9})\)\s*\[(\w{1,4})\]\s*([SPE])(?:\s*\(partial\)|\s*\(full\))?\s+"
    r"(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})\s+"
    r"\$([\d,]+)\s*[-–]\s*\$([\d,]+)",
    re.IGNORECASE,
)


def _norm_date(mdY: str) -> str:
    """'03/16/2026' -> '2026-03-16'."""
    try:
        return datetime.strptime(mdY, "%m/%d/%Y").date().isoformat()
    except Exception:
        return mdY


def _norm_txn(code: str) -> str:
    code = code.upper()
    return {"S": "sell", "P": "buy", "E": "exchange"}.get(code, "unknown")


def _parse_amount(s: str) -> int:
    """'$1,001' -> 1001."""
    return int(s.replace(",", "").replace("$", "").strip())


def fetch_index_for_year(year: int, *, http_get=None) -> list[dict]:
    """Download and parse {year}FD.zip -> list of PTR records (FilingType='P').

    `http_get` is dependency-injected for tests; defaults to httpx.get.
    Returns empty list on any error (logged via log_api_call).
    """
    init_db()
    fetch = http_get if http_get is not None else (
        lambda url: httpx.get(url, headers=_HEADERS, timeout=60.0, follow_redirects=True)
    )
    url = _INDEX_URL.format(year=year)
    try:
        r = fetch(url)
        r.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            xml_name = next(n for n in z.namelist() if n.lower().endswith(".xml"))
            xml = z.read(xml_name).decode("utf-8", errors="replace")
    except Exception as exc:
        log_api_call("house_clerk", url, "error", error=str(exc))
        return []

    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        log_api_call("house_clerk", url, "error", error=f"xml parse: {exc}")
        return []

    ptrs = []
    for m in root:
        if (m.findtext("FilingType") or "").strip() != "P":
            continue
        doc_id = (m.findtext("DocID") or "").strip()
        if not doc_id:
            continue
        name = " ".join(filter(None, [
            (m.findtext("First") or "").strip(),
            (m.findtext("Last") or "").strip(),
            (m.findtext("Suffix") or "").strip(),
        ])).strip()
        ptrs.append({
            "doc_id": doc_id,
            "year": str(year),
            "filing_type": "P",
            "politician_name": name,
            "state_dst": (m.findtext("StateDst") or "").strip(),
            "filing_date": (m.findtext("FilingDate") or "").strip(),
        })
    log_api_call("house_clerk", url, "ok", error=f"{len(ptrs)} PTRs")
    return ptrs


def parse_ptr_pdf(content: bytes) -> list[dict]:
    """Extract transactions from a single PTR PDF.

    Returns list of dicts with raw fields. Normalization happens at insert.
    Returns empty list on PDF read failure (scanned/non-text/corrupt).
    """
    out: list[dict] = []
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            full_text = ""
            for p in pdf.pages:
                full_text += "\n" + (p.extract_text() or "")
        # Collapse whitespace to handle multi-line splits (ticker on one line,
        # amount on the next).
        collapsed = re.sub(r"\s+", " ", full_text)
        for m in _TXN_RE.finditer(collapsed):
            ticker, asset_type, code, t_date, n_date, lo, hi = m.groups()
            out.append({
                "ticker": ticker.upper(),
                "asset_type": asset_type.upper(),
                "transaction_code": code.upper(),
                "transaction_date_raw": t_date,
                "notification_date_raw": n_date,
                "amount_low": _parse_amount(lo),
                "amount_high": _parse_amount(hi),
                "raw_text": m.group(0)[:500],
            })
    except Exception:
        # PDF may be scanned/non-text -- yield nothing, caller logs.
        pass
    return out


def _fetch_and_store_one_ptr(meta: dict, *, http_get=None) -> int:
    """Fetch + parse + store ONE PTR. Returns transactions stored.

    `http_get` is dependency-injected for tests.
    """
    init_db()
    fetch = http_get if http_get is not None else (
        lambda url: httpx.get(url, headers=_HEADERS, timeout=30.0, follow_redirects=True)
    )
    doc_id = meta["doc_id"]
    year = meta["year"]
    url = _PDF_URL.format(year=year, doc_id=doc_id)
    now_iso = datetime.now(tz=timezone.utc).isoformat()

    conn = get_connection()
    try:
        # Upsert index row
        conn.execute(
            "INSERT INTO house_clerk_index (doc_id, year, filing_type, last_attempted) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(doc_id) DO UPDATE SET last_attempted = ?",
            (doc_id, year, "P", now_iso, now_iso),
        )
        conn.commit()

        try:
            r = fetch(url)
            r.raise_for_status()
        except Exception as exc:
            conn.execute(
                "UPDATE house_clerk_index SET status = ?, error = ? WHERE doc_id = ?",
                ("http_error", str(exc)[:200], doc_id),
            )
            conn.commit()
            log_api_call("house_clerk", url, "error", error=str(exc))
            return 0

        txns = parse_ptr_pdf(r.content)
        if not txns:
            conn.execute(
                "UPDATE house_clerk_index SET status = ?, fetched_at = ? WHERE doc_id = ?",
                ("empty", now_iso, doc_id),
            )
            conn.commit()
            return 0

        # Wipe + reinsert this doc's rows (in case of re-parse).
        conn.execute("DELETE FROM house_clerk_trades WHERE doc_id = ?", (doc_id,))
        for i, t in enumerate(txns):
            conn.execute(
                """
                INSERT INTO house_clerk_trades
                  (doc_id, txn_index, politician_name, state_dst, filing_date,
                   ticker, asset_type, transaction_type, transaction_date,
                   notification_date, amount_low, amount_high, raw_text, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doc_id, i,
                    meta["politician_name"], meta["state_dst"], meta["filing_date"],
                    t["ticker"], t["asset_type"], _norm_txn(t["transaction_code"]),
                    _norm_date(t["transaction_date_raw"]),
                    _norm_date(t["notification_date_raw"]),
                    t["amount_low"], t["amount_high"],
                    t["raw_text"], now_iso,
                ),
            )
        conn.execute(
            "UPDATE house_clerk_index SET status = ?, fetched_at = ? WHERE doc_id = ?",
            ("parsed", now_iso, doc_id),
        )
        conn.commit()
        log_api_call("house_clerk", url, "ok", error=f"{len(txns)} txns")
        return len(txns)
    finally:
        conn.close()


def refresh_recent(
    *,
    year: int | None = None,
    max_docs: int = 100,
    http_get_index=None,
    http_get_pdf=None,
) -> dict:
    """Refresh recent PTRs.

    Pulls the index for `year` (defaults to current), finds DocIDs not yet
    parsed (status != 'parsed' or not seen), and processes up to `max_docs`
    of them.

    Returns counts: {found, attempted, parsed, errored, empty}.
    """
    year = year or datetime.now(tz=timezone.utc).year
    init_db()

    index = fetch_index_for_year(year, http_get=http_get_index)
    if not index:
        return {"found": 0, "attempted": 0, "parsed": 0, "errored": 0, "empty": 0}

    conn = get_connection()
    parsed_ids = {r[0] for r in conn.execute(
        "SELECT doc_id FROM house_clerk_index WHERE status = 'parsed'"
    )}
    conn.close()

    todo = [m for m in index if m["doc_id"] not in parsed_ids][:max_docs]
    counts = {
        "found": len(index),
        "attempted": len(todo),
        "parsed": 0,
        "errored": 0,
        "empty": 0,
    }
    for meta in todo:
        n = _fetch_and_store_one_ptr(meta, http_get=http_get_pdf)
        if n > 0:
            counts["parsed"] += 1
        else:
            conn = get_connection()
            row = conn.execute(
                "SELECT status FROM house_clerk_index WHERE doc_id = ?",
                (meta["doc_id"],),
            ).fetchone()
            conn.close()
            if row and row["status"] == "empty":
                counts["empty"] += 1
            else:
                counts["errored"] += 1
    return counts


def get_top_traded_stocks(days: int = 90, *, limit: int = 20) -> list[dict]:
    """Top tickers by transaction count over the last `days`."""
    init_db()
    cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=days)).date().isoformat()
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT ticker, COUNT(*) AS trade_count
            FROM house_clerk_trades
            WHERE ticker != '' AND transaction_date >= ?
            GROUP BY ticker
            ORDER BY trade_count DESC
            LIMIT ?
            """,
            (cutoff, limit),
        ).fetchall()
    finally:
        conn.close()
    return [{"symbol": r["ticker"], "trade_count": r["trade_count"]} for r in rows]


def get_trades_by_symbol(symbol: str, days: int = 180) -> list[dict]:
    """All transactions for one ticker over the lookback window."""
    if not symbol:
        return []
    init_db()
    sym = symbol.upper().strip()
    cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=days)).date().isoformat()
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT doc_id, politician_name, state_dst, filing_date, ticker, asset_type,
                   transaction_type, transaction_date, notification_date,
                   amount_low, amount_high, raw_text
            FROM house_clerk_trades
            WHERE ticker = ? AND transaction_date >= ?
            ORDER BY transaction_date DESC
            """,
            (sym, cutoff),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def get_trades_by_politician(name: str, days: int = 180) -> list[dict]:
    """All transactions for one politician over the lookback window."""
    if not name:
        return []
    init_db()
    cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=days)).date().isoformat()
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT doc_id, politician_name, state_dst, filing_date, ticker, asset_type,
                   transaction_type, transaction_date, notification_date,
                   amount_low, amount_high, raw_text
            FROM house_clerk_trades
            WHERE politician_name LIKE ? AND transaction_date >= ?
            ORDER BY transaction_date DESC
            """,
            (f"%{name.strip()}%", cutoff),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]
