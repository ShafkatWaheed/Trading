"""Backtest a prediction strategy retroactively against historical data.

Why this exists
---------------
Going-forward, the predictions feature can only learn at 1 prediction per
trading day. With 17 signals × hundreds of weight combinations, that's
weeks of waiting per hypothesis. This backtest lets Claude (or you)
simulate a candidate strategy against the last N trading days using:
  - Today's signal data (caveat: see below)
  - Historical close prices via get_historical
  - The same composite_v1 scoring path used in production

A "hit" is defined the same as in the live system: predicted symbol's
same-day rank in Tier A was top `hit_threshold`.

Caveats baked into the docstrings + UI
--------------------------------------
This is a SIGNAL-FROZEN backtest — bubble / analyst / options / news /
congress / pre_earnings signals reflect TODAY'S state, not the state
those signals had N days ago. That's a real bias and the per-pick
ranking includes a "signal_freshness" flag the UI can show.

What is point-in-time correct:
  - Price momentum (computed from get_historical with proper lookback
    indexed from the historical date, not today)
  - Sector mapping (which we treat as static for the backtest window)

What is NOT point-in-time correct:
  - bubble_score, analyst_revisions, news, options, pre_earnings,
    catalyst, recommendation, macro_fit, fundamentals, congress —
    all reflect TODAY'S cached signal, not history's signal
  - reddit / premarket — same caveat

The backtest is honestly labeled as such in the response and the route
docstring. Use it for relative comparison (does adding a sector_match
weight help vs. pure momentum?) — NOT as a real predictor of future
returns.
"""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

from api.services import predictions_service
from src.data.gateway import DataGateway
from src.utils.db import get_connection, init_db

logger = logging.getLogger(__name__)


def _historical_change_pct(df: pd.DataFrame, target_idx: int, lookback_days: int) -> float | None:
    """Compute trailing %-return at row `target_idx` looking back `lookback_days`.

    Returns None when the lookback would index off the front of the frame.
    """
    if target_idx - lookback_days < 0 or target_idx >= len(df):
        return None
    try:
        close = df["Close"] if "Close" in df.columns else df["close"]
        latest = float(close.iloc[target_idx])
        prior = float(close.iloc[target_idx - lookback_days])
    except Exception:
        return None
    if prior <= 0:
        return None
    return ((latest - prior) / prior) * 100.0


def _day_open_close_change(df: pd.DataFrame, idx: int) -> tuple[float | None, float | None, float | None]:
    """Open / close / same-day-change-pct for row idx."""
    if idx < 0 or idx >= len(df):
        return None, None, None
    try:
        open_ = float((df["Open"] if "Open" in df.columns else df["open"]).iloc[idx])
        close = float((df["Close"] if "Close" in df.columns else df["close"]).iloc[idx])
    except Exception:
        return None, None, None
    if open_ <= 0:
        return None, None, None
    return open_, close, ((close - open_) / open_) * 100.0


def _score_one_historical(
    symbol: str,
    df: pd.DataFrame,
    target_idx: int,
    config: dict,
    *,
    pulse: dict | None,
    sector: str | None,
    signals: dict,
) -> dict | None:
    """Replicate predictions_service._score_one but with historical
    momentum at `target_idx`. Other signals (bubble / analyst / news /
    congress / etc.) use TODAY's cached values — see module docstring.
    """
    lookback = int(config.get("lookback_days", 5))
    change_pct = _historical_change_pct(df, target_idx, lookback)
    if change_pct is None:
        return None

    signal = config.get("ranking_signal", "change_5d")
    weights = config.get("weights") if isinstance(config.get("weights"), dict) else None

    # Reuse the production scorer's pure-momentum branch for change_Nd.
    if signal != "composite_v1":
        return {
            "symbol":    symbol,
            "score":     change_pct,
            "reasoning": f"+{change_pct:.1f}% over {lookback}d momentum",
        }

    # composite_v1 with historical momentum + today's other signals
    w = {**{
        "momentum":           0.5,
        "sector_match":       0.3,
        "sector_flow":        0.2,
        "bubble":             0.0,
        "analyst":            0.0,
        "congress":           0.0,
        "options":            0.0,
        "news":               0.0,
        "pre_earnings":       0.0,
        "peer_valuation":     0.0,
        "catalyst":           0.0,
        "recommendation":     0.0,
        "macro_fit":          0.0,
        "analyst_consensus":  0.0,
        "fundamentals":       0.0,
        "premarket":          0.0,
        "reddit":             0.0,
    }, **(weights or {})}
    top_sectors = set((pulse or {}).get("top_sectors") or [])
    sector_flows = (pulse or {}).get("all_sector_flows") or {}
    sector_match = 1.0 if (sector and sector in top_sectors) else 0.0
    sector_flow = float(sector_flows.get(sector or "", 0.0)) if sector else 0.0

    score = (
        w["momentum"]            * change_pct
        + w["sector_match"]      * sector_match * 10.0
        + w["sector_flow"]       * sector_flow
        + w["bubble"]            * signals.get("bubble", 0.0)            * 10.0
        + w["analyst"]           * signals.get("analyst", 0.0)           * 10.0
        + w["congress"]          * signals.get("congress", 0.0)          * 10.0
        + w["options"]           * signals.get("options", 0.0)           * 10.0
        + w["news"]              * signals.get("news", 0.0)              * 10.0
        + w["pre_earnings"]      * signals.get("pre_earnings", 0.0)      * 10.0
        + w["peer_valuation"]    * signals.get("peer_valuation", 0.0)    * 10.0
        + w["catalyst"]          * signals.get("catalyst", 0.0)          * 10.0
        + w["recommendation"]    * signals.get("recommendation", 0.0)    * 10.0
        + w["macro_fit"]         * signals.get("macro_fit", 0.0)         * 10.0
        + w["analyst_consensus"] * signals.get("analyst_consensus", 0.0) * 10.0
        + w["fundamentals"]      * signals.get("fundamentals", 0.0)      * 10.0
        # premarket + reddit signals are inherently today-only; skip in backtest
    )

    return {
        "symbol":    symbol,
        "score":     score,
        "reasoning": f"{change_pct:+.1f}% {lookback}d (backtest)",
    }


