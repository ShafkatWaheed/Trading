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

        CREATE TABLE IF NOT EXISTS backtest_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL, signal_name TEXT NOT NULL,
            timeframe TEXT, lookback_days INTEGER, hold_days INTEGER,
            total_trades INTEGER, wins INTEGER, losses INTEGER,
            win_rate REAL, avg_return REAL, total_return REAL,
            max_gain REAL, max_loss REAL, max_drawdown REAL,
            sharpe_ratio REAL, created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_bt_symbol ON backtest_results(symbol);

        CREATE TABLE IF NOT EXISTS backtest_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            backtest_id INTEGER, symbol TEXT NOT NULL,
            signal_name TEXT, direction TEXT,
            entry_date TEXT, entry_price REAL,
            exit_date TEXT, exit_price REAL,
            pnl REAL, pnl_percent REAL, hold_days INTEGER,
            outcome TEXT
        );

        CREATE TABLE IF NOT EXISTS journal_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL, direction TEXT NOT NULL,
            entry_date TEXT, entry_price REAL,
            exit_date TEXT, exit_price REAL,
            shares INTEGER, pnl REAL, pnl_percent REAL,
            report_verdict TEXT, thesis TEXT, notes TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_journal_symbol ON journal_trades(symbol);
        CREATE INDEX IF NOT EXISTS idx_journal_status ON journal_trades(status);

        CREATE TABLE IF NOT EXISTS portfolio_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            portfolio_name TEXT NOT NULL,
            date TEXT NOT NULL, total_value REAL,
            cash REAL, invested REAL,
            daily_return REAL, cumulative_return REAL,
            benchmark_return REAL, positions_json TEXT
        );

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


# --- Backtest ---

def save_backtest_result(data: dict) -> int:
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO backtest_results (symbol, signal_name, timeframe, lookback_days, hold_days, "
        "total_trades, wins, losses, win_rate, avg_return, total_return, "
        "max_gain, max_loss, max_drawdown, sharpe_ratio, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (data["symbol"], data["signal_name"], data.get("timeframe", ""),
         data.get("lookback_days", 0), data.get("hold_days", 0),
         data["total_trades"], data["wins"], data["losses"],
         data["win_rate"], data["avg_return"], data["total_return"],
         data["max_gain"], data["max_loss"], data["max_drawdown"],
         data["sharpe_ratio"], datetime.utcnow().isoformat()),
    )
    conn.commit()
    bt_id = cursor.lastrowid
    conn.close()
    return bt_id


def save_backtest_trade(bt_id: int, trade: dict) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT INTO backtest_trades (backtest_id, symbol, signal_name, direction, "
        "entry_date, entry_price, exit_date, exit_price, pnl, pnl_percent, hold_days, outcome) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (bt_id, trade["symbol"], trade["signal_name"], trade["direction"],
         trade["entry_date"], trade["entry_price"], trade["exit_date"], trade["exit_price"],
         trade["pnl"], trade["pnl_percent"], trade["hold_days"], trade["outcome"]),
    )
    conn.commit()
    conn.close()


# --- Journal ---

def save_journal_trade(symbol: str, direction: str, entry_date: str, entry_price: float,
                       shares: int, report_verdict: str = "", thesis: str = "") -> int:
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO journal_trades (symbol, direction, entry_date, entry_price, "
        "shares, report_verdict, thesis, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?)",
        (symbol.upper(), direction, entry_date, entry_price, shares,
         report_verdict, thesis, datetime.utcnow().isoformat()),
    )
    conn.commit()
    trade_id = cursor.lastrowid
    conn.close()
    return trade_id


def close_journal_trade(trade_id: int, exit_price: float, exit_date: str = "", notes: str = "") -> None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM journal_trades WHERE id = ?", (trade_id,)).fetchone()
    if not row:
        conn.close()
        return
    entry_price = row["entry_price"]
    shares = row["shares"]
    direction = row["direction"]

    if direction == "long":
        pnl = (exit_price - entry_price) * shares
    else:
        pnl = (entry_price - exit_price) * shares
    pnl_pct = ((exit_price - entry_price) / entry_price * 100) if direction == "long" else ((entry_price - exit_price) / entry_price * 100)

    if not exit_date:
        exit_date = datetime.utcnow().strftime("%Y-%m-%d")

    conn.execute(
        "UPDATE journal_trades SET exit_date=?, exit_price=?, pnl=?, pnl_percent=?, notes=?, status='closed' WHERE id=?",
        (exit_date, exit_price, pnl, pnl_pct, notes, trade_id),
    )
    conn.commit()
    conn.close()


def get_journal_trades(status: str | None = None, symbol: str | None = None) -> list[dict]:
    conn = get_connection()
    query = "SELECT * FROM journal_trades WHERE 1=1"
    params: list = []
    if status:
        query += " AND status = ?"
        params.append(status)
    if symbol:
        query += " AND symbol = ?"
        params.append(symbol.upper())
    query += " ORDER BY created_at DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --- Portfolio Snapshots ---

def save_portfolio_snapshot(name: str, date: str, total_value: float, cash: float,
                            invested: float, daily_return: float, cumulative_return: float,
                            benchmark_return: float, positions_json: str = "") -> None:
    conn = get_connection()
    conn.execute(
        "INSERT INTO portfolio_snapshots (portfolio_name, date, total_value, cash, invested, "
        "daily_return, cumulative_return, benchmark_return, positions_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (name, date, total_value, cash, invested, daily_return, cumulative_return,
         benchmark_return, positions_json),
    )
    conn.commit()
    conn.close()


def get_portfolio_history(name: str) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM portfolio_snapshots WHERE portfolio_name = ? ORDER BY date",
        (name,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
