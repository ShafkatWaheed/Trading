"""Bubble Score — quantifies the gap between price action and fundamentals.

Composite 0-100 score from three components:
  1. Growth gap (40 pts):  how much faster price has run vs revenue/earnings growth
  2. Valuation extremes (40 pts):  how stretched P/E, P/S, P/FCF are vs broad norms
  3. Momentum heat (20 pts):  recent 3M parabolic move, discounted if earnings backed

This is a heuristic. It flags suspicion, not certainty — a 90 here just means
"price is way ahead of what the business has actually delivered."
"""
from __future__ import annotations

from datetime import datetime

from src.data.gateway import DataGateway
from src.utils.db import cache_get, cache_set

_CACHE_TTL_MINUTES = 6 * 60  # 6h — refresh sub-daily so fundamentals updates land


def _safe_float(v) -> float | None:
    try:
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _fetch_yf_fundamentals(symbol: str) -> dict:
    """Direct yfinance fetch for the extended fundamentals we need (P/S, FCF, MCap)."""
    cache_key = f"bubble:fundamentals:v1:{symbol}"
    cached = cache_get(cache_key)
    if cached:
        return cached
    out: dict = {
        "trailing_pe": None, "forward_pe": None, "price_to_sales": None,
        "price_to_book": None, "revenue_growth": None,
        "earnings_growth": None, "earnings_q_growth": None,
        "free_cashflow": None, "market_cap": None, "total_revenue": None,
        "profit_margins": None,
    }
    try:
        import yfinance as yf
        info = yf.Ticker(symbol).info or {}
        out["trailing_pe"]     = _safe_float(info.get("trailingPE"))
        out["forward_pe"]      = _safe_float(info.get("forwardPE"))
        out["price_to_sales"]  = _safe_float(info.get("priceToSalesTrailing12Months"))
        out["price_to_book"]   = _safe_float(info.get("priceToBook"))
        out["revenue_growth"]  = _safe_float(info.get("revenueGrowth"))
        out["earnings_growth"] = _safe_float(info.get("earningsGrowth"))
        out["earnings_q_growth"] = _safe_float(info.get("earningsQuarterlyGrowth"))
        out["free_cashflow"]   = _safe_float(info.get("freeCashflow"))
        out["market_cap"]      = _safe_float(info.get("marketCap"))
        out["total_revenue"]   = _safe_float(info.get("totalRevenue"))
        out["profit_margins"]  = _safe_float(info.get("profitMargins"))
    except Exception:
        pass
    try:
        cache_set(cache_key, out, ttl_minutes=_CACHE_TTL_MINUTES)
    except Exception:
        pass
    return out


def _price_change_pct(symbol: str, days_back: int) -> float | None:
    """Compute price change over `days_back` trading days."""
    try:
        hist = DataGateway().get_historical(symbol, period_days=max(days_back + 30, 100))
        if hist is None or hist.empty or len(hist) < 2:
            return None
        df = hist.reset_index(drop=True)
        end_idx = len(df) - 1
        start_idx = max(0, end_idx - days_back)
        if start_idx >= end_idx:
            return None
        start = float(df["close"].iloc[start_idx])
        end = float(df["close"].iloc[end_idx])
        if start <= 0:
            return None
        return ((end - start) / start) * 100.0
    except Exception:
        return None


def _growth_gap_points(price_1y_pct: float | None,
                      revenue_growth: float | None,
                      earnings_growth: float | None) -> tuple[float, float | None]:
    """Up to 35 pts based on (price_1y_pct − max(rev, eps) growth, both as %)."""
    if price_1y_pct is None:
        return 0.0, None
    growths = [g * 100 for g in (revenue_growth, earnings_growth) if g is not None]
    fundamental_pct = max(growths) if growths else 0.0
    gap = price_1y_pct - fundamental_pct
    if gap <= 0:
        return 0.0, gap
    # 1 point per ~2.5% gap, capped at 35 (so 87%+ gap saturates)
    pts = min(35.0, gap / 2.5)
    return pts, gap


