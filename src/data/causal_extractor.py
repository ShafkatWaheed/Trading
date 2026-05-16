"""Per-stock Claude extraction of commodity exposures (Phase 6).

For each stock, sends `longBusinessSummary` to Claude Haiku with a structured
prompt asking for primary commodity inputs, outputs, substitutes, macro
helpers/hurters, and geographic concentration. Parses the JSON response
and writes `stock_commodity_exposure` rows where the commodity matches our
catalogued list.

Resumable through the `causal_jobs` ledger. Network-gated: tests mock both
the yfinance summary fetch and the Claude call.

CLI:
    python -m src.data.causal_extractor --tier A,B
    python -m src.data.causal_extractor --symbols NVDA,MSFT --force
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone

from src.utils.claude_cli import ask_claude_json
from src.utils.db import get_connection, init_db


# ── prompt construction ─────────────────────────────────────────


EXTRACTION_PROMPT = """\
You are extracting commodity exposures for the publicly-traded company
{symbol} ({name}). Given the business description below, identify which
commodities materially affect this company's costs or revenue.

Return ONLY valid JSON of this exact form:

{{
  "commodity_inputs": [
    {{"commodity": "<lowercase code>", "polarity": -1, "elasticity": 0.0..1.0, "evidence": "<≤15 word note>"}},
    ...
  ],
  "commodity_outputs": [
    {{"commodity": "<lowercase code>", "polarity": 1, "elasticity": 0.0..1.0, "evidence": "<≤15 word note>"}},
    ...
  ]
}}

Use ONLY commodity codes from this catalogue (skip anything not in this list):
{commodity_codes}

Rules:
  * `commodity_inputs` are commodities the company BUYS as feedstock/fuel
    — polarity must be -1 (cost squeeze).
  * `commodity_outputs` are commodities the company SELLS or refines —
    polarity must be +1 (revenue tracker).
  * `elasticity` 0..1 indicates how much commodity price changes pass through.
    0.85 = pure-play producer; 0.30 = mixed/hedged; 0.10 = trivial.
  * Skip commodities with elasticity < 0.10.
  * Return ONLY the JSON. No prose, no markdown fences.

