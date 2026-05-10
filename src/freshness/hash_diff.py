"""Layer 2: business-summary hash-diff detector.

When yfinance's `longBusinessSummary` for a stock changes (acquisition,
spinoff, segment rename, M&A, etc.), it's a strong signal that the stock's
edges are stale and need re-extraction. This module computes a stable hash
of the summary text and compares against the last value stored in
`edge_freshness.last_summary_hash`.

Network-gated: tests inject a fake summary fetcher.
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from typing import Callable

from src.utils.db import get_connection, init_db


def business_summary_hash(text: str) -> str:
    """Stable 16-char hex hash. Whitespace-normalised so trivial reformatting
    doesn't trigger false positives."""
    normalised = " ".join((text or "").split()).lower()
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()[:16]


def _default_fetch(symbol: str) -> str | None:
    try:
        import yfinance as yf
        info = yf.Ticker(symbol).info or {}
        return info.get("longBusinessSummary")
    except Exception:
        return None


def detect_hash_change(
    symbol: str,
    *,
    fetch_fn: Callable[[str], str | None] | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict:
    """Detect whether the business summary changed since the last check.

    Returns dict with keys: symbol, previous_hash, current_hash, changed (bool),
    error (str | None).
    """
    init_db()
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    fetch_fn = fetch_fn or _default_fetch

    try:
        summary = fetch_fn(symbol)
        if not summary:
            return {
                "symbol": symbol,
                "previous_hash": None,
                "current_hash": None,
                "changed": False,
                "error": "no_summary",
            }

        current = business_summary_hash(summary)
        row = conn.execute(
            "SELECT last_summary_hash FROM edge_freshness WHERE symbol = ?",
            (symbol,),
        ).fetchone()
        previous = row["last_summary_hash"] if row else None

        # Update / insert the current hash so subsequent calls have a baseline.
        conn.execute(
            """
            INSERT INTO edge_freshness (symbol, last_summary_hash, last_extracted_at)
            VALUES (?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                last_summary_hash = excluded.last_summary_hash,
                last_extracted_at = excluded.last_extracted_at
            """,
            (symbol, current, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()

        return {
            "symbol": symbol,
            "previous_hash": previous,
            "current_hash": current,
            "changed": previous is not None and previous != current,
            "error": None,
        }
    finally:
        if own_conn:
            conn.close()
