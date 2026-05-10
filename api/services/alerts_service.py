"""Alerts service: read, mark seen, summary."""
from __future__ import annotations

from src.utils.db import init_db, get_alerts, get_connection


def list_alerts(symbol: str | None = None, limit: int = 50) -> list[dict]:
    init_db()
    rows = get_alerts(symbol=symbol, limit=limit)
    out = []
    for r in rows:
        out.append({
            "id": r.get("id"),
            "symbol": r.get("symbol", ""),
            "alert_type": r.get("alert_type", ""),
            "message": r.get("message", ""),
            "old_value": r.get("old_value"),
            "new_value": r.get("new_value"),
            "severity": r.get("severity", "info"),
            "created_at": str(r.get("created_at", "")),
        })
    return out


def get_summary() -> dict:
    """Quick badge counts for the nav."""
    init_db()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS total, "
            "SUM(CASE WHEN severity='critical' THEN 1 ELSE 0 END) AS critical, "
            "SUM(CASE WHEN severity='warning' THEN 1 ELSE 0 END) AS warning, "
            "SUM(CASE WHEN created_at > datetime('now', '-24 hours') THEN 1 ELSE 0 END) AS last_24h "
            "FROM alerts"
        ).fetchone()
        return {
            "total": int((row["total"] or 0) if row else 0),
            "critical": int((row["critical"] or 0) if row else 0),
            "warning": int((row["warning"] or 0) if row else 0),
            "last_24h": int((row["last_24h"] or 0) if row else 0),
        }
    finally:
        conn.close()


def clear_all() -> dict:
    """Wipe all alerts."""
    init_db()
    conn = get_connection()
    try:
        before = conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
        conn.execute("DELETE FROM alerts")
        conn.commit()
        return {"ok": True, "deleted": int(before)}
    finally:
        conn.close()
