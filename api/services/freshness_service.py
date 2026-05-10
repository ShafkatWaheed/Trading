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
