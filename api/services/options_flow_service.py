"""Options flow service — put/call ratio, IV rank, unusual activity story.

Wraps src.data.polygon.PolygonProvider.get_options_summary() and runs it
through src.analysis.options_flow.analyze() to produce a short verdict +
the raw metrics the UI needs to tell the story.

Polygon requires POLYGON_API_KEY. If unset, returns available=false with a
clear reason — the UI renders an explainer instead of an empty card.
"""
from __future__ import annotations

from datetime import datetime

from src.analysis import options_flow as options_analysis
from src.utils.config import POLYGON_API_KEY
from src.utils.db import cache_get, cache_set

_CACHE_TTL_MINUTES = 30  # options data refreshes intraday


def _empty(symbol: str, reason: str) -> dict:
    return {
        "symbol": symbol,
        "available": False,
        "reason": reason,
        "signal": "neutral",
        "score": 0,
        "lede": None,
        "put_call_ratio": None,
        "iv_rank": None,
        "iv_avg_pct": None,
        "iv_percentile": None,
        "max_pain": None,
        "underlying_price": None,
        "total_call_volume": 0,
        "total_put_volume": 0,
        "put_call_interpretation": "",
        "iv_interpretation": "",
        "unusual_activity_note": "",
        "factors": [],
        "unusual_top": [],
        "data_source": None,
        "from_cache": False,
        "last_updated": datetime.utcnow().isoformat() + "Z",
    }


def _fetch_summary(symbol: str) -> tuple[object | None, str | None, str | None]:
    """Try Polygon first (richer data) then yfinance (free fallback).

    Returns (summary, data_source, error_reason). On success, error_reason
    is None. On full failure, summary is None and error_reason explains.
    """
    polygon_error: str | None = None
    if POLYGON_API_KEY:
        try:
            from src.data.polygon import PolygonProvider
            summary = PolygonProvider().get_options_summary(symbol)
            if summary is not None:
                return summary, "polygon", None
        except Exception as e:
            polygon_error = str(e)
            # Fall through to yfinance — never let Polygon failure block the card.

    try:
        from src.data import yf_options
        summary = yf_options.get_options_summary(symbol)
        if summary is not None:
            return summary, "yfinance", None
    except Exception as e:
        # Both sources failed — report the most actionable error.
        if polygon_error:
            return None, None, f"Polygon failed ({polygon_error[:80]}) and yfinance fallback also failed: {e}"
        return None, None, f"Options data unavailable: {e}"

    if polygon_error:
        return None, None, f"Polygon: {polygon_error[:140]}"
    return None, None, "No options data returned."


def _compose_lede(score: int, signal: str, pcr: float | None,
                   iv_rank: float | None, iv_avg_pct: float | None = None) -> str:
    """Synthesize a one-line options story from the score components.

    Prefers IV rank (richer signal — shows where current IV sits in historical
    range). Falls back to absolute IV percent when only yfinance data exists.
    """
    pcr_txt = f"P/C {pcr:.2f}" if pcr is not None else "P/C n/a"
    if iv_rank is not None:
        iv_txt = f"IV rank {iv_rank:.0f}%"
    elif iv_avg_pct is not None:
        iv_txt = f"IV ~{iv_avg_pct:.0f}%"
    else:
        iv_txt = "IV n/a"

    if signal == "bullish" and score >= 2:
        return f"Options market is leaning hard bullish — {pcr_txt}, {iv_txt}. Calls dominate."
    if signal == "bullish":
        return f"Options flow tilts bullish — {pcr_txt}, {iv_txt}."
    if signal == "bearish" and score <= -2:
        return f"Options market is loaded with downside protection — {pcr_txt}, {iv_txt}. Puts dominate."
    if signal == "bearish":
        return f"Options flow tilts bearish — {pcr_txt}, {iv_txt}."
    return f"Options market is balanced — {pcr_txt}, {iv_txt}. No clear directional bet."


def get_options_flow(symbol: str, force: bool = False) -> dict:
    symbol = symbol.upper()
    cache_key = f"options_flow:v1:{symbol}"
    if not force:
        cached = cache_get(cache_key)
        if cached:
            cached["from_cache"] = True
            return cached

    summary, data_source, error_reason = _fetch_summary(symbol)
    if summary is None:
        return _empty(symbol, error_reason or "Options data unavailable.")

    score = options_analysis.analyze(summary)

    def _f(v) -> float | None:
        return float(v) if v is not None else None

    unusual = []
    for u in (summary.unusual_activity or [])[:8]:
        unusual.append({
            "contract_type": u.contract_type,
            "strike": _f(u.strike),
            "expiration": u.expiration,
            "volume": u.volume,
            "open_interest": u.open_interest,
            "volume_oi_ratio": _f(u.volume_oi_ratio),
            "premium": _f(u.premium),
            "sentiment": u.sentiment,
        })

    pcr = _f(summary.put_call_ratio)
    iv_rank = _f(summary.iv_rank)
    # Absolute IV — always available from both sources; useful display fallback
    # when iv_rank is None (yfinance doesn't expose historical IV).
    avg_iv = _f(summary.avg_iv)
    iv_avg_pct = round(avg_iv * 100, 1) if avg_iv else None

    payload = {
        "symbol": symbol,
        "available": True,
        "reason": None,
        "signal": score.signal,
        "score": score.score,
        "lede": _compose_lede(score.score, score.signal, pcr, iv_rank, iv_avg_pct),
        "put_call_ratio": pcr,
        "iv_rank": iv_rank,
        "iv_avg_pct": iv_avg_pct,
        "iv_percentile": _f(summary.iv_percentile),
        "max_pain": _f(summary.max_pain),
        "underlying_price": _f(summary.underlying_price),
        "total_call_volume": summary.total_call_volume,
        "total_put_volume": summary.total_put_volume,
        "put_call_interpretation": score.put_call_interpretation,
        "iv_interpretation": score.iv_interpretation,
        "unusual_activity_note": score.unusual_activity_note,
        "factors": score.factors,
        "unusual_top": unusual,
        "data_source": data_source,
        "from_cache": False,
        "last_updated": datetime.utcnow().isoformat() + "Z",
    }

    try:
        cache_set(cache_key, payload, ttl_minutes=_CACHE_TTL_MINUTES)
    except Exception:
        pass
    return payload
