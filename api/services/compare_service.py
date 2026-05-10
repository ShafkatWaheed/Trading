"""Side-by-side comparison of several tickers.

Reuses the same orchestrator pipeline as Deep Dive but runs in parallel
across N symbols and returns compact rows.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from decimal import Decimal
from api.constants import PERIOD_DAYS as _PERIOD_DAYS
from src.utils.db import cache_get, cache_set


_CACHE_TTL_MINUTES = 24 * 60


def _row(symbol: str, period: str, force: bool = False) -> dict:
    """Build a compact comparison row for one symbol."""
    from src.orchestrator import analyze_stock
    from src.data.gateway import DataGateway

    cache_key = f"compare_row:v2:{symbol}:{period}"
    if not force:
        cached = cache_get(cache_key)
        if cached:
            cached["from_cache"] = True
            return cached

    try:
        report = analyze_stock(symbol, export=False, pdf=False)
    except Exception as e:
        return {"symbol": symbol, "error": f"Analysis failed: {e}"}

    # Risk + sentiment
    try:
        risk = int(getattr(report.risk_rating, "value", 3))
    except Exception:
        risk = 3
    try:
        s = report.sentiment_score
        sentiment = float(s) if isinstance(s, (int, float, Decimal)) else None
    except Exception:
        sentiment = None

    # Period change via gateway
    days = _PERIOD_DAYS.get(period, 21)
    last_price = None
    change_pct = None
    spark: list[dict] = []
    try:
        gw = DataGateway()
        hist = gw.get_historical(symbol, period_days=max(days + 5, 30))
        if hist is not None and not hist.empty:
            closes = hist["close"].astype(float)
            last_price = float(closes.iloc[-1])
            offset = min(days, len(closes) - 1)
            if offset > 0:
                start = float(closes.iloc[-1 - offset])
                change_pct = ((last_price - start) / start) * 100.0 if start else 0.0
                sub = hist.tail(offset + 1)
                spark = [
                    {"date": str(d), "close": float(c)}
                    for d, c in zip(sub["date"].tolist(), sub["close"].astype(float).tolist())
                ]
    except Exception:
        pass

    # Bullish/bearish tally
    bull, bear, total = 0, 0, 0
    BULL = ("buy", "bullish", "positive", "tailwind", "accumulating", "upgrade", "beneficiary")
    BEAR = ("sell", "bearish", "negative", "headwind", "downgrade", "at risk", "high risk")
    for s in (getattr(report, "sections", []) or []):
        title = (s.title or "").lower()
        if "overview" in title or "confluence" in title:
            continue
        cl = (s.content or "").lower()
        is_bull = any(w in cl for w in BULL)
        is_bear = any(w in cl for w in BEAR)
        if is_bull and not is_bear: bull += 1
        elif is_bear and not is_bull: bear += 1
        total += 1

    # Pull a couple of headline fundamentals via cache
    pe = None
    div_yield = None
    try:
        fund = cache_get(f"market:fundamentals:{symbol}") or {}
        pe = float(fund["pe_ratio"]) if fund.get("pe_ratio") is not None else None
        div_yield = float(fund["dividend_yield"]) if fund.get("dividend_yield") is not None else None
    except Exception:
        pass

    payload = {
        "symbol": symbol,
        "name": getattr(getattr(report, "stock", None), "name", None),
        "sector": getattr(getattr(report, "stock", None), "sector", None),
        "verdict": str(report.verdict.value),
        "confidence": str(report.confidence),
        "risk_rating": risk,
        "sentiment_score": sentiment,
        "price": last_price,
        "change_pct": change_pct,
        "spark": spark,
        "bullish_signals": bull,
        "bearish_signals": bear,
        "total_signals": total,
        "pe_ratio": pe,
        "dividend_yield": div_yield,
        "from_cache": False,
    }

    try:
        cache_set(cache_key, payload, ttl_minutes=_CACHE_TTL_MINUTES)
    except Exception:
        pass

    return payload


def compare(symbols: list[str], period: str = "3M", force: bool = False) -> dict:
    syms = [s.upper().strip() for s in symbols if s and s.strip()]
    syms = list(dict.fromkeys(syms))[:6]   # dedupe + cap at 6
    if period not in _PERIOD_DAYS:
        period = "3M"

    rows: list[dict] = []
    if syms:
        with ThreadPoolExecutor(max_workers=min(6, len(syms))) as pool:
            futures = {pool.submit(_row, s, period, force): s for s in syms}
            for fut in futures:
                try:
                    rows.append(fut.result(timeout=120))
                except Exception as e:
                    rows.append({"symbol": futures[fut], "error": str(e)})

    # Preserve input order
    order = {s: i for i, s in enumerate(syms)}
    rows.sort(key=lambda r: order.get(r["symbol"], 999))

    return {
        "rows": rows,
        "period": period,
        "available_periods": list(_PERIOD_DAYS.keys()),
        "last_updated": datetime.utcnow().isoformat() + "Z",
    }
