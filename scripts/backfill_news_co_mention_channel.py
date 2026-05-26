"""Backfill the news-co-mention channel of composite_confidence.

For each unique symbol touched by `stock_relations`, fetch its recent news
once via `src.data.news.NewsProvider.search_stock_news` (Tavily → Exa →
Google News RSS fallback, cached 60min in the DB cache table). Then for
each edge (A, B), count how many of A's articles mention B (ticker or
company name) → composite-confidence news channel.

Cost-aware:
  * One news fetch per symbol (not per edge).
  * NewsProvider already caches non-empty results for 60 min in the DB,
    so re-runs in that window are free.
  * Symbols with empty news → skipped; their edges contribute 0 on this
    channel.

Usage:
    python scripts/backfill_news_co_mention_channel.py
    python scripts/backfill_news_co_mention_channel.py --days 30  # custom window
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data.news import NewsProvider
from src.graph.composite_confidence import count_news_co_mentions, recompute_for_all
from src.utils.db import get_connection, init_db


def _company_name_for(symbol: str) -> str:
    """Best-effort company name via yfinance (also used by NewsProvider).
    Returns '' on failure; the channel just becomes ticker-only."""
    try:
        import yfinance as yf
        info = yf.Ticker(symbol).info
        return (info.get("shortName") or info.get("longName") or "").strip()
    except Exception:
        return ""


def main(days: int = 30) -> int:
    init_db()
    conn = get_connection()
    try:
        symbols = set()
        for r in conn.execute("SELECT from_symbol, to_symbol FROM stock_relations").fetchall():
            symbols.add(r["from_symbol"])
            symbols.add(r["to_symbol"])

        # Also pull the stocks_universe name field so we can pass aliases to the
        # co-mention matcher without yet another yfinance call per symbol.
        name_for: dict[str, str] = {}
        for r in conn.execute(
            "SELECT symbol, name FROM stocks_universe WHERE symbol IN ({})".format(
                ",".join("?" * len(symbols))
            ),
            list(symbols),
        ).fetchall():
            if r["name"]:
                name_for[r["symbol"]] = r["name"]

        print(f"Fetching {days}-day news for {len(symbols)} symbols (cached 60min)…")
        provider = NewsProvider()
        news_by_symbol: dict[str, list[dict]] = {}
        misses = 0
        for sym in sorted(symbols):
            try:
                articles = provider.search_stock_news(sym, days=days)
            except Exception:
                articles = []
            if not articles:
                misses += 1
                continue
            news_by_symbol[sym] = articles
        print(f"  Fetched: {len(news_by_symbol)}   Misses: {misses}")

        def news_co_mention_fn(a: str, b: str) -> int:
            articles = news_by_symbol.get(a, [])
            if not articles:
                return 0
            aliases = [name_for.get(b, "")] if b in name_for else None
            return count_news_co_mentions(
                a, b,
                articles_for_target=articles,
                other_aliases=aliases,
            )

        from src.data.index_loader import load_all_cached
        try:
            etf_holdings = load_all_cached()
        except Exception:
            etf_holdings = None

        out = recompute_for_all(
            conn,
            etf_holdings=etf_holdings,
            news_co_mention_fn=news_co_mention_fn,
        )
        print(f"Updated composite_confidence for {out['updated']} edges.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30, help="News lookback window in days")
    args = parser.parse_args()
    raise SystemExit(main(days=args.days))