def _valuation_points(pe: float | None, ps: float | None, pfcf: float | None) -> tuple[float, dict]:
    """Up to 45 pts from stretched multiples vs broad-market norms.

    Curves are intentionally steep at the upper end so TSLA-style P/E=400 and
    PLTR-style P/S=60 produce visibly higher scores than P/E=30 / P/S=10.
    """
    notes: dict = {}
    pe_pts = 0.0
    if pe is not None and pe > 0:
        if pe > 20:
            # Linear 20→80 PE maps to 0→20 pts, then +1pt per 30 PE above 80, capped 25
            if pe <= 80:
                pe_pts = (pe - 20) / 60 * 20
            else:
                pe_pts = 20 + min(5.0, (pe - 80) / 30)
        notes["pe"] = round(pe, 1)
    ps_pts = 0.0
    if ps is not None and ps > 0:
        if ps > 3:
            # Linear 3→15 PS maps to 0→12 pts, then +1pt per 10 PS above 15, capped 15
            if ps <= 15:
                ps_pts = (ps - 3) / 12 * 12
            else:
                ps_pts = 12 + min(3.0, (ps - 15) / 10 * 3)
        notes["ps"] = round(ps, 1)
    pfcf_pts = 0.0
    if pfcf is not None and pfcf > 0:
        if pfcf > 25:
            # Linear 25→70 PFCF maps to 0→10 pts, capped 10
            pfcf_pts = min(10.0, (pfcf - 25) / 45 * 10.0)
        notes["pfcf"] = round(pfcf, 1)
    return pe_pts + ps_pts + pfcf_pts, notes


def _momentum_points(price_3m_pct: float | None,
                    earnings_growth: float | None) -> tuple[float, float | None]:
    """Up to 20 pts for parabolic 3M, discounted if earnings growth justifies it."""
    if price_3m_pct is None or price_3m_pct < 30:
        return 0.0, price_3m_pct
    raw = min(20.0, (price_3m_pct - 30) / 30 * 20.0)
    # Discount when earnings growth is strong enough to justify the run
    if earnings_growth is not None and earnings_growth > 0.5:  # >50% YoY
        raw *= 0.5
    return raw, price_3m_pct


def _label(score: float) -> str:
    if score < 25:  return "Value Zone"
    if score < 50:  return "Fair Value"
    if score < 70:  return "Stretched"
    if score < 85:  return "Frothy"
    return "Bubble Territory"


def _verdict_headline(score: float) -> str:
    if score >= 85: return "Bubble warning."
    if score >= 70: return "Looks frothy."
    if score >= 50: return "Priced rich."
    if score >= 25: return "Roughly fair."
    return "Looks reasonable."


def _verdict_reasons(pe: float | None, ps: float | None,
                     pfcf: float | None, growth_gap_pct: float | None) -> list[str]:
    """Concrete vivid bullets. Each one tells the user exactly what they're betting on."""
    reasons: list[str] = []

    if pe is not None and pe > 30:
        years_needed = max(2, int(round(pe / 22)))  # 22 ≈ midpoint of 20–25 normal
        reasons.append(
            f"At P/E {pe:.0f}, you'd need {pe:.0f} years of current profits to earn back what you paid "
            f"(normal companies trade at 20–25 years). That's betting profits will roughly {years_needed}× from here."
        )

    if ps is not None and ps > 7:
        halved = ps / 2
        reasons.append(
            f"At P/S {ps:.0f}, you're paying ${ps:.0f} for every $1 of yearly sales "
            f"(typical: $1–5; hot tech tops near $20). Even if revenue doubles, you'd still be at {halved:.0f}× sales."
        )

    if pfcf is not None and pfcf > 40 and not reasons:
        reasons.append(
            f"At P/FCF {pfcf:.0f}, you'd need {pfcf:.0f} years of actual cash generated to earn back what you paid "
            f"(healthy companies: 15–30)."
        )

    if growth_gap_pct is not None and growth_gap_pct > 10:
        reasons.append(
            f"The stock has climbed {growth_gap_pct:.0f}% more than the business itself has grown — "
            f"that's the price running ahead of fundamentals."
        )

    if growth_gap_pct is not None and growth_gap_pct < -50:
        reasons.append(
            f"The business has grown {abs(growth_gap_pct):.0f}% MORE than the price did — "
            f"fundamentals are catching up to the valuation. Worth checking if the growth came from a small base, "
            f"in which case the % is fragile."
        )

    return reasons


