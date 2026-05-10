"""SEC 10-K Item 1A extractor — mines named suppliers/customers via Claude.

For each Tier A stock, this module:
    1. Resolves CIK via the existing SECEdgarProvider (cache-friendly)
    2. Locates the latest 10-K filing
    3. Downloads Item 1A (Risk Factors) — typically 10-25 pages of dense
       supplier/customer disclosures
    4. Sends a truncated slice (~6000 chars) to Claude Haiku with an
       extraction prompt
    5. Parses the JSON response and writes `stock_relations` rows where the
       extracted entity matches a symbol in `stocks_universe`
    6. Marks the job 'done' or 'failed' in `tenk_jobs` for resumability

Network-gated: tests mock both the EDGAR fetch and the Claude call.

CLI:
    python -m src.data.sec_10k_extractor --tier A
    python -m src.data.sec_10k_extractor --symbols NVDA,MSFT --force
    python -m src.data.sec_10k_extractor --status pending --limit 10
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone

import httpx

from src.utils.claude_cli import ask_claude_json
from src.utils.db import get_connection, init_db


# ── prompt construction ──────────────────────────────────────────


EXTRACTION_PROMPT = """\
You are extracting business relationships from a public company's 10-K Risk
Factors disclosure. The text below is from {symbol}'s 10-K Item 1A.

Identify, with HIGH confidence only:
  * SUPPLIERS — companies {symbol} depends on for inputs/services
  * CUSTOMERS — companies that contribute >10% of {symbol}'s revenue
  * JOINT VENTURES — formal collaboration partners

Use ONLY publicly-traded ticker symbols you are CONFIDENT about. Skip vague
references like "our largest customer" without a name.

Return ONLY valid JSON of the form:

{{
  "suppliers": [{{"symbol": "TSM", "name": "Taiwan Semiconductor", "evidence": "<10-word citation>"}}],
  "customers": [{{"symbol": "MSFT", "name": "Microsoft", "evidence": "<10-word citation>"}}],
  "joint_ventures": [{{"symbol": "INTC", "name": "Intel", "evidence": "<10-word citation>"}}]
}}

Text from {symbol}'s 10-K Item 1A:
---
{text}
---
"""


def _build_extraction_prompt(symbol: str, item_1a_text: str, max_chars: int = 6000) -> str:
    """Truncate to max_chars to fit Claude Haiku's context window comfortably."""
    truncated = item_1a_text[:max_chars]
    if len(item_1a_text) > max_chars:
        truncated += "\n\n[... text truncated for length ...]"
    return EXTRACTION_PROMPT.format(symbol=symbol, text=truncated)


# ── 10-K fetching (network) ──────────────────────────────────────


SEC_HEADERS = {
    "User-Agent": "Trading Prototype research@example.com",
    "Accept-Encoding": "gzip, deflate",
}

ITEM_1A_PATTERNS = [
    re.compile(r"item\s*1a[\s.\-:]*risk\s*factors", re.IGNORECASE),
]
ITEM_1B_PATTERNS = [
    re.compile(r"item\s*1b[\s.\-:]", re.IGNORECASE),
    re.compile(r"item\s*2[\s.\-:]", re.IGNORECASE),
]


def _strip_html(html: str) -> str:
    """Crude text extractor — fast, dependency-free, good enough for Claude input."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&[a-z]+;", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_item_1a(filing_text: str) -> str | None:
    """Slice Item 1A out of a 10-K filing's plain-text content."""
    text = filing_text.replace("\xa0", " ")
    start_match = None
    for pat in ITEM_1A_PATTERNS:
        start_match = pat.search(text)
        if start_match:
            break
    if start_match is None:
        return None
    start = start_match.end()

    # Find the next section header (Item 1B or Item 2)
    end_match = None
    for pat in ITEM_1B_PATTERNS:
        m = pat.search(text, start)
        if m and (end_match is None or m.start() < end_match.start()):
            end_match = m
    end = end_match.start() if end_match else min(len(text), start + 80_000)
    return text[start:end].strip() or None


