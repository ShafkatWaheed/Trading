"""Backfill the return-correlation channel of composite_confidence.

For each edge in `stock_relations`, compute the Pearson r between the two
symbols' 60-day daily returns (from Tiingo's cached daily-prices endpoint)
and recompute composite_confidence.

Cost-aware:
  * Pre-fetches returns once per UNIQUE symbol involved in any edge
    (~150-200 symbols, not 344 pairs × 2 = 688).
  * Tiingo's cache_get/cache_set kicks in via get_daily_prices, so reruns
    within 12 h cost zero network calls.
  * Symbols that fail to fetch (no key, rate-limited, etc.) are skipped;
    their edges fall back to no correlation contribution.

Usage:
    python scripts/backfill_correlation_channel.py
    python scripts/backfill_correlation_channel.py --window 90    # custom days
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.analysis.commodity_validator import pearson_correlation
from src.data.tiingo import get_daily_prices
from src.graph.composite_confidence import recompute_for_all
from src.utils.db import get_connection, init_db


def fetch_returns(symbol: str, window_days: int) -> list[float] | None:
    """Fetch the last `window_days` of daily returns via Tiingo.

    Returns None on fetch failure or insufficient data.
    """
    end = datetime.utcnow().date()
    start = end - timedelta(days=window_days * 2)  # over-fetch for trading-day buffer
    rows = get_daily_prices(symbol, start=start.isoformat(), end=end.isoformat())
    if not rows or len(rows) < 5:
        return None
    # Use adjClose if present; fall back to close.
    closes: list[float] = []
    for r in rows:
        c = r.get("adjClose") or r.get("close")
        if c is None:
            continue
        closes.append(float(c))
    if len(closes) < 5:
        return None
    # Convert closes → daily simple returns.
    returns = [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes))]
    return returns[-window_days:] if len(returns) > window_days else returns


def main(window_days: int = 60) -> int:
    init_db()
    conn = get_connection()
    try:
        symbols = set()
        for r in conn.execute("SELECT from_symbol, to_symbol FROM stock_relations").fetchall():
            symbols.add(r["from_symbol"])
            symbols.add(r["to_symbol"])

        print(f"Fetching {window_days}-day returns for {len(symbols)} symbols (Tiingo, cached)…")
        returns_cache: dict[str, list[float]] = {}
        misses = 0
        for sym in sorted(symbols):
            r = fetch_returns(sym, window_days)
            if r is None:
                misses += 1
                continue
            returns_cache[sym] = r
        print(f"  Fetched: {len(returns_cache)}   Misses: {misses}")

        def correlation_fn(a: str, b: str) -> float | None:
            ra = returns_cache.get(a)
            rb = returns_cache.get(b)
            if ra is None or rb is None:
                return None
            # Align lengths (use the shorter)
            n = min(len(ra), len(rb))
            if n < 5:
                return None
            try:
                return pearson_correlation(ra[-n:], rb[-n:])
            except Exception:
                return None

        # Re-load ETF holdings so we don't drop that channel — we want the
        # FULL composite score, not just correlation.
        from src.data.index_loader import load_all_cached
        try:
            etf_holdings = load_all_cached()
        except Exception:
            etf_holdings = None

        out = recompute_for_all(
            conn,
            etf_holdings=etf_holdings,
            correlation_fn=correlation_fn,
        )
        print(f"Updated composite_confidence for {out['updated']} edges.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--window", type=int, default=60, help="Days of returns used for correlation")
    args = parser.parse_args()
    raise SystemExit(main(window_days=args.window))