def get_bubble_score(symbol: str, force: bool = False) -> dict:
    symbol = symbol.upper()
    cache_key = f"bubble_score:v1:{symbol}"
    if not force:
        cached = cache_get(cache_key)
        if cached:
            cached["from_cache"] = True
            return cached

    fund = _fetch_yf_fundamentals(symbol)

    pe = fund.get("trailing_pe")
    ps = fund.get("price_to_sales")
    pb = fund.get("price_to_book")
    mc = fund.get("market_cap")
    fcf = fund.get("free_cashflow")
    pfcf = (mc / fcf) if (mc and fcf and fcf > 0) else None

    price_1y = _price_change_pct(symbol, days_back=252)
    price_3m = _price_change_pct(symbol, days_back=63)

    revenue_growth = fund.get("revenue_growth")
    earnings_growth = fund.get("earnings_growth") or fund.get("earnings_q_growth")

    gap_pts, growth_gap_pct = _growth_gap_points(price_1y, revenue_growth, earnings_growth)
    val_pts, val_notes = _valuation_points(pe, ps, pfcf)
    mom_pts, _ = _momentum_points(price_3m, earnings_growth)

    score = round(gap_pts + val_pts + mom_pts, 1)
    score = max(0.0, min(100.0, score))

    # Vibes premium: what % of the 1Y price gain came from non-fundamentals.
    vibes_share_pct: float | None = None
    fundamental_pct: float | None = None
    if price_1y is not None and price_1y > 0:
        growths = [g * 100 for g in (revenue_growth, earnings_growth) if g is not None]
        fundamental_pct = max(growths) if growths else 0.0
        if fundamental_pct >= price_1y:
            vibes_share_pct = 0.0
        else:
            vibes_share_pct = round(((price_1y - fundamental_pct) / price_1y) * 100.0, 1)

    payload = {
        "symbol": symbol,
        "score": score,
        "label": _label(score),
        "components": {
            "growth_gap":       round(gap_pts, 1),
            "valuation":        round(val_pts, 1),
            "momentum":         round(mom_pts, 1),
        },
        "metrics": {
            "price_change_1y_pct": round(price_1y, 1) if price_1y is not None else None,
            "price_change_3m_pct": round(price_3m, 1) if price_3m is not None else None,
            "revenue_growth_pct": round(revenue_growth * 100, 1) if revenue_growth is not None else None,
            "earnings_growth_pct": round(earnings_growth * 100, 1) if earnings_growth is not None else None,
            "growth_gap_pct":   round(growth_gap_pct, 1) if growth_gap_pct is not None else None,
            "vibes_share_pct":  vibes_share_pct,
            "fundamental_growth_pct": round(fundamental_pct, 1) if fundamental_pct is not None else None,
            "pe_ratio":         round(pe, 1) if pe is not None else None,
            "ps_ratio":         round(ps, 1) if ps is not None else None,
            "pb_ratio":         round(pb, 1) if pb is not None else None,
            "pfcf_ratio":       round(pfcf, 1) if pfcf is not None else None,
        },
        "verdict": _verdict_headline(score),
        "reasons": _verdict_reasons(pe, ps, pfcf, growth_gap_pct),
        "last_updated": datetime.utcnow().isoformat() + "Z",
        "from_cache": False,
    }

    try:
        cache_set(cache_key, payload, ttl_minutes=_CACHE_TTL_MINUTES)
    except Exception:
        pass
    return payload
