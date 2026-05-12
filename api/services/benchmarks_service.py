"""Benchmarks for the price chart — SPY + sector ETF spark, normalized to 100.

Lazily fetched separately from /deep-dive so the main report stays fast.
"""
from __future__ import annotations

from datetime import datetime

from src.utils.db import cache_get, cache_set
from api.constants import PERIOD_DAYS

_CACHE_TTL_MINUTES = 60

_SECTOR_ETF: dict[str, str] = {
    "Technology":             "XLK",
    "Healthcare":             "XLV",
    "Health Care":            "XLV",
    "Financials":             "XLF",
    "Financial Services":     "XLF",
    "Consumer Discretionary": "XLY",
    "Consumer Cyclical":      "XLY",
    "Consumer Staples":       "XLP",
    "Consumer Defensive":     "XLP",
    "Industrials":            "XLI",
    "Energy":                 "XLE",
    "Utilities":              "XLU",
    "Real Estate":            "XLRE",
    "Materials":              "XLB",
    "Basic Materials":        "XLB",
    "Communication Services": "XLC",
}


def _spark_for(symbol: str, days: int) -> list[dict]:
    """Return [{date: 'YYYY-MM-DD', close: float, idx: float}] normalized to 100."""
    try:
        import yfinance as yf
        period = "1mo" if days <= 30 else "3mo" if days <= 90 else "6mo" if days <= 180 else "1y" if days <= 366 else "2y"
        t = yf.Ticker(symbol)
        hist = t.history(period=period, auto_adjust=False)
        if hist is None or hist.empty:
            return []
        # Slice to last `days` rows for symmetry with the main chart
        hist = hist.tail(days + 5)
        first_close = float(hist["Close"].iloc[0])
        if first_close <= 0:
            return []
        out: list[dict] = []
        for d, row in hist.iterrows():
            close = float(row["Close"])
            out.append({
                "date":  d.strftime("%Y-%m-%d"),
                "close": round(close, 4),
                "idx":   round((close / first_close) * 100.0, 3),
            })
        return out
    except Exception:
        return []


def _detect_sector(symbol: str) -> str | None:
    try:
        import yfinance as yf
        info = yf.Ticker(symbol).info or {}
        return info.get("sector")
    except Exception:
        return None


def get_benchmarks(symbol: str, period: str = "3M", force: bool = False) -> dict:
    symbol = symbol.upper()
    period = period if period in PERIOD_DAYS else "3M"
    days = PERIOD_DAYS[period]

    cache_key = f"benchmarks:v1:{symbol}:{period}"
    if not force:
        cached = cache_get(cache_key)
        if cached:
            cached["from_cache"] = True
            return cached

    sector = _detect_sector(symbol)
    sector_etf = _SECTOR_ETF.get(sector) if sector else None

    spy_spark = _spark_for("SPY", days)
    sector_spark = _spark_for(sector_etf, days) if sector_etf else []

    payload = {
        "symbol":        symbol,
        "period":        period,
        "sector":        sector,
        "sector_etf":    sector_etf,
        "spy_spark":     spy_spark,
        "sector_spark":  sector_spark,
        "last_updated":  datetime.utcnow().isoformat() + "Z",
        "from_cache":    False,
    }

    try:
        cache_set(cache_key, payload, ttl_minutes=_CACHE_TTL_MINUTES)
    except Exception:
        pass
    return payload