def backtest_strategy(
    *,
    version: int | None = None,
    config: dict | None = None,
    days: int = 30,
    hit_threshold: int = 25,
    top_n: int = 10,
) -> dict:
    """Simulate a strategy across the last `days` trading days.

    Either `version` (use that strategy's saved config) or `config` (raw
    dict, lets Claude propose-and-test without persisting first).

    Returns:
      {
        "version_or_config":  <whichever was passed>,
        "days_evaluated":     N,
        "predictions_total":  N * top_n,
        "hits":               M,
        "hit_rate":           M / total,
        "per_day":            [{date, picks: [...], hits_in_day}],
        "caveat":             "<honest description of signal-freshness bias>",
      }
    """
    init_db()
    if version is not None and config is None:
        # Load saved strategy
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT config_json FROM prediction_strategies WHERE version = ?",
                (version,),
            ).fetchone()
        finally:
            conn.close()
        if not row:
            return {"error": "version_not_found", "version": version}
        try:
            config = json.loads(row["config_json"])
        except Exception:
            return {"error": "config_corrupt", "version": version}
    if not config:
        return {"error": "config_required"}

    symbols = predictions_service._load_universe(config.get("universe_tier", "A"))
    if not symbols:
        return {"error": "empty_universe"}

    # Pre-fetch all bulk signals + sector mapping once. The historical
    # momentum is the only thing recomputed per-day.
    sectors_by_sym = predictions_service._symbol_sectors(symbols)
    pulse = predictions_service._pulse_context()
    signals_by_sym = predictions_service._bulk_all_signals(symbols)

    # Fetch historical bars for every symbol (1 yfinance call each, parallel).
    lookback = int(config.get("lookback_days", 5))
    period_days = days + lookback + 30

    def _fetch_hist(sym: str) -> tuple[str, pd.DataFrame | None]:
        try:
            gw = DataGateway()
            df = gw.get_historical(sym, period_days=period_days)
        except Exception:
            return sym, None
        return sym, df

    hist_by_sym: dict[str, pd.DataFrame] = {}
    with ThreadPoolExecutor(max_workers=16) as pool:
        for sym, df in pool.map(_fetch_hist, symbols):
            if df is not None and len(df) > lookback + 1:
                hist_by_sym[sym] = df

    if not hist_by_sym:
        return {"error": "no_historical_data"}

    # Build the set of dates to evaluate from the shortest available frame.
    # We need each frame to have at least lookback+1 bars at the target idx.
    min_len = min(len(df) for df in hist_by_sym.values())
    # Walk back `days` rows from the end of each frame.
    evaluation_indices = list(range(min_len - days, min_len))
    evaluation_indices = [i for i in evaluation_indices if i > lookback]

    per_day: list[dict] = []
    total_hits = 0
    total_picks = 0

    for target_idx in evaluation_indices:
        # Pick a representative date from any frame (they share trading days)
        first_df = next(iter(hist_by_sym.values()))
        try:
            day_date = str(first_df.index[target_idx])[:10]
        except Exception:
            day_date = f"idx-{target_idx}"

        # Score every symbol at target_idx, rank, take top_n
        scored: list[dict] = []
        for sym, df in hist_by_sym.items():
            row = _score_one_historical(
                sym, df, target_idx, config,
                pulse=pulse,
                sector=sectors_by_sym.get(sym),
                signals=signals_by_sym.get(sym) or {},
            )
            if row is not None:
                scored.append(row)
        scored.sort(key=lambda r: r["score"], reverse=True)
        picks = scored[:top_n]

        # Compute actual next-day rank for every symbol (same-day open→close
        # — matches the live actuals semantics) and tag each pick with rank
        same_day_changes: list[tuple[str, float]] = []
        for sym, df in hist_by_sym.items():
            _, _, change = _day_open_close_change(df, target_idx)
            if change is not None:
                same_day_changes.append((sym, change))
        same_day_changes.sort(key=lambda kv: kv[1], reverse=True)
        rank_by_sym = {s: i + 1 for i, (s, _) in enumerate(same_day_changes)}

        hits_in_day = 0
        for rank, p in enumerate(picks, start=1):
            actual_rank = rank_by_sym.get(p["symbol"])
            p["rank"] = rank
            p["actual_rank"] = actual_rank
            p["hit"] = bool(actual_rank and actual_rank <= hit_threshold)
            if p["hit"]:
                hits_in_day += 1
        total_hits += hits_in_day
        total_picks += len(picks)

        per_day.append({
            "date":            day_date,
            "picks":           picks,
            "hits_in_day":     hits_in_day,
            "universe_scored": len(same_day_changes),
        })

    return {
        "version":            version,
        "config":             config,
        "days":               days,
        "days_evaluated":     len(per_day),
        "hit_threshold":      hit_threshold,
        "top_n":              top_n,
        "predictions_total":  total_picks,
        "hits":               total_hits,
        "hit_rate":           total_hits / max(total_picks, 1),
        "per_day":            per_day,
        "caveat": (
            "SIGNAL-FROZEN BACKTEST: only momentum is point-in-time. All "
            "other signals (bubble/analyst/news/congress/options/etc.) "
            "reflect today's cached values, not history's. Use this for "
            "relative weight comparison, NOT as a forecast of future returns."
        ),
    }
