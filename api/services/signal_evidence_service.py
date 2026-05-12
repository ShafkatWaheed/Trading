"""Per-signal empirical evidence — backtest each currently-active signal on
this stock and return win rate + avg return so users see "RSI 78 + last time
this fired, win rate was 67% over 30d" instead of just "RSI is overbought".

Cached 24h since the underlying historical data only changes daily.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from src.utils.db import cache_get, cache_set
from api.services import deep_dive_service

_CACHE_TTL_MINUTES = 24 * 60
_HOLD_DAYS = 30
_MAX_PARALLEL = 4
# Cap how many signals we backtest per request to keep latency sane.
# Active signals (not neutral) are prioritized; cap so a 30-signal payload
# doesn't make this tab take 30s on first hit.
_MAX_SIGNALS = 14


def _backtest_one(symbol: str, signal_name: str) -> dict:
    """Run a single backtest for one signal on this stock. Returns
    {win_rate, avg_return_pct, total_trades, max_gain_pct, max_loss_pct}
    or {error: ...} if the signal can't be backtested.
    """
    try:
        from src.analysis.backtester import backtest_signal, SIGNALS
        from src.data.gateway import DataGateway

        if signal_name not in SIGNALS:
            return {"error": "unknown signal"}

        gw = DataGateway()
        hist = gw.get_historical(symbol, period_days=365 * 3)
        if hist is None or hist.empty or len(hist) < 60:
            return {"error": "not enough history"}

        result = backtest_signal(symbol, hist, signal_name, hold_days=_HOLD_DAYS)
        # backtester returns: win_rate as decimal 0..1, avg_return / max_gain / max_loss
        # already as percent values (5.1 = 5.1%, not 510%).
        return {
            "win_rate":       round(float(result.win_rate), 3) if result.win_rate is not None else None,
            "avg_return_pct": round(float(result.avg_return), 1) if result.avg_return is not None else None,
            "total_trades":   int(result.total_trades) if result.total_trades is not None else 0,
            "max_gain_pct":   round(float(result.max_gain), 1) if result.max_gain is not None else None,
            "max_loss_pct":   round(float(result.max_loss), 1) if result.max_loss is not None else None,
            "hold_days":      _HOLD_DAYS,
        }
    except Exception as e:
        return {"error": str(e)[:120]}


def _grade(win_rate: float | None, avg_return: float | None, trades: int) -> str:
    """A simple grade for a signal's track record on this stock."""
    if not win_rate or not avg_return or trades < 3:
        return "n/a"
    score = win_rate * (1 + max(0.0, avg_return) / 5.0)
    if win_rate >= 0.7 and avg_return >= 3:    return "A"
    if win_rate >= 0.6 and avg_return >= 2:    return "B"
    if win_rate >= 0.5 and avg_return >= 0:    return "C"
    if win_rate >= 0.4:                        return "D"
    return "F"


def _signal_key(s: dict) -> str:
    """Map a deep-dive signal row to a backtester signal name. Best-effort."""
    name = (s.get("name") or "").lower().replace(" ", "_").replace("/", "_")
    return name


# Map deep-dive section names → representative backtest signal name.
# When a section is bullish vs bearish we pick the matching directional signal
# so the win-rate reflects the appropriate side of the catalog.
_SECTION_TO_SIGNAL: dict[str, dict[str, str]] = {
    "technical analysis":   {"bullish": "rsi_oversold",     "bearish": "rsi_overbought"},
    "fundamental analysis": {"bullish": "earnings_beat",    "bearish": "earnings_miss"},
    "macro environment":    {"bullish": "vix_low",          "bearish": "vix_high"},
    "smart money":          {"bullish": "insider_cluster_buy", "bearish": "insider_cluster_sell"},
    "smart money (insider + institutional)": {"bullish": "insider_cluster_buy", "bearish": "insider_cluster_sell"},
    "congressional trades": {"bullish": "congress_buy_cluster", "bearish": "congress_sell_cluster"},
    "analyst ratings":      {"bullish": "analyst_upgrade",  "bearish": "analyst_downgrade"},
    "options flow":         {"bullish": "unusual_call_activity", "bearish": "unusual_put_activity"},
    "sector rotation":      {"bullish": "sector_rotation",  "bearish": "sector_rotation"},
    "geopolitical risk":    {"bullish": "geopolitical_calm", "bearish": "geopolitical_shock"},
    "disruption":           {"bullish": "disruption_winner", "bearish": "disruption_loser"},
    "news sentiment":       {"bullish": "news_positive_burst", "bearish": "news_negative_burst"},
}