def fetch_latest_10k_text(symbol: str) -> tuple[str | None, str | None]:
    """Returns (item_1a_text, filing_url). Either may be None on failure.

    Uses the existing SECEdgarProvider for CIK lookup + httpx for the filing
    download. Strips HTML and isolates Item 1A.
    """
    from src.data.sec_edgar import SECEdgarProvider

    provider = SECEdgarProvider()
    try:
        cik = provider._get_cik(symbol)
    except Exception:
        return None, None
    if not cik:
        return None, None

    cik_padded = cik.zfill(10)
    submissions_url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
    try:
        resp = httpx.get(submissions_url, headers=SEC_HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None, None

    # Find the latest 10-K from recent filings
    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])

    filing_url = None
    for i, form in enumerate(forms):
        if form == "10-K":
            acc = accessions[i].replace("-", "")
            doc = primary_docs[i]
            filing_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{doc}"
            break

    if not filing_url:
        return None, None

    try:
        resp = httpx.get(filing_url, headers=SEC_HEADERS, timeout=60)
        resp.raise_for_status()
        plain = _strip_html(resp.text)
    except Exception:
        return None, filing_url

    item_1a = extract_item_1a(plain)
    return item_1a, filing_url


# ── job state helpers ────────────────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_job(conn: sqlite3.Connection, symbol: str) -> None:
    conn.execute(
        "INSERT INTO tenk_jobs (symbol, status) VALUES (?, 'pending') "
        "ON CONFLICT(symbol) DO NOTHING",
        (symbol,),
    )


def _mark(
    conn: sqlite3.Connection,
    symbol: str,
    *,
    status: str,
    filing_url: str | None = None,
    edges_written: int = 0,
    error: str | None = None,
) -> None:
    conn.execute(
        """
        UPDATE tenk_jobs SET
            status = ?,
            last_attempt = ?,
            filing_url = COALESCE(?, filing_url),
            edges_written = ?,
            error = ?
        WHERE symbol = ?
        """,
        (status, _now(), filing_url, edges_written, error, symbol),
    )


# ── edge writing ────────────────────────────────────────────────


def _write_relations_from_extraction(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    parsed: dict,
    valid_universe: set[str],
) -> int:
    """Write stock_relations rows from a parsed extraction.

    Hand-loaded edges (with `evidence` starting 'seed:hand') are NEVER
    overwritten. Where claude already wrote a 10k_mined edge, we update.
    """
    written = 0
    relation_groups = (
        ("suppliers", "supplier"),
        ("customers", "customer"),
        ("joint_ventures", "complement"),  # JVs map to complement for now
    )

    for key, relation_type in relation_groups:
        items = parsed.get(key) or []
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            target = (item.get("symbol") or "").upper().strip()
            if not target or target == symbol or target not in valid_universe:
                continue
            evidence_text = (item.get("evidence") or "")[:240]

            conn.execute(
                """
                INSERT INTO stock_relations
                    (from_symbol, to_symbol, relation_type, strength, polarity, evidence)
                VALUES (?, ?, ?, 0.55, 1.0, ?)
                ON CONFLICT(from_symbol, to_symbol, relation_type) DO UPDATE SET
                    strength = MAX(stock_relations.strength, excluded.strength),
                    -- Don't overwrite the hand-loaded spine
                    evidence = CASE
                        WHEN stock_relations.evidence LIKE 'seed:hand%' THEN stock_relations.evidence
                        ELSE excluded.evidence END
                """,
                (symbol, target, relation_type, f"10k_mined: {evidence_text}"),
            )
            written += 1
    return written


# ── per-stock processing ────────────────────────────────────────


