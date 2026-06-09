"""Daily top-10 gainers predictions.

Pipeline
--------
Each morning (pre-market) we score every Tier A symbol using the active
strategy and store the top 10 picks. After market close we record each
pick's actual % move so accuracy can be tracked over time. Claude
periodically reviews a window of completed predictions and proposes a
new strategy version; old versions are kept for comparison.

Point-in-time guarantee
-----------------------
- Predictions for date `D` are generated PRE-OPEN of `D` using only
  data available at or before the close of `D-1`. No current-day data.
- Actuals for date `D` are stamped AFTER `D` market close.
- Strategy reviews look only at rows where `actuals` is recorded — the
  in-flight day is never used for training.

Phase 1 scope (this file)
-------------------------
- Schema bootstrap (a baseline strategy is auto-inserted on first call)
- `generate_predictions_for_date(date)` — score Tier A, pick top 10,
  persist to `daily_predictions`. Idempotent: returns the existing rows
  if predictions for that date are already stored.
- `get_predictions_for_date(date)` — read-only fetch
- `get_predictions_today()` — convenience wrapper

Baseline strategy v1
--------------------
"5d momentum" — rank by trailing 5-day % change. Deliberately simple
so Claude has clear room to improve it. Each pick carries a 1-line
reasoning string for the UI.
"""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

from src.data.gateway import DataGateway
from src.utils.db import get_connection, init_db

logger = logging.getLogger(__name__)


_BASELINE_STRATEGY = {
    "name": "5d_momentum_v1",
    "description": (
        "Baseline: rank Tier A by trailing 5-day % return; pick top 10. "
        "Deliberately simple so Claude has room to improve it with "
        "catalysts, sector strength, oversold-bounce signals, etc."
    ),
    "config": {
        "ranking_signal": "change_5d",
        "lookback_days": 5,
        "universe_tier": "A",
        "min_history_days": 6,    # need at least 6 bars to compute change_5d
        "top_n": 10,
    },
}


