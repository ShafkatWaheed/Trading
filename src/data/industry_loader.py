"""yfinance industry/sector loader — populate stock_industry from yfinance.

Pulls each symbol's `info.industry`, `info.sector`, `info.marketCap`, and
`info.longBusinessSummary` and writes the mapping to `stock_industry` plus
the `industries` table (auto-creating new industry rows if yfinance returns
an industry we haven't catalogued).

Design notes:
  * Network-gated: `pull_industry()` makes a real call to yfinance; tests
    monkeypatch the `yfinance` module at the test boundary.
  * Resumable: by default skips symbols that already have at least one
    `stock_industry` row (`force=True` re-pulls all).
  * Polite: 100ms sleep between calls; aggregator calls log every 100 symbols.
  * Single-threaded by default — yfinance internals aren't thread-safe in
    older versions and Yahoo has informal anti-flooding behaviour.

CLI:
    python -m src.data.industry_loader [--symbols AAPL,MSFT,...] [--force]
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from typing import Iterable

from src.utils.db import get_connection, init_db


# ── single-symbol fetch ────────────────────────────────────────────


def pull_industry(symbol: str) -> dict | None:
    """Fetch industry + sector from yfinance for a single symbol.

    Returns None on any error so callers can continue the batch.
    """
    try:
        import yfinance as yf
        info = yf.Ticker(symbol).info or {}
    except Exception:
        return None

    return {
        "symbol": symbol,
        "industry": (info.get("industry") or "").strip(),
        "sector": (info.get("sector") or "").strip(),
        "market_cap": info.get("marketCap"),
        "business_summary": (info.get("longBusinessSummary") or "").strip(),
    }


# ── batched fetch + DB upsert ──────────────────────────────────────


def apply_yfinance_industries(
    symbols: Iterable[str] | None = None,
    *,
    force: bool = False,
    sleep_seconds: float = 0.1,
    progress_every: int = 100,
    log: bool = True,
    conn: sqlite3.Connection | None = None,
) -> dict[str, int]:
    """Pull industries from yfinance and write into stock_industry + industries.

    `symbols=None` means "every row in stocks_universe". `force=False` skips
    symbols that already have a stock_industry row.
    """
    init_db()
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    if symbols is None:
        rows = conn.execute("SELECT symbol FROM stocks_universe ORDER BY symbol").fetchall()
        symbols = [r["symbol"] for r in rows]

    if not force:
        existing = {
            r["symbol"]
            for r in conn.execute(
                "SELECT DISTINCT symbol FROM stock_industry"
            ).fetchall()
        }
        symbols = [s for s in symbols if s not in existing]

    n_total = len(list(symbols))
    rows_written = 0
    industries_added = 0
    fetch_failures = 0

    try:
        for i, symbol in enumerate(symbols, start=1):
            info = pull_industry(symbol)
            if info is None:
                fetch_failures += 1
            elif info["industry"]:
                # 1) ensure industry row exists
                pre = conn.execute(
                    "SELECT 1 FROM industries WHERE code=?", (info["industry"],)
                ).fetchone()
                if pre is None:
                    industries_added += 1
                conn.execute(
                    """
                    INSERT INTO industries (code, sector)
                    VALUES (?, ?)
                    ON CONFLICT(code) DO UPDATE SET
                        sector = COALESCE(NULLIF(excluded.sector, ''), industries.sector)
                    """,
                    (info["industry"], info["sector"] or "Unknown"),
                )

                # 2) primary stock_industry mapping (single-tag, weight 1.0)
                conn.execute(
                    """
                    INSERT INTO stock_industry
                        (symbol, industry_code, weight, is_primary, source)
                    VALUES (?, ?, 1.0, 1, 'yfinance')
                    ON CONFLICT(symbol, industry_code) DO UPDATE SET
                        weight = 1.0,
                        is_primary = 1,
                        source = 'yfinance'
                    """,
                    (symbol, info["industry"]),
                )

                # 3) backfill market_cap on stocks_universe if it was empty
                if info["market_cap"] is not None:
                    conn.execute(
                        "UPDATE stocks_universe SET market_cap = COALESCE(market_cap, ?) "
                        "WHERE symbol = ?",
                        (info["market_cap"], symbol),
                    )
                rows_written += 1

            if i % progress_every == 0:
                conn.commit()
                if log:
                    print(f"  [industry_loader] {i}/{n_total} processed "
                          f"(written={rows_written}, failures={fetch_failures})")

            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

        conn.commit()
        return {
            "processed": n_total,
            "rows_written": rows_written,
            "industries_added": industries_added,
            "fetch_failures": fetch_failures,
        }
    finally:
        if own_conn:
            conn.close()


# ── CLI ─────────────────────────────────────────────────────────────


def _main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--symbols", help="Comma-separated symbols; default = all in stocks_universe")
    p.add_argument("--force", action="store_true", help="Re-pull even for symbols already in stock_industry")
    p.add_argument("--sleep", type=float, default=0.1, help="Seconds to sleep between calls (default 0.1)")
    args = p.parse_args()

    symbols = None
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    out = apply_yfinance_industries(
        symbols=symbols,
        force=args.force,
        sleep_seconds=args.sleep,
    )
    print()
    for k, v in out.items():
        print(f"  {k:20s}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