def process_symbol(
    symbol: str,
    *,
    fetch_fn=None,
    extract_fn=None,
    model: str = "haiku",
    conn: sqlite3.Connection | None = None,
) -> dict:
    """Process one symbol end-to-end. Idempotent through the `tenk_jobs` ledger.

    `fetch_fn` and `extract_fn` are injection points for tests:
        fetch_fn(symbol) -> (item_1a_text, filing_url)
        extract_fn(prompt, model='haiku') -> dict | None  (parsed JSON)
    Defaults call the live SEC EDGAR + Claude CLI.
    """
    init_db()
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    fetch_fn = fetch_fn or fetch_latest_10k_text
    extract_fn = extract_fn or ask_claude_json

    _ensure_job(conn, symbol)
    _mark(conn, symbol, status="in_progress")
    conn.commit()

    try:
        # 1. Fetch
        item_1a, filing_url = fetch_fn(symbol)
        if not item_1a:
            _mark(conn, symbol, status="failed",
                  filing_url=filing_url,
                  error="Item 1A could not be located")
            conn.commit()
            return {"symbol": symbol, "edges_written": 0, "error": "no_item_1a"}

        # 2. Extract
        prompt = _build_extraction_prompt(symbol, item_1a)
        parsed = extract_fn(prompt, model=model)
        if not isinstance(parsed, dict):
            _mark(conn, symbol, status="failed",
                  filing_url=filing_url,
                  error="claude returned no parseable JSON")
            conn.commit()
            return {"symbol": symbol, "edges_written": 0, "error": "extraction_failed"}

        # 3. Write
        universe = {
            r["symbol"]
            for r in conn.execute("SELECT symbol FROM stocks_universe").fetchall()
        }
        n = _write_relations_from_extraction(
            conn, symbol=symbol, parsed=parsed, valid_universe=universe,
        )
        _mark(conn, symbol, status="done", filing_url=filing_url, edges_written=n)
        conn.commit()
        return {"symbol": symbol, "edges_written": n, "error": None}
    finally:
        if own_conn:
            conn.close()


# ── batch runner ────────────────────────────────────────────────


def run_for_tier(
    tier: str = "A",
    *,
    limit: int | None = None,
    force: bool = False,
    log: bool = True,
) -> dict:
    """Process every symbol at the given tier; skip those already 'done' unless force."""
    init_db()
    conn = get_connection()
    try:
        symbols = [
            r["symbol"] for r in conn.execute(
                "SELECT symbol FROM stocks_universe WHERE tier = ? ORDER BY symbol",
                (tier,),
            ).fetchall()
        ]
        if not force:
            done_set = {
                r["symbol"] for r in conn.execute(
                    "SELECT symbol FROM tenk_jobs WHERE status = 'done'"
                ).fetchall()
            }
            symbols = [s for s in symbols if s not in done_set]
        if limit is not None:
            symbols = symbols[:limit]
    finally:
        conn.close()

    succeeded = 0
    failed = 0
    edges = 0
    for sym in symbols:
        if log:
            print(f"  [10k_extract] {sym}…")
        out = process_symbol(sym)
        if out.get("error"):
            failed += 1
        else:
            succeeded += 1
            edges += out["edges_written"]

    return {
        "processed": len(symbols),
        "succeeded": succeeded,
        "failed": failed,
        "edges_written": edges,
    }


# ── CLI ─────────────────────────────────────────────────────────


def _main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tier", default="A", help="Tier to process (default: A)")
    p.add_argument("--symbols", help="Comma-separated; overrides --tier")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--force", action="store_true",
                   help="Re-process even if marked 'done' in tenk_jobs")
    args = p.parse_args()

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
        for sym in symbols:
            print(f"  [10k_extract] {sym}…")
            out = process_symbol(sym)
            print(f"    edges={out['edges_written']} error={out.get('error')}")
        return 0

    out = run_for_tier(tier=args.tier, limit=args.limit, force=args.force)
    print()
    for k, v in out.items():
        print(f"  {k:20s}: {v}")
    return 0 if out["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(_main())
