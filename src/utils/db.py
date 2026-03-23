import json
import sqlite3
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent.parent.parent / "trading.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS cache (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_cache_expires ON cache(expires_at);

        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            report_type TEXT NOT NULL,
            content TEXT NOT NULL,
            verdict TEXT,
            risk_rating INTEGER,
            sentiment_score REAL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_reports_symbol ON reports(symbol);
        CREATE INDEX IF NOT EXISTS idx_reports_date ON reports(created_at);
        CREATE INDEX IF NOT EXISTS idx_reports_type ON reports(report_type);

        CREATE TABLE IF NOT EXISTS watchlist (
            symbol TEXT PRIMARY KEY,
            name TEXT,
            added_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            message TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT,
            severity TEXT NOT NULL DEFAULT 'info',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_alerts_symbol ON alerts(symbol);
        CREATE INDEX IF NOT EXISTS idx_alerts_date ON alerts(created_at);

        CREATE TABLE IF NOT EXISTS api_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            status TEXT NOT NULL,
            error_message TEXT,
            timestamp TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()


def cache_get(key: str) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT value, expires_at FROM cache WHERE key = ?", (key,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    if datetime.fromisoformat(row["expires_at"]) < datetime.utcnow():
        cache_delete(key)
        return None
    return json.loads(row["value"])


def cache_set(key: str, value: dict, ttl_minutes: int = 15) -> None:
    conn = get_connection()
    now = datetime.utcnow()
    expires = now + timedelta(minutes=ttl_minutes)
    conn.execute(
        "INSERT OR REPLACE INTO cache (key, value, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (key, json.dumps(value, default=str), now.isoformat(), expires.isoformat()),
    )
    conn.commit()
    conn.close()


def cache_delete(key: str) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM cache WHERE key = ?", (key,))
    conn.commit()
    conn.close()


def log_api_call(source: str, endpoint: str, status: str, error: str | None = None) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT INTO api_log (source, endpoint, status, error_message, timestamp) VALUES (?, ?, ?, ?, ?)",
        (source, endpoint, status, error, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def save_report(symbol: str, report_type: str, content: str, verdict: str | None = None,
                risk_rating: int | None = None, sentiment_score: float | None = None) -> int:
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO reports (symbol, report_type, content, verdict, risk_rating, sentiment_score, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (symbol, report_type, content, verdict, risk_rating, sentiment_score, datetime.utcnow().isoformat()),
    )
    conn.commit()
    report_id = cursor.lastrowid
    conn.close()
    return report_id


def get_reports(symbol: str | None = None, report_type: str | None = None, limit: int = 20) -> list[dict]:
    conn = get_connection()
    query = "SELECT * FROM reports WHERE 1=1"
    params: list = []
    if symbol:
        query += " AND symbol = ?"
        params.append(symbol)
    if report_type:
        query += " AND report_type = ?"
        params.append(report_type)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_report_by_id(report_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_watchlist() -> list[dict]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM watchlist ORDER BY added_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_watchlist_item(symbol: str, name: str = "") -> None:
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO watchlist (symbol, name, added_at) VALUES (?, ?, ?)",
        (symbol.upper(), name, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def remove_watchlist_item(symbol: str) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM watchlist WHERE symbol = ?", (symbol.upper(),))
    conn.commit()
    conn.close()


# --- Alerts ---

def save_alert(symbol: str, alert_type: str, message: str,
               old_value: str = "", new_value: str = "", severity: str = "info") -> int:
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO alerts (symbol, alert_type, message, old_value, new_value, severity, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (symbol, alert_type, message, old_value, new_value, severity, datetime.utcnow().isoformat()),
    )
    conn.commit()
    alert_id = cursor.lastrowid
    conn.close()
    return alert_id


def get_alerts(symbol: str | None = None, limit: int = 50) -> list[dict]:
    conn = get_connection()
    query = "SELECT * FROM alerts WHERE 1=1"
    params: list = []
    if symbol:
        query += " AND symbol = ?"
        params.append(symbol)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_latest_report_for_symbol(symbol: str) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM reports WHERE symbol = ? ORDER BY created_at DESC LIMIT 1",
        (symbol,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None
