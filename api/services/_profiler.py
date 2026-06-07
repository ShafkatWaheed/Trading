"""Phase timing profiler.

Wraps each phase of a long pipeline (brief, daily-picks, etc.) and records
wall-clock duration to phase_timings. The point: find the actual bottleneck
before optimizing. If the brief takes 110s and 95 of those are inside the
single Claude lens call, parallelizing the rest is pointless — pool the
Claude process. If the 110s is spread across context fetchers and enrich,
parallelization wins. The table tells you which.

Usage:
    from api.services import _profiler
    run_id = _profiler.start_run("brief")
    with _profiler.Timer(run_id, "context"):
        ctx = _market_context()
    with _profiler.Timer(run_id, "lens"):
        lens = _derive_search_query(ctx)
    ...

Read recent runs via `get_recent_runs()` or `GET /brief/timings`.
"""
from __future__ import annotations

import logging
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from src.utils.db import get_connection, init_db

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def start_run(label: str = "brief") -> str:
    """Return a fresh run_id. The label is just a prefix for filtering."""
    return f"{label}-{uuid.uuid4().hex[:12]}"


@contextmanager
def Timer(run_id: str, phase: str, *, note: str = ""):
    """Record wall-clock duration of `phase` under `run_id`.

    Always writes — even if the block raises (with success=0). The write
    failure is logged but never re-raised, so profiling can't break the
    pipeline it's measuring.
    """
    started_at = _now_iso()
    t0 = time.perf_counter()
    ok = True
    try:
        yield
    except Exception:
        ok = False
        raise
    finally:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        ended_at = _now_iso()
        try:
            _record(run_id, phase, duration_ms, started_at, ended_at, ok, note)
        except Exception as e:
            logger.warning(
                "phase_timings record failed (run_id=%s phase=%s): %r",
                run_id, phase, e,
            )


def _record(
    run_id: str,
    phase: str,
    duration_ms: int,
    started_at: str,
    ended_at: str,
    ok: bool,
    note: str,
) -> None:
    init_db()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO phase_timings
              (run_id, phase, duration_ms, started_at, ended_at, success, note)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, phase, duration_ms, started_at, ended_at, 1 if ok else 0, note or None),
        )
        conn.commit()
    finally:
        conn.close()


def get_recent_runs(
    *, limit: int = 20, label_prefix: str | None = None
) -> list[dict]:
    """Return per-run summaries with phase breakdowns, newest first.

    Each item:
      {
        "run_id": "brief-abc123...",
        "started_at": "2026-06-07T...",
        "total_ms": 87431,
        "phase_count": 9,
        "phases": [
          {"phase": "context", "duration_ms": 1240, "success": 1},
          {"phase": "lens",    "duration_ms": 64210, "success": 1},
          ...
        ]
      }
    """
    init_db()
    conn = get_connection()
    try:
        if label_prefix:
            sql = """
                SELECT run_id,
                       MIN(started_at)  AS started_at,
                       SUM(duration_ms) AS total_ms,
                       COUNT(*)         AS phase_count
                  FROM phase_timings
                 WHERE run_id LIKE ?
                 GROUP BY run_id
                 ORDER BY started_at DESC
                 LIMIT ?
            """
            runs = [dict(r) for r in conn.execute(sql, (f"{label_prefix}%", limit)).fetchall()]
        else:
            sql = """
                SELECT run_id,
                       MIN(started_at)  AS started_at,
                       SUM(duration_ms) AS total_ms,
                       COUNT(*)         AS phase_count
                  FROM phase_timings
                 GROUP BY run_id
                 ORDER BY started_at DESC
                 LIMIT ?
            """
            runs = [dict(r) for r in conn.execute(sql, (limit,)).fetchall()]

        for run in runs:
            rows = conn.execute(
                """
                SELECT phase, duration_ms, success, note
                  FROM phase_timings
                 WHERE run_id = ?
                 ORDER BY started_at
                """,
                (run["run_id"],),
            ).fetchall()
            run["phases"] = [dict(r) for r in rows]
        return runs
    finally:
        conn.close()
