"""Atomic nightly backup of trading.db with 14-day retention.

Why this exists
---------------
CLAUDE.md documents that trading.db has been wiped TWICE — once by
a test fixture's DELETE FROM stocks_universe, once by the migration
test path. The graph took thousands of stocks with it and recovery
required offline restoration from cached ETF holdings.

This script eliminates that recovery scramble. It writes a fresh
backup every night and keeps the last 14, rolling old ones out as
new ones come in.

Backup target
-------------
data/db_backups/trading-YYYY-MM-DD-HHMM.db

We use sqlite3's `.backup` API (not file copy) because the DB is in
WAL mode — a file copy during an active write can produce a corrupt
snapshot. `.backup` takes a consistent point-in-time copy even with
writers active.

Retention
---------
Keep the newest 14 backups. Older ones are deleted on each run so
disk usage stays bounded around ~1.4GB at current DB size.

Manual usage
------------
    .venv/bin/python scripts/backup_db.py

Scheduled usage
---------------
api/main.py registers this in the daily scheduler. Failures are
logged but never raise — a backup failure must NEVER block startup
or the rest of the scheduler.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


logger = logging.getLogger(__name__)


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DB_PATH = _PROJECT_ROOT / "trading.db"
_BACKUP_DIR = _PROJECT_ROOT / "data" / "db_backups"
_RETENTION = 14


def _ensure_backup_dir() -> Path:
    _BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    return _BACKUP_DIR


def _backup_filename(now: datetime | None = None) -> str:
    now = now or datetime.now(tz=timezone.utc)
    return f"trading-{now.strftime('%Y-%m-%d-%H%M')}.db"


def run_backup() -> dict:
    """Take one fresh backup + prune to retention. Returns a status dict."""
    _ensure_backup_dir()

    if not _DB_PATH.exists():
        return {"ok": False, "reason": "source_db_missing", "path": str(_DB_PATH)}

    target = _BACKUP_DIR / _backup_filename()
    tmp = target.with_suffix(target.suffix + ".tmp")

    # Use sqlite3 .backup for a consistent snapshot — safer than file copy
    # while the DB is being written to in WAL mode.
    src = sqlite3.connect(str(_DB_PATH))
    try:
        dst = sqlite3.connect(str(tmp))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()

    # Atomic rename so an interrupted backup can never leave a corrupt
    # half-written .db with the canonical filename.
    os.replace(tmp, target)

    pruned = _prune_old_backups()
    size_mb = target.stat().st_size / (1024 * 1024)
    return {
        "ok":            True,
        "target":        str(target),
        "size_mb":       round(size_mb, 1),
        "pruned":        pruned,
        "kept_count":    len(_list_backups()),
    }


def _list_backups() -> list[Path]:
    if not _BACKUP_DIR.exists():
        return []
    return sorted(
        _BACKUP_DIR.glob("trading-*.db"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def _prune_old_backups() -> int:
    """Delete everything past the retention window. Returns count deleted."""
    backups = _list_backups()
    to_delete = backups[_RETENTION:]
    n = 0
    for p in to_delete:
        try:
            p.unlink()
            n += 1
        except Exception as e:
            logger.warning("backup_db: failed to delete old backup %s: %r", p, e)
    return n


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    result = run_backup()
    if result.get("ok"):
        print(
            f"✓ backup → {result['target']} "
            f"({result['size_mb']} MB) · pruned {result['pruned']} old · "
            f"keeping {result['kept_count']}"
        )
        sys.exit(0)
    print(f"✗ backup failed: {result.get('reason', 'unknown')}", file=sys.stderr)
    sys.exit(1)
