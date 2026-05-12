"""Wall Street analyst consensus from yfinance — ratings + price targets."""
from __future__ import annotations

from datetime import datetime

from src.utils.db import cache_get, cache_set

_CACHE_TTL_MINUTES = 12 * 60


def _safe_float(v) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _safe_int(v) -> int | None:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def get_analyst_consensus(symbol: str, force: bool = False) -> dict:
    symbol = symbol.upper()
    cache_key = f"analyst_consensus:v1:{symbol}"
    if not force:
        cached = cache_get(cache_key)
        if cached:
            cached["from_cache"] = True
            return cached

    out: dict = {
        "symbol": symbol,
        "rating": None,                 # e.g., "buy" / "hold" / "sell" / "strong_buy"
        "rating_mean": None,            # 1.0 strong buy → 5.0 strong sell
        "analyst_count": None,
        "current_price": None,
        "target_mean": None,
        "target_high": None,
        "target_low": None,
        "upside_pct": None,             # (target_mean - current) / current * 100
        "ratings_breakdown": {
            "strong_buy": 0, "buy": 0, "hold": 0, "sell": 0, "strong_sell": 0,
        },
        "from_cache": False,
        "last_updated": datetime.utcnow().isoformat() + "Z",
    }

    try:
        import yfinance as yf
        t = yf.Ticker(symbol)
        info = t.info or {}

        out["rating"] = info.get("recommendationKey")
        out["rating_mean"] = _safe_float(info.get("recommendationMean"))
        out["analyst_count"] = _safe_int(info.get("numberOfAnalystOpinions"))
        out["current_price"] = _safe_float(info.get("currentPrice"))
        out["target_mean"] = _safe_float(info.get("targetMeanPrice"))
        out["target_high"] = _safe_float(info.get("targetHighPrice"))
        out["target_low"] = _safe_float(info.get("targetLowPrice"))

        if out["current_price"] and out["target_mean"]:
            out["upside_pct"] = round(((out["target_mean"] - out["current_price"]) / out["current_price"]) * 100, 1)

        try:
            recs = t.recommendations
            if recs is not None and len(recs) > 0:
                # First row = current month
                row = recs.iloc[0]
                out["ratings_breakdown"] = {
                    "strong_buy":  _safe_int(row.get("strongBuy")) or 0,
                    "buy":         _safe_int(row.get("buy")) or 0,
                    "hold":        _safe_int(row.get("hold")) or 0,
                    "sell":        _safe_int(row.get("sell")) or 0,
                    "strong_sell": _safe_int(row.get("strongSell")) or 0,
                }
        except Exception:
            pass
    except Exception as e:
        out["error"] = f"Failed to fetch analyst data: {e}"

    try:
        cache_set(cache_key, out, ttl_minutes=_CACHE_TTL_MINUTES)
    except Exception:
        pass
    return out
