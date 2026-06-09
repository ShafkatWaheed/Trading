"""Cache administration — audit, clear by namespace, purge expired.

Why this exists
---------------
An audit revealed 6344 of 7514 cache rows (84%) were expired but still
on disk because `cache_get` returns None on stale rows without ever
deleting them. Over months that bloats the DB and slows the LIKE
queries used by predictions bulk loaders.

Operations
----------
  audit()                 — count rows by namespace + expiry bucket
  clear_namespace(prefix) — wipe all rows where key LIKE 'prefix:%'
  clear_expired()         — wipe all rows whose expires_at < now
  clear_key(exact_key)    — wipe a single row by exact key
  clear_all()             — wipe EVERY cache row (admin nuclear option)

The nightly scheduler in api/main.py calls clear_expired() at 3:00 ET
so the audit + clear endpoints below are for ad-hoc admin operations
only — UI on /data-sources lets the user purge a stuck namespace
without dropping into SQL.
"""
from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime

from src.utils.db import get_connection, init_db

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def audit() -> dict:
    """Return cache state: total rows, per-namespace counts, expiry buckets.

    Used by GET /admin/cache/audit and the Data Sources cache panel.
    """
    init_db()
    conn = get_connection()
    try:
        total = conn.execute("SELECT COUNT(*) AS n FROM cache").fetchone()["n"]
        rows = conn.execute("SELECT key, expires_at FROM cache").fetchall()
    finally:
        conn.close()

    by_namespace: Counter[str] = Counter()
    expiry_buckets = {
        "expired": 0, "lt_1h": 0, "lt_24h": 0,
        "lt_7d": 0,   "lt_30d": 0, "gt_30d": 0,
    }
    now = datetime.utcnow()

    for r in rows:
        # Namespace is everything before the first colon (e.g. "options_flow")
        prefix = r["key"].split(":")[0]
        by_namespace[prefix] += 1

        try:
            e = datetime.fromisoformat(r["expires_at"])
        except Exception:
            continue
        delta_h = (e - now).total_seconds() / 3600.0
        if   delta_h < 0:    expiry_buckets["expired"] += 1
        elif delta_h < 1:    expiry_buckets["lt_1h"]   += 1
        elif delta_h < 24:   expiry_buckets["lt_24h"]  += 1
        elif delta_h < 168:  expiry_buckets["lt_7d"]   += 1
        elif delta_h < 720:  expiry_buckets["lt_30d"]  += 1
        else:                expiry_buckets["gt_30d"]  += 1

    # Top namespaces by row count (the ones worth purging)
    top = [
        {"namespace": k, "rows": v}
        for k, v in by_namespace.most_common(30)
    ]
    return {
        "total":          total,
        "by_namespace":   top,
        "expiry_buckets": expiry_buckets,
        "as_of":          _now_iso(),
    }


def clear_namespace(prefix: str) -> dict:
    """Delete every cache row where key starts with `prefix:`.

    Returns {deleted: int}. Refuses to operate on empty / single-char
    prefixes so a typo can't wipe the whole cache.
    """
    if not prefix or len(prefix) < 2:
        return {"deleted": 0, "error": "prefix_too_short"}
    init_db()
    conn = get_connection()
    try:
        cur = conn.execute(
            "DELETE FROM cache WHERE key LIKE ?",
            (f"{prefix}:%",),
        )
        n = cur.rowcount
        conn.commit()
        logger.info("cache_admin: cleared %d rows for namespace %s", n, prefix)
        return {"deleted": n, "namespace": prefix}
    finally:
        conn.close()


def clear_expired() -> dict:
    """Delete every row whose expires_at has passed. Returns count."""
    init_db()
    now = _now_iso()
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM cache WHERE expires_at < ?", (now,))
        n = cur.rowcount
        conn.commit()
        if n:
            logger.info("cache_admin: pruned %d expired rows", n)
        return {"deleted": n}
    finally:
        conn.close()


def clear_key(key: str) -> dict:
    """Delete one exact cache row by key. Returns {deleted: 0|1}."""
    if not key:
        return {"deleted": 0, "error": "empty_key"}
    init_db()
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM cache WHERE key = ?", (key,))
        n = cur.rowcount
        conn.commit()
        return {"deleted": n, "key": key}
    finally:
        conn.close()


def clear_all() -> dict:
    """Nuclear option — wipe EVERY cache row.

    Use only when intentionally rebuilding caches from cold (e.g. after
    a schema migration that changed serialized shapes). Routes guard
    this behind an explicit `confirm=true` query param.
    """
    init_db()
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM cache")
        n = cur.rowcount
        conn.commit()
        logger.warning("cache_admin: NUKED entire cache — %d rows deleted", n)
        return {"deleted": n}
    finally:
        conn.close()
