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


# ── Actuals + accuracy (Phase 2) ─────────────────────────────────────────


def _eod_change_pct(symbol: str, date: str) -> tuple[float | None, float | None, float | None]:
    """Open / close / change_pct for `symbol` on `date`.

    Returns (open, close, change_pct) or (None, None, None) on any miss.
    Used by `record_actuals_for_date` AFTER market close — calling it
    earlier in the day yields incomplete data and the row gets stamped
    with None values.
    """
    try:
        gw = DataGateway()
        # 90 days of history gives us plenty of buffer to find `date`.
        df = gw.get_historical(symbol, period_days=90)
    except Exception as e:
        logger.info("predictions: get_historical failed for %s: %r", symbol, e)
        return None, None, None
    if df is None or len(df) == 0:
        return None, None, None

    # The DataFrame index is a DatetimeIndex; match the date.
    try:
        target_rows = df[df.index.astype(str).str.startswith(date)]
    except Exception:
        return None, None, None
    if len(target_rows) == 0:
        return None, None, None
    row = target_rows.iloc[-1]
    try:
        open_ = float(row["Open"] if "Open" in row.index else row["open"])
        close = float(row["Close"] if "Close" in row.index else row["close"])
    except Exception:
        return None, None, None
    if open_ <= 0:
        return None, None, None
    return open_, close, ((close - open_) / open_) * 100.0


def record_actuals_for_date(date: str) -> dict:
    """Record open/close/change_pct for every symbol predicted on `date`,
    plus the actual universe ranks (for hit/miss computation).

    Idempotent — re-running for the same date overwrites the rows so a
    later EOD fetch (when more bars are settled) supersedes an earlier one.

    POINT-IN-TIME GUARANTEE: only call AFTER market close for `date`. The
    helper does not check this — caller (scheduler / manual route) must.
    """
    init_db()

    # 1. Pull the predictions for this date.
    preds = get_predictions_for_date(date)
    if not preds["picks"]:
        return {"date": date, "recorded": 0, "reason": "no_predictions"}

    # 2. Score the FULL Tier A universe for the same date so we know
    #    where each predicted pick ranked among actual winners.
    universe = _load_universe("A")
    universe_changes: dict[str, float] = {}
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = pool.map(
            lambda s: (s, _eod_change_pct(s, date)),
            universe,
        )
        for sym, (_o, _c, change) in results:
            if change is not None:
                universe_changes[sym] = change

    # Rank universe by change desc; symbol → rank (1-based).
    sorted_universe = sorted(universe_changes.items(), key=lambda kv: kv[1], reverse=True)
    rank_by_sym = {sym: i + 1 for i, (sym, _) in enumerate(sorted_universe)}
    universe_size = len(rank_by_sym)

    # 3. Persist actuals row per predicted pick.
    now = _now_iso()
    conn = get_connection()
    recorded = 0
    try:
        for pick in preds["picks"]:
            sym = pick["symbol"]
            # If we scored the symbol while ranking the universe, reuse
            # the change directly. Otherwise it's missing data — None values.
            if sym in universe_changes:
                # Re-derive open/close from the freshly-fetched bar so the
                # row has the exact prices the universe rank used.
                open_, close, change = _eod_change_pct(sym, date)
            else:
                open_, close, change = None, None, None
            rank = rank_by_sym.get(sym)
            conn.execute(
                """
                INSERT OR REPLACE INTO daily_prediction_actuals
                  (prediction_date, symbol, open_price, close_price,
                   change_pct, universe_rank, universe_size, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (date, sym, open_, close, change, rank, universe_size, now),
            )
            recorded += 1
        conn.commit()
    finally:
        conn.close()

    return {
        "date":          date,
        "recorded":      recorded,
        "universe_size": universe_size,
    }


def get_accuracy_window(*, window_days: int = 30, hit_threshold: int = 25) -> dict:
    """Rolling accuracy over the last `window_days` of COMPLETED predictions.

    "Completed" = prediction has a matching actuals row. In-flight days
    (today, weekend predictions where market hasn't closed) are excluded.

    Hit definition: a predicted symbol "hit" if its actual rank in the
    scored universe for that day was <= `hit_threshold`.

    Returns:
      {
        "window_days":       30,
        "hit_threshold":     25,
        "days_evaluated":    N,
        "predictions_total": N * 10,
        "hits":              count of picks with universe_rank <= 25,
        "hit_rate":          hits / predictions_total,
        "by_strategy":       {version: {predictions, hits, hit_rate}}
      }
    """
    init_db()
    conn = get_connection()
    try:
        rows = conn.execute(
            f"""
            SELECT dp.prediction_date     AS date,
                   dp.symbol              AS symbol,
                   dp.strategy_version    AS strategy_version,
                   dpa.universe_rank      AS universe_rank,
                   dpa.universe_size      AS universe_size,
                   dpa.change_pct         AS change_pct
              FROM daily_predictions dp
              JOIN daily_prediction_actuals dpa
                ON dp.prediction_date = dpa.prediction_date
               AND dp.symbol = dpa.symbol
             WHERE dpa.universe_rank IS NOT NULL
             ORDER BY dp.prediction_date DESC, dp.rank
             LIMIT ?
            """,
            (window_days * 10,),
        ).fetchall()
    finally:
        conn.close()

    total = len(rows)
    hits = sum(1 for r in rows if r["universe_rank"] and r["universe_rank"] <= hit_threshold)
    days_evaluated = len({r["date"] for r in rows})

    # Per-strategy breakdown
    by_strategy: dict[int, dict[str, Any]] = {}
    for r in rows:
        v = r["strategy_version"]
        if v not in by_strategy:
            by_strategy[v] = {"predictions": 0, "hits": 0}
        by_strategy[v]["predictions"] += 1
        if r["universe_rank"] and r["universe_rank"] <= hit_threshold:
            by_strategy[v]["hits"] += 1
    for v, b in by_strategy.items():
        b["hit_rate"] = b["hits"] / b["predictions"] if b["predictions"] else 0.0

    return {
        "window_days":       window_days,
        "hit_threshold":     hit_threshold,
        "days_evaluated":    days_evaluated,
        "predictions_total": total,
        "hits":              hits,
        "hit_rate":          (hits / total) if total else 0.0,
        "by_strategy":       by_strategy,
    }


def get_predictions_with_actuals(date: str) -> dict:
    """Return predictions for a date enriched with actuals (when present).

    Used by the UI to show "yesterday's predictions and how they did".
    Picks without an actuals row get None values — the UI can show "TBD".
    """
    preds = get_predictions_for_date(date)
    if not preds["picks"]:
        return preds

    init_db()
    conn = get_connection()
    try:
        actuals = {
            r["symbol"]: dict(r)
            for r in conn.execute(
                """
                SELECT symbol, open_price, close_price, change_pct,
                       universe_rank, universe_size, recorded_at
                  FROM daily_prediction_actuals
                 WHERE prediction_date = ?
                """,
                (date,),
            ).fetchall()
        }
    finally:
        conn.close()

    enriched = []
    for pick in preds["picks"]:
        a = actuals.get(pick["symbol"], {})
        enriched.append({
            **pick,
            "open_price":     a.get("open_price"),
            "close_price":    a.get("close_price"),
            "actual_change_pct": a.get("change_pct"),
            "universe_rank":  a.get("universe_rank"),
            "universe_size":  a.get("universe_size"),
            "actuals_recorded_at": a.get("recorded_at"),
        })
    return {
        **preds,
        "picks": enriched,
        "actuals_present": bool(actuals),
    }
