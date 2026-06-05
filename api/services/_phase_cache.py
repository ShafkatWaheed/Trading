"""Phase-level checkpoint cache for the brief pipeline.

Saves the output of each expensive phase (Claude calls, multi-API enrichment)
keyed by (symbol, phase, input_hash). On a restart we replay until the first
cache miss — failed phases re-run, completed phases are free.

Symbol is a scoping namespace — for the daily market brief we use the literal
string "market" since the brief is market-wide, not per-ticker. For per-symbol
flows the ticker string is the namespace and `invalidate(symbol)` clears
everything for that ticker.

TTL defaults to 6h: short enough that the brief reflects the current state of
news/fundamentals, long enough that a restart within a single session
(typical Claude flake → user clicks regenerate) reuses the expensive earlier
phases.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone

from src.utils.db import get_connection, init_db

logger = logging.getLogger(__name__)

_DEFAULT_TTL_HOURS = 6


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _hash(parts: object) -> str:
    """Stable 16-char content hash. sort_keys=True keeps dict order from
    perturbing the hash; default=str handles datetime/Decimal payloads."""
    return hashlib.sha256(
        json.dumps(parts, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]


def make_key(symbol: str, phase: str, input_parts: object) -> str:
    return f"{symbol.upper()}::{phase}::{_hash(input_parts)}"


def get(
    symbol: str,
    phase: str,
    input_parts: object,
    *,
    ttl_hours: int = _DEFAULT_TTL_HOURS,
):
    """Return cached payload (parsed JSON) or None. TTL-bounded by created_at."""
    init_db()
    key = make_key(symbol, phase, input_parts)
    cutoff = (
        datetime.now(tz=timezone.utc) - timedelta(hours=ttl_hours)
    ).isoformat()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT payload FROM brief_phase_cache "
            "WHERE cache_key = ? AND created_at > ?",
            (key, cutoff),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    try:
        return json.loads(row["payload"])
    except Exception:
        logger.warning(
            "brief_phase_cache: failed to decode payload for key=%s", key
        )
        return None


def put(symbol: str, phase: str, input_parts: object, payload) -> None:
    """Write phase output. Overwrites existing entry for same key."""
    init_db()
    key = make_key(symbol, phase, input_parts)
    try:
        body = json.dumps(payload, default=str)
    except Exception as e:
        logger.warning(
            "brief_phase_cache: cannot serialize payload (%r) — skipping put",
            e,
        )
        return
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO brief_phase_cache "
            "(cache_key, payload, created_at) VALUES (?, ?, ?)",
            (key, body, _now_iso()),
        )
        conn.commit()
    finally:
        conn.close()


def invalidate(symbol: str) -> int:
    """Wipe all cached phases for a symbol (called by /brief/restart)."""
    init_db()
    conn = get_connection()
    try:
        cur = conn.execute(
            "DELETE FROM brief_phase_cache WHERE cache_key LIKE ?",
            (f"{symbol.upper()}::%",),
        )
        n = cur.rowcount
        conn.commit()
        return n
    finally:
        conn.close()
