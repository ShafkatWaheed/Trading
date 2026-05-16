"""Innovation service — orchestrates USPTO PatentsView + analysis mapper.

Returns a dict consumable directly by the new /stocks/{t}/innovation route.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from dataclasses import asdict

from src.analysis.sector_signals.innovation import patents_to_information
from src.data.entity_aliases import resolve_ticker_with_audit
from src.data.uspto_patentsview import fetch_patents_for_assignee
from src.utils.db import get_connection, init_db


def _get_uspto_canonical_names(ticker: str) -> list[str]:
    """Look up the USPTO canonical names for a ticker from entity_aliases."""
    init_db()
    conn = get_connection()
    rows = conn.execute(
        "SELECT alias_name FROM entity_aliases "
        "WHERE ticker = ? AND alias_type = 'uspto_canonical'",
        (ticker,),
    ).fetchall()
    conn.close()
    return [r["alias_name"] for r in rows]


def get_innovation_for_ticker(ticker: str, *, lookback_days: int = 365) -> dict:
    """Build Innovation card payload for `ticker`.

    Strategy:
      1. Look up uspto_canonical aliases for the ticker
      2. If none, fall back to the legal alias (resolver round-trip)
      3. Query PatentsView for each canonical assignee name, dedupe by patent_id
      4. Map raw patents → StockInformation
    """
    canonical_names = _get_uspto_canonical_names(ticker)
    if not canonical_names:
        # No canonical assignee seeded — try the legal name as a single best-effort query
        # (this won't catch subsidiary patents, but it's better than nothing)
        conn = get_connection()
        row = conn.execute(
            "SELECT alias_name FROM entity_aliases WHERE ticker = ? AND alias_type = 'legal' LIMIT 1",
            (ticker,),
        ).fetchone()
        conn.close()
        if row:
            canonical_names = [row["alias_name"]]

    since = (datetime.now(tz=timezone.utc) - timedelta(days=lookback_days)).date().isoformat()
    seen_ids: set[str] = set()
    merged: list[dict] = []
    for name in canonical_names:
        # Log the resolution decision (input was the canonical name we're querying)
        resolve_ticker_with_audit(name, source="innovation", use_fuzzy=False)
        for p in fetch_patents_for_assignee(name, since_date=since):
            if p["patent_id"] in seen_ids:
                continue
            seen_ids.add(p["patent_id"])
            merged.append(p)

    as_of = datetime.now(tz=timezone.utc).isoformat()
    info = patents_to_information(ticker=ticker, patents=merged, as_of=as_of)
    payload = asdict(info)
    return payload
