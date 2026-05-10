"""Deep Dive service: rich analysis payload for the dashboard.

Wraps `src/orchestrator.analyze_stock()` and shapes the result for the API:
- KPI grid (price, confidence, risk, sentiment)
- Period price change (1D / 1W / 1M / 3M / 6M / 1Y)
- Signal breakdown grouped by category
- Trade plan (entry / stop / target1 / target2 / sizing / alignment / risks / timing)
- Bullish vs bearish signal counts
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from api.constants import PERIOD_DAYS as _PERIOD_DAYS
from src.utils.db import cache_get, cache_set


# Time-to-live for the cached deep-dive payload. The user explicitly asked for
# 24h cache: anything within a day serves from disk; older requests recompute.
_CACHE_TTL_MINUTES = 24 * 60


# ── Signal section catalog (mirrors the original dashboard) ──────


SECTION_THEME = {
    "technical analysis":   {"icon": "📈", "color": "blue",   "category": "Technical Analysis",  "max": 2},
    "fundamental analysis": {"icon": "📊", "color": "violet", "category": "Fundamental Analysis", "max": 2},
    "news sentiment":       {"icon": "📰", "color": "cyan",   "category": "News Sentiment",       "max": 1},
    "macro environment":    {"icon": "🌍", "color": "amber",  "category": "Macro Environment",    "max": 2},
    "options flow":         {"icon": "⚡", "color": "pink",   "category": "Options Flow",         "max": 2},
    "smart money":          {"icon": "🏦", "color": "green",  "category": "Smart Money",          "max": 2},
    "congressional":        {"icon": "🏛", "color": "violet", "category": "Congressional Trades", "max": 1},
    "geopolitical":         {"icon": "🌐", "color": "amber",  "category": "Geopolitical Risk",    "max": 1},
    "disruptive":           {"icon": "🚀", "color": "violet", "category": "Disruptive Technology", "max": 1},
    "analyst":              {"icon": "🎯", "color": "blue",   "category": "Analyst Ratings",      "max": 1},
    "institutional":        {"icon": "🏛", "color": "green",  "category": "Institutional Holders", "max": 1},
    "community buzz":       {"icon": "🗣", "color": "pink",   "category": "Community Buzz",       "max": 1},
    "short interest":       {"icon": "📉", "color": "red",    "category": "Short Interest",       "max": 1},
    "job market":           {"icon": "💼", "color": "green",  "category": "Job Market Trend",     "max": 1},
    "overview":             {"icon": "ℹ",  "color": "neutral","category": "Overview",             "max": 0},
    "confluence":           {"icon": "🎯", "color": "blue",   "category": "Confluence",           "max": 0},
}


def _theme_for(title: str) -> dict:
    t = (title or "").lower()
    for key, theme in SECTION_THEME.items():
        if key in t:
            return theme
    return {"icon": "•", "color": "neutral", "category": title, "max": 1}


# ── Direction / strength heuristics ──────────────────────────────


_BULLISH = ("buy", "bullish", "positive", "tailwind", "accumulating", "upgrade",
            "strong buy", "beneficiary")
_BEARISH = ("sell", "bearish", "negative", "tighten", "distributing", "headwind",
            "downgrade", "at risk", "high risk")


def _direction_strength(content: str, data: dict | None) -> tuple[str, float]:
    if isinstance(data, dict):
        d = (data.get("direction") or "").lower()
        if d in ("bullish", "bearish", "neutral"):
            try:
                strength = float(data.get("strength", 0.6))
            except Exception:
                strength = 0.6
            return d, max(0.0, min(1.0, strength))

    cl = (content or "").lower()
    is_bull = any(w in cl for w in _BULLISH)
    is_bear = any(w in cl for w in _BEARISH)
    if is_bull and not is_bear:
        return "bullish", 0.7
    if is_bear and not is_bull:
        return "bearish", 0.7
    return "neutral", 0.4


def _to_signals(report) -> list[dict]:
    rows = []
    for section in getattr(report, "sections", []) or []:
        title = section.title or ""
        theme = _theme_for(title)
        if theme["category"] in ("Overview", "Confluence"):
            continue
        data = section.data if isinstance(getattr(section, "data", None), dict) else {}
        direction, strength = _direction_strength(section.content or "", data)
        rows.append({
            "name": title,
            "category": theme["category"],
            "icon": theme["icon"],
            "color": theme["color"],
            "direction": direction,
            "strength": strength,
            "explanation": section.content or "",
            "why": data.get("why"),
        })
    return rows


# ── Trade plan helpers ───────────────────────────────────────────


def _extract_levels(report) -> dict:
    out = {
        "support": None, "resistance": None, "sma_50": None,
        "week52_high": None, "week52_low": None,
    }
    for section in getattr(report, "sections", []) or []:
        d = section.data if isinstance(getattr(section, "data", None), dict) else {}
        title = (section.title or "").lower()
        try:
            if "technical" in title:
                if d.get("support"): out["support"] = float(d["support"])
                if d.get("resistance"): out["resistance"] = float(d["resistance"])
                if d.get("sma_50"): out["sma_50"] = float(d["sma_50"])
            if "overview" in title:
                if d.get("52w_high"): out["week52_high"] = float(d["52w_high"])
                if d.get("52w_low"): out["week52_low"] = float(d["52w_low"])
        except Exception:
            continue
    return out


def _trade_plan(report, price: float | None, account_size: float, risk_pct: float) -> dict | None:
    if price is None or price <= 0:
        return None

    levels = _extract_levels(report)
    support = levels["support"]
    resistance = levels["resistance"]
    sma_50 = levels["sma_50"]
    w52_high = levels["week52_high"]

    # Stop loss: tighter of support / SMA50, fallback 8% below
    candidates = [v for v in (support, sma_50) if v and v < price]
    stop_loss = max(candidates) if candidates else round(price * 0.92, 2)

    # Targets
    target1 = resistance if resistance and resistance > price else round(price * 1.06, 2)
    target2 = w52_high if w52_high and w52_high > target1 else round(price * 1.12, 2)

    risk_per_share = max(0.01, round(price - stop_loss, 2))
    reward1 = round(target1 - price, 2)
    reward2 = round(target2 - price, 2)
    rr_ratio = round(reward1 / risk_per_share, 2) if risk_per_share > 0 else 0.0

    # Position sizing
    risk_amount = account_size * (risk_pct / 100.0)
    shares = int(risk_amount / risk_per_share) if risk_per_share > 0 else 0
    position_value = round(shares * price, 2)
    profit_t1 = round(shares * reward1, 2)
    profit_t2 = round(shares * reward2, 2)
    loss_at_stop = round(shares * risk_per_share, 2)

    # Signal alignment
    bull_count, bear_count, neutral_count, total = 0, 0, 0, 0
    for s in (getattr(report, "sections", []) or []):
        title = (s.title or "").lower()
        if "overview" in title or "confluence" in title:
            continue
        cl = (s.content or "").lower()
        is_bull = any(w in cl for w in _BULLISH)
        is_bear = any(w in cl for w in _BEARISH)
        if is_bull and not is_bear:   bull_count += 1
        elif is_bear and not is_bull: bear_count += 1
        else:                          neutral_count += 1
        total += 1
    dominant = "bullish" if bull_count >= bear_count else "bearish"
    agree = max(bull_count, bear_count)
    alignment_pct = round((agree / total) * 100) if total else 0

    # Timing notes
    timing_good: list[str] = []
    timing_warn: list[str] = []
    for s in (getattr(report, "sections", []) or []):
        title = (s.title or "").lower()
        if "macro" in title:
            regime = (s.data or {}).get("regime", "normal") if isinstance(s.data, dict) else "normal"
            if regime == "normal":
                timing_good.append("Market regime: Normal (no macro headwinds)")
            elif "recession" in str(regime):
                timing_warn.append("Recession warning — reduce position sizes")
            elif "volatil" in str(regime):
                timing_warn.append("High volatility — tighten stops, reduce size")
    if support and abs(price - support) / price < 0.03:
        timing_good.append(f"Price near support (${support:.2f}) — good entry zone")
    if resistance and abs(price - resistance) / price < 0.02:
        timing_warn.append(f"Price near resistance (${resistance:.2f}) — wait for confirmed breakout")

    # Risks (from report)
    risks = []
    for r in (getattr(report, "risks", []) or [])[:5]:
        risks.append(str(r))

    return {
        "price": price,
        "entry": price,
        "stop_loss": stop_loss,
        "target1": target1,
        "target2": target2,
        "support": support,
        "resistance": resistance,
        "stop_pct": round((risk_per_share / price) * 100, 1),
        "target1_pct": round((reward1 / price) * 100, 1),
        "target2_pct": round((reward2 / price) * 100, 1),
        "risk_per_share": risk_per_share,
        "risk_reward": rr_ratio,
        "account_size": account_size,
        "risk_pct": risk_pct,
        "shares": shares,
        "position_value": position_value,
        "profit_t1": profit_t1,
        "profit_t2": profit_t2,
        "loss_at_stop": loss_at_stop,
        "alignment_pct": alignment_pct,
        "alignment_dominant": dominant,
        "alignment_bull": bull_count,
        "alignment_bear": bear_count,
        "alignment_neutral": neutral_count,
        "alignment_total": total,
        "timing_good": timing_good,
        "timing_warn": timing_warn,
        "risks": risks,
    }


# ── Period price change ──────────────────────────────────────────


def _period_change(symbol: str, period: str) -> dict | None:
    days = _PERIOD_DAYS.get(period, 21)
    try:
        from src.data.gateway import DataGateway
        gw = DataGateway()
        hist = gw.get_historical(symbol, period_days=max(days + 5, 30))
        if hist is None or hist.empty:
            return None
        closes = hist["close"].astype(float)
        last = float(closes.iloc[-1])
        offset = min(days, len(closes) - 1)
        if offset <= 0:
            return {"period": period, "lookback_days": days, "start_price": last,
                    "end_price": last, "change_pct": 0.0,
                    "spark": [{"date": str(d), "close": float(c)}
                              for d, c in zip(hist["date"].tolist(), closes.tolist())]}
        start = float(closes.iloc[-1 - offset])
        change = ((last - start) / start) * 100.0 if start else 0.0
        sub = hist.tail(offset + 1)
        return {
            "period": period,
            "lookback_days": days,
            "start_price": start,
            "end_price": last,
            "change_pct": change,
            "spark": [
                {"date": str(d), "close": float(c)}
                for d, c in zip(sub["date"].tolist(), sub["close"].astype(float).tolist())
            ],
        }
    except Exception:
        return None


# ── Volume profile (volume-by-price bins) ────────────────────────


def _volume_profile(symbol: str, period_days: int = 60, bins: int = 30) -> dict | None:
    try:
        from src.data.gateway import DataGateway
        gw = DataGateway()
        hist = gw.get_historical(symbol, period_days=period_days)
        if hist is None or hist.empty:
            return None
        closes = hist["close"].astype(float)
        volumes = hist["volume"].astype(float)
        price_min = float(closes.min())
        price_max = float(closes.max())
        bin_size = (price_max - price_min) / bins
        if bin_size <= 0:
            return None
        bucket_volumes: dict[float, float] = {}
        for c, v in zip(closes, volumes):
            idx = int((c - price_min) / bin_size)
            idx = min(idx, bins - 1)  # right edge inclusive
            bucket = round(price_min + idx * bin_size, 2)
            bucket_volumes[bucket] = bucket_volumes.get(bucket, 0.0) + float(v)
        prices = sorted(bucket_volumes.keys())
        rows = [{"price": p, "volume": float(bucket_volumes[p])} for p in prices]
        # Point of Control = price level with the highest volume
        poc = max(rows, key=lambda r: r["volume"])["price"] if rows else None
        last_price = float(closes.iloc[-1])
        return {
            "rows": rows,
            "poc": poc,
            "last_price": last_price,
            "period_days": period_days,
            "bin_size": round(bin_size, 4),
        }
    except Exception:
        return None


# ── Earnings calendar ────────────────────────────────────────────


def _earnings_calendar(symbol: str) -> list[dict]:
    try:
        from src.data.gateway import DataGateway
        gw = DataGateway()
        rows = gw.get_earnings_calendar(symbol) or []
        out = []
        for r in rows[:8]:
            out.append({
                "date": r.get("date"),
                "eps_estimate": float(r["eps_estimate"]) if r.get("eps_estimate") is not None else None,
                "eps_actual": float(r["eps_actual"]) if r.get("eps_actual") is not None else None,
                "surprise_pct": float(r["surprise_pct"]) if r.get("surprise_pct") is not None else None,
            })
        return out
    except Exception:
        return []


# ── Public entry ─────────────────────────────────────────────────


def get_deep_dive(
    symbol: str,
    period: str = "3M",
    signal_filter: str = "all",
    account_size: float = 10000.0,
    risk_pct: float = 2.0,
    force: bool = False,
) -> dict:
    from src.orchestrator import analyze_stock

    symbol = symbol.upper()
    if period not in _PERIOD_DAYS:
        period = "3M"

    cache_key = (
        f"deep_dive:v2:{symbol}:{period}:{signal_filter}:"
        f"{int(account_size)}:{risk_pct}"
    )

    # ── Cache hit ─────────────────────────────────────────────
    if not force:
        cached = cache_get(cache_key)
        if cached:
            cached["from_cache"] = True
            return cached

    report = analyze_stock(symbol, export=False, pdf=False)

    # Risk + sentiment
    risk_rating = 3
    try:
        risk_rating = int(getattr(report.risk_rating, "value", 3))
    except Exception:
        pass

    sentiment_score: float | None = None
    try:
        s = report.sentiment_score
        sentiment_score = float(s) if isinstance(s, (int, float, Decimal)) else None
    except Exception:
        pass

    price = None
    try:
        price = float(report.current_price)
    except Exception:
        pass

    period_change = _period_change(symbol, period)
    if period_change and price is None:
        price = period_change.get("end_price")

    signals = _to_signals(report)

    # Apply signal filter
    f = (signal_filter or "all").lower()
    if f == "buy":
        signals = [s for s in signals if s["direction"] == "bullish"]
    elif f == "sell":
        signals = [s for s in signals if s["direction"] == "bearish"]
    elif f == "strong":
        signals = [s for s in signals if s["strength"] >= 0.7]

    bullish = [s for s in signals if s["direction"] == "bullish"]
    bearish = [s for s in signals if s["direction"] == "bearish"]

    # Group by category for the breakdown panel
    grouped: dict[str, list[dict]] = {}
    for s in signals:
        grouped.setdefault(s["category"], []).append(s)

    # Risk label
    risk_label = "Low" if risk_rating <= 2 else "High" if risk_rating >= 4 else "Moderate"

    # Pull name/sector with fallbacks: live Stock object, then local STOCK_DB catalog,
    # then cached fundamentals — Yahoo Finance often fails to return company info.
    stock_obj = getattr(report, "stock", None)
    name = getattr(stock_obj, "name", None)
    sector = getattr(stock_obj, "sector", None)
    industry = getattr(stock_obj, "industry", None)

    if not name or not sector:
        try:
            from api.services.discover_service import _load_stock_meta
            meta = _load_stock_meta().get(symbol, {})
            name = name or meta.get("name")
            sector = sector or meta.get("sector")
        except Exception:
            pass

    if not name or not sector or not industry:
        try:
            fund = cache_get(f"market:fundamentals:{symbol}") or {}
            name = name or fund.get("longName") or fund.get("shortName")
            sector = sector or fund.get("sector")
            industry = industry or fund.get("industry")
        except Exception:
            pass

    now_iso = datetime.utcnow().isoformat() + "Z"
    payload = {
        "symbol": symbol,
        "name": name,
        "sector": sector,
        "industry": industry,
        "verdict": str(report.verdict.value),
        "confidence": str(report.confidence),
        "risk_rating": risk_rating,
        "risk_label": risk_label,
        "price": price,
        "period_change": period_change,
        "summary": getattr(report, "summary", None),
        "sentiment_score": sentiment_score,
        "signals": signals,
        "signal_groups": grouped,
        "signal_counts": {
            "bullish": len(bullish),
            "bearish": len(bearish),
            "neutral": len(signals) - len(bullish) - len(bearish),
            "total": len(signals),
        },
        "trade_plan": _trade_plan(report, price, account_size, risk_pct),
        "earnings": _earnings_calendar(symbol),
        "volume_profile": _volume_profile(symbol),
        "available_periods": list(_PERIOD_DAYS.keys()),
        "period": period,
        "signal_filter": f,
        "last_updated": now_iso,
        "cached_at": now_iso,
        "from_cache": False,
    }

    try:
        cache_set(cache_key, payload, ttl_minutes=_CACHE_TTL_MINUTES)
    except Exception:
        # Don't fail the request if the cache write fails
        pass

    return payload