def get_signal_evidence(symbol: str, force: bool = False) -> dict:
    """Return per-signal historical backtest stats for currently-active signals."""
    symbol = symbol.upper()
    cache_key = f"signal_evidence:v1:{symbol}"

    if not force:
        cached = cache_get(cache_key)
        if cached:
            cached["from_cache"] = True
            return cached

    dd = deep_dive_service.get_deep_dive(symbol, period="3M")
    if not dd:
        return {"symbol": symbol, "evidence": {}, "error": "No deep-dive context."}

    # Pick currently-active (non-neutral) signals first, fall back to all
    raw = dd.get("signals") or []
    active = [s for s in raw if s.get("direction") in ("bullish", "bearish")]
    pool = (active + [s for s in raw if s not in active])[:_MAX_SIGNALS]

    # Resolve each signal's name → SIGNALS catalog key
    from src.analysis.backtester import SIGNALS
    catalog = set(SIGNALS.keys())

    # Build (display_name, catalog_key) pairs, keep only those we can backtest
    jobs: list[tuple[str, str]] = []
    for s in pool:
        display = s.get("name") or ""
        direction = (s.get("direction") or "neutral").lower()

        # Try direct name normalization first
        candidates = [
            display.lower().replace(" ", "_"),
            display.lower().replace(" ", "_").replace("-", "_"),
            display.lower().replace(" ", "").replace("-", "_"),
        ]
        match = next((c for c in candidates if c in catalog), None)

        # Then fall back to section→signal mapping
        if not match:
            section_map = _SECTION_TO_SIGNAL.get(display.lower())
            if section_map:
                key_for_dir = section_map.get(direction) or section_map.get("bullish")
                if key_for_dir and key_for_dir in catalog:
                    match = key_for_dir

        if match:
            jobs.append((display, match))

    def _run(job):
        display, key = job
        return display, key, _backtest_one(symbol, key)

    evidence: dict[str, dict] = {}
    if jobs:
        with ThreadPoolExecutor(max_workers=_MAX_PARALLEL) as pool_ex:
            for display, key, stats in pool_ex.map(_run, jobs):
                if stats.get("error"):
                    evidence[display] = {"signal_key": key, "error": stats["error"]}
                else:
                    evidence[display] = {
                        "signal_key":      key,
                        "win_rate":        stats["win_rate"],
                        "avg_return_pct":  stats["avg_return_pct"],
                        "total_trades":    stats["total_trades"],
                        "max_gain_pct":    stats["max_gain_pct"],
                        "max_loss_pct":    stats["max_loss_pct"],
                        "hold_days":       stats["hold_days"],
                        "grade":           _grade(stats["win_rate"], stats["avg_return_pct"], stats["total_trades"]),
                    }

    payload = {
        "symbol":         symbol,
        "hold_days":      _HOLD_DAYS,
        "signals_tested": len(jobs),
        "signals_total":  len(raw),
        "evidence":       evidence,
        "last_updated":   datetime.utcnow().isoformat() + "Z",
        "from_cache":     False,
    }

    try:
        cache_set(cache_key, payload, ttl_minutes=_CACHE_TTL_MINUTES)
    except Exception:
        pass
    return payload
