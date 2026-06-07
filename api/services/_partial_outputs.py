"""Brief partial outputs — progressive polling support.

As `brief_service.get_brief` finishes each phase it writes the phase output
here. The polling GET /brief includes whatever's available so the UI can
render progressively instead of showing a 7-minute spinner.

Workflow:
    set(job_key, "lens", lens_dict)              ← after lens written
    set(job_key, "picks_skeleton", picks_meta)   ← after picks selected
    set(job_key, "picks_validated", picks_full)  ← after web validate
    set(job_key, "narrate", prose_dict)          ← after narrative
    clear(job_key)                                ← after force_restart

The full completed brief still lands in the regular cache via cache_set —
this table is scratch space for in-flight runs. Rows are auto-cleared when
a new job starts on the same key (INSERT OR REPLACE).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from src.utils.db import get_connection, init_db

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def set_partial(job_key: str, phase: str, payload) -> None:
    """Write a phase output for this job. Overwrites any prior row."""
    init_db()
    try:
        body = json.dumps(payload, default=str)
    except Exception as e:
        logger.warning(
            "brief_partial_outputs: cannot serialize %s/%s — skipping: %r",
            job_key, phase, e,
        )
        return
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO brief_partial_outputs "
            "(job_key, phase, payload, created_at) VALUES (?, ?, ?, ?)",
            (job_key, phase, body, _now_iso()),
        )
        conn.commit()
    finally:
        conn.close()


def get_partials(job_key: str) -> dict:
    """Return {phase: decoded_payload} for a job. Empty dict if nothing yet."""
    init_db()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT phase, payload FROM brief_partial_outputs WHERE job_key = ?",
            (job_key,),
        ).fetchall()
    finally:
        conn.close()
    out: dict = {}
    for r in rows:
        try:
            out[r["phase"]] = json.loads(r["payload"])
        except Exception:
            logger.warning(
                "brief_partial_outputs: corrupt payload for %s/%s — skipping",
                job_key, r["phase"],
            )
    return out


def clear(job_key: str) -> int:
    """Wipe all partials for a job. Returns row count deleted."""
    init_db()
    conn = get_connection()
    try:
        cur = conn.execute(
            "DELETE FROM brief_partial_outputs WHERE job_key = ?", (job_key,)
        )
        n = cur.rowcount
        conn.commit()
        return n
    finally:
        conn.close()
