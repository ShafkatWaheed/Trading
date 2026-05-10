"""Discover service: opportunity ranking using precomputed scores + rich metadata."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from src.utils.db import init_db, get_all_precomputed_scores, cache_get, save_precomputed_score
from api.constants import PERIOD_DAYS as _PERIOD_DAYS


POPULAR_TOP5 = ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN"]


def _load_stock_meta() -> dict[str, dict]:
    from src.data.stock_db import stock_meta
    return stock_meta()


def _parse_rr(rr_raw) -> float | None:
    """risk_reward_ratio is stored as '216.5:1' — parse leading float."""
    if rr_raw is None:
        return None
    try:
        return float(str(rr_raw).split(":")[0])
    except Exception:
        return None


def _change_pct_from_history(symbol: str, lookback_days: int) -> tuple[float | None, float | None]:
    """Best-effort current price + period change. Uses cached fundamentals for current price."""
    try:
        from src.data.gateway import DataGateway
        gw = DataGateway()
        hist = gw.get_historical(symbol, period_days=max(lookback_days + 5, 30))
        if hist is None or hist.empty:
            return None, None
        closes = hist["close"].astype(float)
        last = float(closes.iloc[-1])
        offset = min(lookback_days, len(closes) - 1)
        if offset <= 0:
            return last, 0.0
        prior = float(closes.iloc[-1 - offset])
        change = ((last - prior) / prior) * 100.0 if prior else 0.0
        return last, change
    except Exception:
        return None, None


def _fundamentals_for(symbol: str) -> dict:
    """Pull cached fundamentals — sector, mcap, 52w high/low, earnings."""
    try:
        c = cache_get(f"market:fundamentals:{symbol}")
        if not c:
            return {}
        return c
    except Exception:
        return {}


def _format_mcap(v) -> str | None:
    try:
        m = float(v)
        if m >= 1e12: return f"${m/1e12:.1f}T"
        if m >= 1e9:  return f"${m/1e9:.0f}B"
        if m >= 1e6:  return f"${m/1e6:.0f}M"
        return f"${m:.0f}"
    except Exception:
        return None


# Strategy descriptions — short text shown on secondary signals
STRATEGY_DESC = {
    "Volume Spike": "Volume well above 20-day average — institutional interest or catalyst-driven move.",
    "Momentum": "Trending up with healthy RSI (50-70) and confirming MACD direction.",
    "Breakout": "Approaching/breaking through resistance. Confirmed breakouts with volume often sustain.",
    "Oversold Bounce": "RSI below 30 — extreme oversold. Statistically tend to bounce within days.",
    "Mean Reversion": "Price has moved far from average. Counter-trend bet on a return — higher risk.",
    "Golden Cross": "50-day MA crossed above 200-day MA — one of the most reliable long-term bullish signals.",
    "Death Cross": "50-day MA crossed below 200-day MA — bearish, often precedes extended downtrends.",
    "Insider Accumulation": "Multiple insiders bought within 7 days. Insiders have material non-public information.",
    "Congress Buying": "Bipartisan congressional buying. May indicate upcoming favorable policy.",
    "Earnings Catalyst": "Earnings within 14 days with favorable technical setup — can amplify a beat reaction.",
    "Dividend Play": "Dividend yield > 3% with stable fundamentals. Income while you hold.",
    "Bollinger Squeeze": "Bollinger Bands narrowing — volatility compression typically precedes large breakout.",
    "Support Bounce": "Testing proven support. Risk well-defined, clear upside to resistance.",
    "Gap Fill": "Filling a price gap toward pre-gap level. ~70% of gaps fill within weeks.",
    "Sector Leader": "Top performer in the strongest sector — leaders in leaders tend to outperform.",
    "Neutral": "No clear pattern — multiple signals conflicting or absent.",
}

STRATEGY_THEME = {
    "Volume Spike": {"icon": "📊", "color": "#3b82f6"},
    "Momentum": {"icon": "🚀", "color": "#22c55e"},
    "Breakout": {"icon": "💥", "color": "#f59e0b"},
    "Oversold Bounce": {"icon": "🔄", "color": "#06b6d4"},
    "Mean Reversion": {"icon": "📉", "color": "#8b5cf6"},
    "Golden Cross": {"icon": "✨", "color": "#fbbf24"},
    "Death Cross": {"icon": "💀", "color": "#dc2626"},
    "Insider Accumulation": {"icon": "🏦", "color": "#10b981"},
    "Congress Buying": {"icon": "🏛", "color": "#6366f1"},
    "Earnings Catalyst": {"icon": "📅", "color": "#f97316"},
    "Dividend Play": {"icon": "💵", "color": "#14b8a6"},
    "Bollinger Squeeze": {"icon": "🔧", "color": "#a855f7"},
    "Support Bounce": {"icon": "🛡", "color": "#0ea5e9"},
    "Gap Fill": {"icon": "📐", "color": "#78716c"},
    "Sector Leader": {"icon": "👑", "color": "#eab308"},
    "Neutral": {"icon": "⏸", "color": "#6b7280"},
}


def _spark_data(symbol: str, lookback_days: int) -> list[dict] | None:
    """Tiny price series for sparkline charts. ~30 points max."""
    try:
        from src.data.gateway import DataGateway
        gw = DataGateway()
        hist = gw.get_historical(symbol, period_days=max(lookback_days + 5, 30))
        if hist is None or hist.empty:
            return None
        trim = min(lookback_days, len(hist))
        sub = hist.tail(trim)
        return [
            {"date": str(d), "close": float(c)}
            for d, c in zip(sub["date"].tolist(), sub["close"].astype(float).tolist())
        ]
    except Exception:
        return None


def _build_card(symbol: str, d: dict, info: dict, lookback_days: int) -> dict:
    last_price, change_pct = _change_pct_from_history(symbol, lookback_days)
    fund = _fundamentals_for(symbol)
    spark = _spark_data(symbol, lookback_days)

    rr = _parse_rr(d.get("risk_reward_ratio"))
    sub_scores = {
        "volume": float(d.get("volume_score") or 0),
        "price": float(d.get("price_score") or 0),
        "flow": float(d.get("flow_score") or 0),
        "risk_reward": float(d.get("risk_reward_score") or 0),
    }

    sector_meta = info.get("sector")
    industry = fund.get("industry")
    sector_str = sector_meta or fund.get("sector")
    if industry and sector_str:
        sector_str = f"{sector_str} · {industry}"

    week52_high = fund.get("week_52_high")
    week52_low = fund.get("week_52_low")
    week52 = None
    if week52_high and week52_low and last_price:
        try:
            high = float(week52_high)
            low = float(week52_low)
            if high > low:
                pct_pos = ((last_price - low) / (high - low)) * 100.0
                week52 = {
                    "high": high,
                    "low": low,
                    "position_pct": max(0.0, min(100.0, pct_pos)),
                }
        except Exception:
            week52 = None

    secondaries: list[dict] = []
    for s in (d.get("secondary_strategies") or []):
        theme = STRATEGY_THEME.get(s, STRATEGY_THEME["Neutral"])
        secondaries.append({
            "name": s,
            "icon": theme["icon"],
            "description": STRATEGY_DESC.get(s, ""),
        })

    # Confirmation flags — present on richer scores
    confirms = {
        "trend_pullback": bool(d.get("trend_pullback")),
        "relative_strength": bool(d.get("relative_strength")),
        "volume_confirmed": bool(d.get("volume_confirmed")),
        "momentum_override": bool(d.get("momentum_override")),
    }
    confirm_count = sum([confirms["trend_pullback"], confirms["relative_strength"], confirms["volume_confirmed"]])

    return {
        "symbol": symbol,
        "name": info.get("name") or fund.get("longName"),
        "sector": sector_meta or fund.get("sector"),
        "sector_label": sector_str,
        "market_cap": _format_mcap(fund.get("market_cap")),
        "next_earnings": fund.get("next_earnings_date"),
        "price": last_price,
        "change_pct": change_pct,
        "week52": week52,
        "score": round(float(d.get("total_score") or 0), 1),
        "label": d.get("label") or "—",
        "strategy": d.get("strategy") or "Neutral",
        "strategy_icon": STRATEGY_THEME.get(d.get("strategy") or "Neutral", STRATEGY_THEME["Neutral"])["icon"],
        "strategy_description": STRATEGY_DESC.get(d.get("strategy") or "Neutral", ""),
        "secondary_strategies": secondaries,
        "risk_reward_ratio": rr,
        "sub_scores": sub_scores,
        "confirmations": confirms,
        "confirmation_count": confirm_count,
        "spark": spark,
    }


def _compute_score_for(symbol: str) -> dict | None:
    """Compute opportunity score for a single symbol on demand (also writes it
    into the precomputed_scores table so the next call is instant)."""
    try:
        from src.analysis import technical
        from src.analysis.opportunity import compute_opportunity
        from src.data.gateway import DataGateway

        gw = DataGateway()
        hist = gw.get_historical(symbol, period_days=252)
        if hist is None or hist.empty:
            return None

        tech = technical.analyze(symbol, hist)
        score = compute_opportunity(symbol, tech)

        score_dict = {
            "total_score": int(getattr(score, "total_score", 0) or 0),
            "volume_score": int(getattr(score, "volume_score", 0) or 0),
            "price_score": int(getattr(score, "price_score", 0) or 0),
            "flow_score": int(getattr(score, "flow_score", 0) or 0),
            "risk_reward_score": int(getattr(score, "risk_reward_score", 0) or 0),
            "risk_reward_ratio": str(getattr(score, "risk_reward_ratio", "")),
            "strategy": str(getattr(score, "strategy", "Neutral")),
            "secondary_strategies": list(getattr(score, "secondary_strategies", []) or []),
            "label": str(getattr(score, "label", "—")),
        }
        try:
            save_precomputed_score(symbol, score_dict)
        except Exception:
            pass
        return score_dict
    except Exception:
        return None


def get_opportunities(
    min_score: float = 0,
    limit: int = 30,
    sector: str | None = None,
    period: str = "1M",
    symbols: list[str] | None = None,
) -> dict:
    """Return ranked opportunity cards. Pulls from precomputed_scores; if scope
    symbols are missing scores, computes them on-demand in parallel."""
    init_db()
    meta = _load_stock_meta()
    lookback_days = _PERIOD_DAYS.get(period, 21)

    scope = {s.upper() for s in symbols} if symbols else None

    # Pull cached scores fresh (within 24h)
    scores = get_all_precomputed_scores(max_age_minutes=24 * 60)

    # If we have a fixed scope (watchlist), compute missing ones on-demand.
    if scope:
        missing = [s for s in scope if s not in scores]
        if missing:
            with ThreadPoolExecutor(max_workers=min(6, len(missing))) as pool:
                futures = {pool.submit(_compute_score_for, s): s for s in missing}
                for fut in as_completed(futures):
                    sym = futures[fut]
                    try:
                        result = fut.result(timeout=60)
                    except Exception:
                        result = None
                    if result:
                        scores[sym] = result

    rows = []
    for symbol, d in scores.items():
        if scope and symbol not in scope:
            continue
        score = float(d.get("total_score", 0))
        if score < min_score:
            continue
        info = meta.get(symbol, {})
        if sector and info.get("sector") != sector:
            continue
        rows.append(_build_card(symbol, d, info, lookback_days))

    rows.sort(key=lambda x: x["score"], reverse=True)
    return {
        "opportunities": rows[:limit],
        "period": period,
        "lookback_days": lookback_days,
        "available_periods": list(_PERIOD_DAYS.keys()),
        "popular_top5": POPULAR_TOP5,
        "last_updated": datetime.utcnow().isoformat() + "Z",
    }