# ── Strategy bootstrap + lookup ────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _ensure_baseline_strategy() -> int:
    """Create v1 baseline if no strategy exists. Return the active version."""
    init_db()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT version FROM prediction_strategies "
            "WHERE deactivated_at IS NULL ORDER BY version DESC LIMIT 1"
        ).fetchone()
        if row:
            return int(row["version"])
        now = _now_iso()
        cur = conn.execute(
            """
            INSERT INTO prediction_strategies
              (name, description, config_json, created_at, activated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                _BASELINE_STRATEGY["name"],
                _BASELINE_STRATEGY["description"],
                json.dumps(_BASELINE_STRATEGY["config"]),
                now, now,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def get_active_strategy() -> dict:
    """Return the currently-active strategy row + parsed config.

    Bootstraps the baseline on first call.
    """
    _ensure_baseline_strategy()
    init_db()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT version, name, description, config_json, created_at, "
            "       activated_at "
            "FROM prediction_strategies "
            "WHERE deactivated_at IS NULL "
            "ORDER BY version DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise RuntimeError("predictions: no active strategy after bootstrap")
    try:
        config = json.loads(row["config_json"])
    except Exception:
        config = {}
    return {
        "version":      int(row["version"]),
        "name":         row["name"],
        "description":  row["description"],
        "config":       config,
        "created_at":   row["created_at"],
        "activated_at": row["activated_at"],
    }


# ── Universe + signal scoring ──────────────────────────────────────────


def _load_universe(tier: str) -> list[str]:
    """Return list of symbols for a tier."""
    init_db()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT symbol FROM stocks_universe WHERE tier = ? ORDER BY symbol",
            (tier,),
        ).fetchall()
    finally:
        conn.close()
    return [r["symbol"] for r in rows]


def _score_one(symbol: str, *, lookback_days: int, min_history_days: int) -> dict | None:
    """Compute one symbol's score under the baseline (5d momentum) strategy.

    Returns {symbol, score, reasoning} or None if data is missing.
    All historical bars must be AT OR BEFORE today — no current-day
    intraday bars allowed (point-in-time guarantee).
    """
    try:
        gw = DataGateway()
        df = gw.get_historical(symbol, period_days=min_history_days + 30)
    except Exception as e:
        logger.info("predictions: get_historical failed for %s: %r", symbol, e)
        return None
    if df is None or len(df) < min_history_days:
        return None
    # Use only completed bars. The last row of df is the most recent
    # COMPLETED daily bar — get_historical never returns intraday data.
    try:
        close = df["Close"] if "Close" in df.columns else df["close"]
        latest = float(close.iloc[-1])
        prior = float(close.iloc[-1 - lookback_days])
    except Exception:
        return None
    if prior <= 0:
        return None
    change_pct = ((latest - prior) / prior) * 100.0
    return {
        "symbol":    symbol,
        "score":     change_pct,
        "reasoning": (
            f"+{change_pct:.1f}% over {lookback_days}d momentum"
            if change_pct >= 0
            else f"{change_pct:.1f}% over {lookback_days}d (mean-reversion candidate)"
        ),
    }


def _rank_universe(symbols: list[str], config: dict) -> list[dict]:
    """Score every symbol in parallel and return top N by score desc."""
    lookback = int(config.get("lookback_days", 5))
    min_hist = int(config.get("min_history_days", 6))
    top_n = int(config.get("top_n", 10))

    # 16 workers is plenty for ~150 Tier A symbols and respects rate limits.
    scored: list[dict] = []
    with ThreadPoolExecutor(max_workers=16) as pool:
        for result in pool.map(
            lambda s: _score_one(s, lookback_days=lookback, min_history_days=min_hist),
            symbols,
        ):
            if result is not None:
                scored.append(result)
    scored.sort(key=lambda r: r["score"], reverse=True)
    return scored[:top_n]


# ── Public API ─────────────────────────────────────────────────────────


def generate_predictions_for_date(date: str, *, force: bool = False) -> dict:
    """Generate (or retrieve) top-10 predictions for `date` (YYYY-MM-DD).

    Idempotent: returns the already-stored rows if predictions exist for
    this date, unless `force=True`. Predictions are immutable once stored
    — re-running with the same date and strategy returns whatever is in
    the table, preserving the historical accuracy record.

    The `date` parameter is the day the predictions WILL BE MEASURED, not
    the day they were created. Caller is responsible for passing the
    correct date (typically "today" if called pre-market).
    """
    init_db()

    if not force:
        existing = get_predictions_for_date(date)
        if existing["picks"]:
            return existing

    strategy = get_active_strategy()
    config = strategy["config"]
    tier = config.get("universe_tier", "A")
    symbols = _load_universe(tier)
    if not symbols:
        # Defensive: no Tier A loaded yet. Don't crash; return empty.
        logger.warning("predictions: no symbols in Tier %s — universe needs seeding", tier)
        return {
            "date": date,
            "strategy_version": strategy["version"],
            "strategy_name":    strategy["name"],
            "picks":            [],
            "universe_size":    0,
        }

    top = _rank_universe(symbols, config)
    now = _now_iso()

    conn = get_connection()
    try:
        # Replace any prior rows for this date — safe because predictions
        # are owned by (date, rank) and the new run is for the same date.
        conn.execute("DELETE FROM daily_predictions WHERE prediction_date = ?", (date,))
        for rank, row in enumerate(top, start=1):
            conn.execute(
                """
                INSERT INTO daily_predictions
                  (prediction_date, rank, symbol, score, reasoning,
                   strategy_version, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    date, rank, row["symbol"], row["score"],
                    row["reasoning"], strategy["version"], now,
                ),
            )
        conn.commit()
    finally:
        conn.close()

    return {
        "date":              date,
        "strategy_version":  strategy["version"],
        "strategy_name":     strategy["name"],
        "picks":             [
            {**row, "rank": i, "strategy_version": strategy["version"]}
            for i, row in enumerate(top, start=1)
        ],
        "universe_size":     len(symbols),
    }


def get_predictions_for_date(date: str) -> dict:
    """Read-only fetch of predictions for a date. Empty list if none."""
    init_db()
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT rank, symbol, score, reasoning, strategy_version, created_at
              FROM daily_predictions
             WHERE prediction_date = ?
             ORDER BY rank
            """,
            (date,),
        ).fetchall()
        # Lookup strategy name for the rows we have. All picks for a date
        # use the same strategy (we replace them as a set).
        strategy_version = rows[0]["strategy_version"] if rows else None
        strategy_name: str | None = None
        if strategy_version is not None:
            srow = conn.execute(
                "SELECT name FROM prediction_strategies WHERE version = ?",
                (strategy_version,),
            ).fetchone()
            strategy_name = srow["name"] if srow else None
    finally:
        conn.close()
    return {
        "date":             date,
        "strategy_version": strategy_version,
        "strategy_name":    strategy_name,
        "picks":            [dict(r) for r in rows],
    }


def get_predictions_today() -> dict:
    """Convenience: predictions for today's UTC date.

    If none exist yet (pre-market hasn't run the scheduler), generates
    them inline. Caller pays the wall-clock cost of scoring the universe
    on first call of the day.
    """
    today = datetime.now(tz=timezone.utc).date().isoformat()
    return generate_predictions_for_date(today)
