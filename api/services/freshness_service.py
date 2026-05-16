"""Freshness service — read the queue + acknowledge user actions (Phase 7B)."""

from __future__ import annotations

from src.freshness.orchestrator import acknowledge as _acknowledge
from src.utils.db import get_connection, init_db


def get_queue() -> dict:
    """Return all stocks currently flagged for review, plus a status histogram."""
    init_db()
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT symbol, status, trigger_reason, flagged_at, last_extracted_at
            FROM edge_freshness
            WHERE status = 'needs_review'
            ORDER BY flagged_at DESC NULLS LAST, symbol
            """
        ).fetchall()
        counts = {
            r[0]: r[1]
            for r in conn.execute(
                "SELECT status, COUNT(*) FROM edge_freshness GROUP BY status"
            ).fetchall()
        }
        return {
            "queue": [dict(r) for r in rows],
            "counts_by_status": counts,
        }
    finally:
        conn.close()


def acknowledge(symbol: str, action: str) -> dict:
    """Apply an action: re_extract | skip_30d | pin_current."""
    return _acknowledge(symbol, action=action)


# ── Sector-influence Wave 1: per-source freshness surface ────────────


def get_sources_status() -> dict:
    """Return the per-source freshness registry for the admin /freshness page.

    Shape:
        {
          "sources": [ {source, cadence, ttl_seconds, last_fetched_at,
                        next_due_at, last_status, last_payload_count,
                        rate_limit_remaining, ...}, ... ],
          "counts": {"never_fetched": N, "ok": M, "error": K, "empty": E, ...},
        }
    """
    from src.data.source_freshness import get_all_sources

    rows = get_all_sources()
    out: list[dict] = []
    counts: dict[str, int] = {}
    for r in rows:
        status_key = r.last_status if r.last_status else "never_fetched"
        counts[status_key] = counts.get(status_key, 0) + 1
        out.append({
            "source": r.source,
            "cadence": r.cadence,
            "ttl_seconds": r.ttl_seconds,
            "last_fetched_at": r.last_fetched_at,
            "next_due_at": r.next_due_at,
            "last_status": r.last_status,
            "last_error": r.last_error,
            "last_payload_count": r.last_payload_count,
            "rate_limit_budget": r.rate_limit_budget,
            "rate_limit_remaining": r.rate_limit_remaining,
        })
    return {"sources": out, "counts": counts}
