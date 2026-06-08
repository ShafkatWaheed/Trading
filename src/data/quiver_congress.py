"""Quiver Quantitative congressional-trading ingest — House + Senate.

Single source of truth for STOCK Act disclosures. Replaces the old per-chamber
scrapers (`house_clerk`, `senate_efd`): the House Clerk PDFs and the Senate eFD
portal (Akamai Bot Manager) plus Capitol Trades' API (CloudFront) were all
unreliable or IP-blocked from our host. Quiver exposes both chambers via one
clean authenticated JSON API, with chamber AND party (which the disclosure
feeds never carried).

Data path: Quiver `live/congresstrading` -> `congress_trades` table. The
`src.data.congress` adapter reads from here via the reader functions below.

Per CLAUDE.md: data layer. Calls an external API, reads/writes trading.db.
Returns empty / raises on failure -- no fake fallbacks. Point-in-time safe:
ReportDate is the "available at" (filing) timestamp; TransactionDate is the
trade date. The 45-day STOCK Act disclosure delay still applies downstream.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

import httpx

from src.utils.config import QUIVER_API_TOKEN
from src.utils.db import cache_get, cache_set, get_connection, init_db, log_api_call
from src.utils.retry import with_retry

_BASE = "https://api.quiverquant.com/beta"
_LIVE_CONGRESS = f"{_BASE}/live/congresstrading"
_TIMEOUT = 40
_CACHE_TTL_MIN = 360  # 6h — the live feed updates a few times a day at most

_AMOUNT_RE = re.compile(r"\$([\d,]+)\s*[-–]\s*\$([\d,]+)")
_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")

_PARTY_MAP = {"D": "Democrat", "R": "Republican", "I": "Independent"}


def _enabled() -> bool:
    return bool(QUIVER_API_TOKEN)


# ── pure helpers (unit-tested) ───────────────────────────────────────────


def _norm_txn(label: str) -> str:
    """Quiver transaction label -> buy | sell | exchange | unknown."""
    s = (label or "").strip().lower()
    if s.startswith("purchase"):
        return "buy"
    if s.startswith("sale"):
        return "sell"
    if s.startswith("exchange"):
        return "exchange"
    return "unknown"


def _norm_chamber(house_field: str) -> str:
    """Quiver 'House' field -> 'House' | 'Senate'."""
    return "Senate" if (house_field or "").strip().lower() == "senate" else "House"


def _norm_party(p: str) -> str:
    """Quiver party code ('D'/'R'/'I') -> full name; 'Unknown' otherwise."""
    return _PARTY_MAP.get((p or "").strip().upper(), "Unknown")


def _parse_amount_range(s: str) -> tuple[int, int]:
    """'$100,001 - $250,000' -> (100001, 250000). (0, 0) when no range found."""
    m = _AMOUNT_RE.search(s or "")
    if not m:
        return (0, 0)
    return (int(m.group(1).replace(",", "")), int(m.group(2).replace(",", "")))


def _norm_date(s: str) -> str:
    """Quiver dates are ISO 'YYYY-MM-DD'; pass through, tolerate 'M/D/Y'."""
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return s


def _ticker_ok(t: str) -> bool:
    return bool(t) and _TICKER_RE.match(t.upper()) is not None


def _filing_uuid(chamber: str, bioguide: str, report_date: str, name: str) -> str:
    """Stable per-filing id (one filer's report = one PTR, many txns).

    Quiver has no filing id, so we synthesize a deterministic one keyed on
    chamber + filer + report date so re-runs upsert instead of duplicating.
    """
    key = (bioguide or "").strip() or (name or "unknown").strip().replace(" ", "_")
    return f"quiver:{chamber[:3].lower()}:{key}:{report_date or 'na'}"


def normalize(records: list[dict]) -> dict[str, list[dict]]:
    """Group Quiver records (both chambers) into {filing_uuid: [trade_dict, ...]}.

    Rows without a real ticker are dropped. Each trade_dict matches the
    congress_trades columns (filing_uuid/txn_index added at write time).
    """
    by_filing: dict[str, list[dict]] = {}
    for r in records:
        ticker = (r.get("Ticker") or "").upper().strip()
        if not _ticker_ok(ticker):
            continue
        chamber = _norm_chamber(r.get("House") or "")
        name = (r.get("Representative") or "").strip()
        bioguide = (r.get("BioGuideID") or "").strip()
        report_date = _norm_date(r.get("ReportDate") or "")
        txn_date = _norm_date(r.get("TransactionDate") or "")
        lo, hi = _parse_amount_range(r.get("Range") or "")
        uuid = _filing_uuid(chamber, bioguide, report_date, name)
        by_filing.setdefault(uuid, []).append({
            "chamber": chamber,
            "politician_name": name or "Unknown",
            "party": _norm_party(r.get("Party") or ""),
            "state": "",  # not carried in Quiver's live congress feed
            "bioguide_id": bioguide,
            "ticker": ticker,
            "asset_type": (r.get("TickerType") or "").strip(),
            "transaction_type": _norm_txn(r.get("Transaction") or ""),
            "transaction_date": txn_date,
            "filing_date": report_date,
            "amount_low": lo,
            "amount_high": hi,
            "raw_text": json.dumps({
                "range": r.get("Range"),
                "transaction": r.get("Transaction"),
                "description": r.get("Description"),
            })[:500],
        })
    return by_filing


# ── fetch ────────────────────────────────────────────────────────────────


@with_retry(max_retries=3, source="quiver")
def _http_get(url: str) -> list:
    headers = {
        "Authorization": f"Token {QUIVER_API_TOKEN}",
        "Accept": "application/json",
    }
    resp = httpx.get(url, headers=headers, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def fetch_congress(*, use_cache: bool = True) -> list[dict]:
    """Most-recent congressional trades (House + Senate) from Quiver.

    Returns raw Quiver records. [] when the token is unset or on error (logged).
    """
    if not _enabled():
        log_api_call("quiver", "live/congresstrading", "error", "QUIVER_API_TOKEN unset")
        return []
    cache_key = "quiver:congress:live"
    if use_cache:
        cached = cache_get(cache_key)
        if cached is not None:
            return cached.get("rows", [])
    try:
        rows = _http_get(_LIVE_CONGRESS)
        log_api_call("quiver", "live/congresstrading", "success", f"{len(rows)} rows")
        cache_set(cache_key, {"rows": rows}, ttl_minutes=_CACHE_TTL_MIN)
        return rows
    except Exception as exc:
        log_api_call("quiver", "live/congresstrading", "error", str(exc))
        return []


# ── ingest ─────────────────────────────────────────────────────────────────


def refresh(*, fetch_fn=None) -> dict:
    """Populate `congress_trades` (House + Senate) from Quiver's feed.

    Idempotent: each filing (chamber + filer + report date) is rewritten in
    full, so re-running never duplicates. `fetch_fn` is dependency-injected for
    tests; the default hits the live API.
    Returns {filings, trades, house, senate, politicians}.
    """
    init_db()
    records = fetch_fn() if fetch_fn is not None else fetch_congress()
    grouped = normalize(records or [])
    now_iso = datetime.now(tz=timezone.utc).isoformat()

    counts = {"filings": 0, "trades": 0, "house": 0, "senate": 0, "politicians": 0}
    politicians: set[str] = set()
    conn = get_connection()
    try:
        for uuid, trades in grouped.items():
            if not trades:
                continue
            conn.execute("DELETE FROM congress_trades WHERE filing_uuid=?", (uuid,))
            for i, t in enumerate(trades):
                conn.execute(
                    """INSERT INTO congress_trades
                       (filing_uuid, txn_index, chamber, politician_name, party,
                        state, bioguide_id, ticker, asset_type, transaction_type,
                        transaction_date, filing_date, amount_low, amount_high,
                        raw_text, source, fetched_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (uuid, i, t["chamber"], t["politician_name"], t["party"],
                     t["state"], t["bioguide_id"], t["ticker"], t["asset_type"],
                     t["transaction_type"], t["transaction_date"], t["filing_date"],
                     t["amount_low"], t["amount_high"], t["raw_text"], "quiver", now_iso),
                )
            counts["filings"] += 1
            counts["trades"] += len(trades)
            counts["house" if trades[0]["chamber"] == "House" else "senate"] += len(trades)
            politicians.add(trades[0]["politician_name"])
        conn.commit()
    finally:
        conn.close()

    counts["politicians"] = len(politicians)
    log_api_call("quiver", "refresh", "success",
                 f"{counts['filings']} filings, {counts['trades']} trades "
                 f"(H={counts['house']} S={counts['senate']}), "
                 f"{counts['politicians']} members")
    return counts


# ── readers (consumed by src.data.congress) ─────────────────────────────────

_TRADE_COLS = (
    "filing_uuid, txn_index, chamber, politician_name, party, state, "
    "bioguide_id, ticker, asset_type, transaction_type, transaction_date, "
    "filing_date, amount_low, amount_high, raw_text"
)


def _cutoff(days: int) -> str:
    return (datetime.now(tz=timezone.utc) - timedelta(days=days)).date().isoformat()


def get_trades_by_symbol(symbol: str, days: int = 180) -> list[dict]:
    """All congressional transactions for one ticker over the lookback window."""
    if not symbol:
        return []
    init_db()
    conn = get_connection()
    try:
        rows = conn.execute(
            f"SELECT {_TRADE_COLS} FROM congress_trades "
            "WHERE ticker = ? AND transaction_date >= ? "
            "ORDER BY transaction_date DESC",
            (symbol.upper().strip(), _cutoff(days)),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def get_trades_by_politician(name: str, days: int = 180) -> list[dict]:
    """All congressional transactions for one member over the lookback window."""
    if not name:
        return []
    init_db()
    conn = get_connection()
    try:
        rows = conn.execute(
            f"SELECT {_TRADE_COLS} FROM congress_trades "
            "WHERE politician_name LIKE ? AND transaction_date >= ? "
            "ORDER BY transaction_date DESC",
            (f"%{name.strip()}%", _cutoff(days)),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def get_top_traded_stocks(days: int = 90, *, limit: int = 20) -> list[dict]:
    """Top tickers by transaction count over the last `days` (both chambers)."""
    init_db()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT ticker, COUNT(*) AS trade_count FROM congress_trades "
            "WHERE ticker != '' AND transaction_date >= ? "
            "GROUP BY ticker ORDER BY trade_count DESC LIMIT ?",
            (_cutoff(days), limit),
        ).fetchall()
    finally:
        conn.close()
    return [{"symbol": r["ticker"], "trade_count": r["trade_count"]} for r in rows]