Business description:
---
{summary}
---
"""


def _build_prompt(symbol: str, name: str, summary: str, commodity_codes: list[str]) -> str:
    listing = ", ".join(sorted(commodity_codes))
    truncated = (summary or "")[:3500]
    return EXTRACTION_PROMPT.format(
        symbol=symbol,
        name=name or symbol,
        summary=truncated or "(no business description available)",
        commodity_codes=listing,
    )


# ── job state helpers ──────────────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_job(conn: sqlite3.Connection, symbol: str) -> None:
    conn.execute(
        "INSERT INTO causal_jobs (symbol, status) VALUES (?, 'pending') "
        "ON CONFLICT(symbol) DO NOTHING",
        (symbol,),
    )


def _mark(
    conn: sqlite3.Connection,
    symbol: str,
    *,
    status: str,
    edges_written: int = 0,
    error: str | None = None,
) -> None:
    conn.execute(
        """
        UPDATE causal_jobs SET
            status = ?,
            last_attempt = ?,
            edges_written = ?,
            error = ?
        WHERE symbol = ?
        """,
        (status, _now(), edges_written, error, symbol),
    )


# ── extraction → write ─────────────────────────────────────────


def _write_extracted_exposures(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    parsed: dict,
    valid_codes: set[str],
) -> int:
    """Write stock_commodity_exposure rows from a parsed Claude response.

    UPSERT semantics: existing 'hand'-source rows are NEVER overwritten.
    Only writes for commodities in `valid_codes`. Returns count of rows written.
    """
    written = 0
    for key, role in (("commodity_inputs", "input"), ("commodity_outputs", "output")):
        items = parsed.get(key) or []
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            code = (item.get("commodity") or "").lower().strip()
            if not code or code not in valid_codes:
                continue
            try:
                polarity = float(item.get("polarity", 0))
                elasticity = float(item.get("elasticity", 0))
            except (TypeError, ValueError):
                continue
            if elasticity < 0.10:
                continue
            polarity = max(-1.0, min(1.0, polarity))
            elasticity = max(0.0, min(1.0, elasticity))
            evidence = (item.get("evidence") or "")[:240]
            evidence_tag = f"claude: {evidence}" if evidence else "claude_extraction"

            # Write/upsert. Hand-loaded rows are preserved — the CASE clause
            # in the UPDATE keeps source='hand' if already present.
            conn.execute(
                """
                INSERT INTO stock_commodity_exposure
                    (symbol, commodity_code, role, polarity, elasticity,
                     confidence, evidence, source)
                VALUES (?, ?, ?, ?, ?, 'medium', ?, 'claude')
                ON CONFLICT(symbol, commodity_code, role) DO UPDATE SET
                    polarity = CASE
                        WHEN stock_commodity_exposure.source = 'hand' THEN stock_commodity_exposure.polarity
                        ELSE excluded.polarity END,
                    elasticity = CASE
                        WHEN stock_commodity_exposure.source = 'hand' THEN stock_commodity_exposure.elasticity
                        ELSE excluded.elasticity END,
                    evidence = CASE
                        WHEN stock_commodity_exposure.source = 'hand' THEN stock_commodity_exposure.evidence
                        ELSE excluded.evidence END,
                    source = CASE
                        WHEN stock_commodity_exposure.source = 'hand' THEN stock_commodity_exposure.source
                        ELSE excluded.source END
                """,
                (symbol, code, role, polarity, elasticity, evidence_tag),
            )
            written += 1
    return written


# ── per-stock processing ───────────────────────────────────────


def process_symbol(
    symbol: str,
    *,
    fetch_summary_fn=None,
    extract_fn=None,
    model: str = "haiku",
    conn: sqlite3.Connection | None = None,
) -> dict:
    """Process one symbol end-to-end. Idempotent through `causal_jobs`.

    `fetch_summary_fn(sym) -> (name, summary)` and `extract_fn(prompt, model=...) -> dict | None`
    are dependency-injection hooks used by tests to avoid live network/LLM calls.
    """
    init_db()
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    if fetch_summary_fn is None:
        fetch_summary_fn = _default_fetch_summary
    extract_fn = extract_fn or ask_claude_json

    _ensure_job(conn, symbol)
    _mark(conn, symbol, status="in_progress")
    conn.commit()

    try:
        # 1) Pull business summary
        name, summary = fetch_summary_fn(symbol)
        if not summary:
            _mark(conn, symbol, status="failed", error="no business summary available")
            conn.commit()
            return {"symbol": symbol, "edges_written": 0, "error": "no_summary"}

        # 2) Look up valid commodity codes (so we don't attempt to write rows
        #    for commodities we don't have in our catalogue)
        valid_codes = {
            r["code"]
            for r in conn.execute("SELECT code FROM commodities").fetchall()
        }

        # 3) Build prompt + ask Claude
        prompt = _build_prompt(symbol, name or symbol, summary, list(valid_codes))
        parsed = extract_fn(prompt, model=model)
        if not isinstance(parsed, dict):
            _mark(conn, symbol, status="failed", error="claude returned no parseable JSON")
            conn.commit()
            return {"symbol": symbol, "edges_written": 0, "error": "extraction_failed"}

        # 4) Write
        n = _write_extracted_exposures(
            conn, symbol=symbol, parsed=parsed, valid_codes=valid_codes
        )
        _mark(conn, symbol, status="done", edges_written=n)
        conn.commit()
        return {"symbol": symbol, "edges_written": n, "error": None}
    finally:
        if own_conn:
            conn.close()


def _default_fetch_summary(symbol: str) -> tuple[str | None, str | None]:
    """Pull (name, longBusinessSummary) from yfinance."""
    try:
        import yfinance as yf
        info = yf.Ticker(symbol).info or {}
        return info.get("longName") or info.get("shortName"), info.get("longBusinessSummary")
    except Exception:
        return None, None


# ── batch runner ───────────────────────────────────────────────


def detect_drift_and_reset(conn) -> int:
    """Reset 'done' causal_jobs rows whose claimed exposures have disappeared.

    Same pattern as `peer_jobs.detect_drift_and_reset` — if the ledger says
    `edges_written > 0` but `stock_commodity_exposure` has no claude-sourced
    rows for that symbol, the ledger has drifted and we reset to pending.
    """
    rows = conn.execute(
        "SELECT symbol, edges_written FROM causal_jobs "
        "WHERE status='done' AND edges_written > 0"
    ).fetchall()
    reset = 0
    for r in rows:
        actual = conn.execute(
            "SELECT COUNT(*) FROM stock_commodity_exposure "
            "WHERE symbol=? AND source='claude'",
            (r["symbol"],),
        ).fetchone()[0]
        if actual == 0:
            conn.execute(
                "UPDATE causal_jobs SET status='pending', last_attempt=? WHERE symbol=?",
                (_now(), r["symbol"]),
            )
            reset += 1
    if reset:
        conn.commit()
    return reset


def run_for_tiers(
    tiers: list[str],
    *,
    limit: int | None = None,
    force: bool = False,
    log: bool = True,
) -> dict:
    """Process every symbol at the given tiers; skip those already 'done' unless force."""
    init_db()
    conn = get_connection()
    try:
        # Heal ledger drift before discovering pending work.
        drift_reset = detect_drift_and_reset(conn)
        if log and drift_reset:
            print(f"  [causal_extract] drift detected — reset {drift_reset} stale 'done' rows")

        placeholders = ",".join("?" * len(tiers))
        symbols = [
            r["symbol"] for r in conn.execute(
                f"SELECT symbol FROM stocks_universe WHERE tier IN ({placeholders}) ORDER BY symbol",
                tiers,
            ).fetchall()
        ]
        if not force:
            done = {
                r["symbol"] for r in conn.execute(
                    "SELECT symbol FROM causal_jobs WHERE status='done'"
                ).fetchall()
            }
            symbols = [s for s in symbols if s not in done]
        if limit is not None:
            symbols = symbols[:limit]
    finally:
        conn.close()

    succeeded = 0
    failed = 0
    edges = 0
    for sym in symbols:
        if log:
            print(f"  [causal_extract] {sym}…")
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
        "drift_reset": drift_reset,
    }


# ── CLI ────────────────────────────────────────────────────────


def _main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tier", default="A,B", help="Comma-separated tiers (default: A,B)")
    p.add_argument("--symbols", help="Comma-separated; overrides --tier")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--force", action="store_true",
                   help="Re-process even if marked 'done' in causal_jobs")
    args = p.parse_args()

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
        for sym in symbols:
            print(f"  [causal_extract] {sym}…")
            out = process_symbol(sym)
            print(f"    edges={out['edges_written']} error={out.get('error')}")
        return 0

    tiers = [t.strip().upper() for t in args.tier.split(",") if t.strip()]
    out = run_for_tiers(tiers, limit=args.limit, force=args.force)
    print()
    for k, v in out.items():
        print(f"  {k:20s}: {v}")
    return 0 if out["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(_main())
