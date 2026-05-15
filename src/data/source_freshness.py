"""Per-source freshness registry for Wave 1+ external data sources.

Each external source (USPTO, openFDA, USAspending, Drewry WCI, …)
registers once with its cadence and TTL. After each fetch attempt,
`record_fetch()` updates the row with last_status, last_fetched_at,
next_due_at, and rate-limit residual.

Empty-payload pitfall (spec §6.2): when payload_count is 0, we set
next_due_at to fetched_at + 1 hour (NOT the normal TTL) so the
scheduler re-attempts soon. Memory pointer:
  ~/.claude/projects/-home-shafkat-project-Trading/memory/
    project_cache_strategy.md
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from src.utils.db import get_connection, init_db


@dataclass(frozen=True)
class SourceFreshness:
    source: str
    cadence: str
    ttl_seconds: int
    last_fetched_at: str | None
    next_due_at: str | None
    last_status: str | None
    last_error: str | None
    last_payload_count: int | None
    rate_limit_budget: int | None
    rate_limit_remaining: int | None


_EMPTY_RETRY_SECONDS = 3600   # 1h, per spec §6.2


def register_source(
    *,
    source: str,
    cadence: str,
    ttl_seconds: int,
    rate_limit_budget: int | None,
) -> None:
    """Insert or update the registry row for a source. Idempotent."""
    init_db()
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO source_freshness
          (source, cadence, ttl_seconds, rate_limit_budget, rate_limit_remaining)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(source) DO UPDATE SET
          cadence = excluded.cadence,
          ttl_seconds = excluded.ttl_seconds,
          rate_limit_budget = excluded.rate_limit_budget
        """,
        (source, cadence, int(ttl_seconds), rate_limit_budget, rate_limit_budget),
    )
    conn.commit()
    conn.close()


def record_fetch(
    *,
    source: str,
    status: str,
    payload_count: int | None,
    rate_limit_remaining: int | None,
    error: str | None,
) -> None:
    """Update last_fetched_at, next_due_at, status, payload_count.

    Empty-payload short TTL: when payload_count == 0, next_due_at is
    `fetched_at + 1h` instead of the source's normal TTL.
    """
    init_db()
    now = datetime.now(tz=timezone.utc)
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT ttl_seconds FROM source_freshness WHERE source = ?",
            (source,),
        ).fetchone()
        if row is None:
            raise ValueError(f"source not registered: {source}")
        ttl = int(row["ttl_seconds"])
        wait_s = _EMPTY_RETRY_SECONDS if payload_count == 0 else ttl
        next_due = now + timedelta(seconds=wait_s)

        conn.execute(
            """
            UPDATE source_freshness SET
              last_fetched_at = ?,
              next_due_at = ?,
              last_status = ?,
              last_error = ?,
              last_payload_count = ?,
              rate_limit_remaining = ?
            WHERE source = ?
            """,
            (
                now.isoformat(),
                next_due.isoformat(),
                status,
                error,
                int(payload_count) if payload_count is not None else None,
                rate_limit_remaining,
                source,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _row_to_source(row) -> SourceFreshness:
    return SourceFreshness(
        source=row["source"],
        cadence=row["cadence"],
        ttl_seconds=int(row["ttl_seconds"]),
        last_fetched_at=row["last_fetched_at"],
        next_due_at=row["next_due_at"],
        last_status=row["last_status"],
        last_error=row["last_error"],
        last_payload_count=row["last_payload_count"],
        rate_limit_budget=row["rate_limit_budget"],
        rate_limit_remaining=row["rate_limit_remaining"],
    )


def get_source(source: str) -> SourceFreshness | None:
    init_db()
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM source_freshness WHERE source = ?", (source,)
    ).fetchone()
    conn.close()
    return _row_to_source(row) if row is not None else None


def get_all_sources() -> list[SourceFreshness]:
    init_db()
    conn = get_connection()
    rows = conn.execute("SELECT * FROM source_freshness ORDER BY source").fetchall()
    conn.close()
    return [_row_to_source(r) for r in rows]
