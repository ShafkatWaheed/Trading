"""Entity Match Debug service — read recent match decisions for a ticker."""
from __future__ import annotations

import json

from src.utils.db import get_connection, init_db


def get_matches_for_ticker(ticker: str, *, lookback_days: int = 30) -> dict:
    """Return the most recent entity_match_decisions for `ticker`.

    Shape (consumed directly by the /stocks/{t}/entity-matches endpoint):
        {
          "ticker": str,
          "matches": [
            {
              "source": "patents" | "fda" | ...,
              "input_name": str,
              "matched_alias": str | None,
              "method": "exact_cik" | "exact_uei" | "exact_alias" | "fuzzy" | "no_match",
              "confidence": float,
              "rejected": [{"ticker": str, "alias_name": str, "score": float}, ...],
              "decided_at": str,
            }, ...
          ]
        }
    """
    from datetime import datetime, timedelta, timezone
    cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=lookback_days)).isoformat()

    init_db()
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT source, input_name, matched_alias, method, confidence,
               rejected_candidates_json, decided_at
        FROM entity_match_decisions
        WHERE ticker = ? AND decided_at >= ?
        ORDER BY decided_at DESC
        """,
        (ticker.upper(), cutoff),
    ).fetchall()
    conn.close()

    matches = []
    seen_sources: set[str] = set()
    for r in rows:
        # De-dupe by source — show latest decision per source
        if r["source"] in seen_sources:
            continue
        seen_sources.add(r["source"])
        rejected = []
        if r["rejected_candidates_json"]:
            try:
                rejected = json.loads(r["rejected_candidates_json"])
            except Exception:
                rejected = []
        matches.append({
            "source": r["source"],
            "input_name": r["input_name"],
            "matched_alias": r["matched_alias"],
            "method": r["method"],
            "confidence": float(r["confidence"]),
            "rejected": rejected,
            "decided_at": r["decided_at"],
        })

    return {"ticker": ticker.upper(), "matches": matches}
