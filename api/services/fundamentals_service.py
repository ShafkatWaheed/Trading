"""Fundamentals service — score a stock's business + tell its story.

Pulls fundamentals from yfinance, runs them through src.analysis.fundamental,
and composes a one-line narrative archetype ("cash cow, low growth", "expensive
growth story", "hidden gem", etc.) along with the raw inputs the UI needs to
let users see *why* each pillar got its score.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from src.analysis import fundamental as fundamental_analysis
from src.models.stock import StockFundamentals
from src.utils.db import cache_get, cache_set

_CACHE_TTL_MINUTES = 12 * 60  # fundamentals don't move intraday


def _safe_dec(v) -> Decimal | None:
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except (TypeError, ValueError):
        return None


def _safe_float(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fetch_fundamentals(symbol: str) -> tuple[StockFundamentals | None, dict]:
    """Pull yfinance .info and convert to our StockFundamentals model.

    Returns (model, raw_extras) — raw_extras carries fields the model doesn't
    track but the UI wants (FCF margin, payout coverage, etc.).
    """
    extras: dict = {
        "fcf_margin_pct": None,
        "payout_ratio": None,
        "gross_margin_pct": None,
        "operating_margin_pct": None,
    }

    try:
        import yfinance as yf
        t = yf.Ticker(symbol)
        info = t.info or {}
    except Exception:
        return None, extras

    market_cap = _safe_dec(info.get("marketCap"))
    if market_cap is None:
        return None, extras

    # yfinance returns these as decimals (0.23 = 23%); normalize to percent.
    def _pct(v) -> Decimal | None:
        d = _safe_dec(v)
        return d * 100 if d is not None else None

    revenue = _safe_dec(info.get("totalRevenue"))
    fcf = _safe_dec(info.get("freeCashflow"))
    if revenue and revenue > 0 and fcf is not None:
        extras["fcf_margin_pct"] = round(float(fcf / revenue * 100), 1)

    extras["gross_margin_pct"]     = _safe_float(_pct(info.get("grossMargins")))
    extras["operating_margin_pct"] = _safe_float(_pct(info.get("operatingMargins")))
    extras["payout_ratio"]         = _safe_float(_safe_dec(info.get("payoutRatio")))

    # yfinance debtToEquity is reported as a number (e.g. 142.5) representing
    # percent, not the ratio. Convert to ratio for fundamental.py thresholds.
    de_raw = _safe_dec(info.get("debtToEquity"))
    de = de_raw / 100 if de_raw is not None else None

    # yfinance changed `dividendYield` to be in percent form (KO=2.6 means 2.6%).
    # `trailingAnnualDividendYield` remains the decimal form (0.026). Use the
    # already-percent field directly and fall back to the decimal field * 100.
    dy = _safe_dec(info.get("dividendYield"))
    if dy is None:
        dy = _pct(info.get("trailingAnnualDividendYield"))

    model = StockFundamentals(
        symbol=symbol.upper(),
        market_cap=market_cap,
        pe_ratio=_safe_dec(info.get("trailingPE")),
        peg_ratio=_safe_dec(info.get("pegRatio") or info.get("trailingPegRatio")),
        eps=_safe_dec(info.get("trailingEps")),
        eps_growth=_pct(info.get("earningsGrowth") or info.get("earningsQuarterlyGrowth")),
        revenue=revenue,
        revenue_growth=_pct(info.get("revenueGrowth")),
        profit_margin=_pct(info.get("profitMargins")),
        roe=_pct(info.get("returnOnEquity")),
        debt_to_equity=de,
        free_cash_flow=fcf,
        dividend_yield=dy,
        sector=info.get("sector") or "",
        industry=info.get("industry") or "",
    )
    return model, extras


def _round_decimals_in_text(s: str) -> str:
    """Round any decimals embedded in strength/weakness strings to 1 decimal place."""
    import re
    def _r(m: re.Match) -> str:
        try:
            return f"{float(m.group(0)):.1f}"
        except ValueError:
            return m.group(0)
    return re.sub(r"-?\d+\.\d+", _r, s)


def _compose_story(s: fundamental_analysis.FundamentalScore, f: StockFundamentals) -> tuple[str, str]:
    """Pick a one-line narrative archetype + a short tagline.

    Returns (archetype, lede). The archetype is a short label like
    "Cash Machine" or "Growth Story" used for visual emphasis; the lede is a
    full sentence the card opens with.
    """
    g, p, h, v = s.growth_score, s.profitability_score, s.health_score, s.valuation_score

    # Most expressive archetypes first — let the punchy ones win
    if g >= 4 and p >= 4 and h >= 4 and v >= 4:
        return ("Compounder", f"Every pillar firing — strong growth, fat margins, clean balance sheet, and {f.symbol} is still cheap relative to all of that.")
    if g >= 4 and p >= 4 and v <= 2:
        return ("Expensive Growth", f"{f.symbol} is a quality growth machine, but the market has already priced it for perfection.")
    if g <= 2 and p >= 4 and h >= 4:
        return ("Cash Cow", f"{f.symbol} isn't growing fast, but it prints cash and the balance sheet is rock-solid — a profit-first holding.")
    if g >= 4 and p <= 2:
        return ("Growth Story", f"{f.symbol} is sprinting on top-line growth, but the business hasn't turned that into profits yet.")
    if v >= 4 and g >= 3 and h >= 3:
        return ("Hidden Gem", f"{f.symbol} screens cheap on valuation despite respectable growth and a healthy balance sheet.")
    if h <= 2:
        return ("Balance-Sheet Watch", f"{f.symbol}'s growth and profits look OK on paper, but the balance sheet is the part to keep eyes on.")
    if g <= 2 and p <= 2:
        return ("Turnaround Candidate", f"{f.symbol} is currently weak on both growth and profitability — only a buy if you believe in a comeback.")
    if v <= 2:
        return ("Priced for Perfection", f"{f.symbol} is trading rich; the business has to keep delivering to justify it.")
    if p >= 4 and v >= 3:
        return ("Quality at Fair Price", f"{f.symbol} is a profitable, reasonably-valued business — not flashy, but works.")
    return ("Mixed Picture", f"{f.symbol} is a mixed bag — strengths and weaknesses across the four pillars, no clear archetype.")


def _pillar_story(name: str, score: int, f: StockFundamentals, extras: dict) -> str:
    """One-line interpretation for each pillar so it reads, not just charts."""
    if name == "valuation":
        if score >= 4:
            return "Trades cheap on earnings — the market may be discounting risk you should investigate."
        if score <= 2:
            return "Premium valuation. The price assumes continued strong execution."
        return "Roughly in line with what the business produces."

    if name == "growth":
        rg = float(f.revenue_growth) if f.revenue_growth is not None else None
        eg = float(f.eps_growth) if f.eps_growth is not None else None
        if score >= 4:
            return "Top line and earnings are expanding — the engine is running hot."
        if score <= 2 and (rg is not None and rg < 0):
            return "Revenue is contracting. Need a catalyst to reverse the trend."
        if score <= 2 and (eg is not None and eg < 0):
            return "Earnings are shrinking faster than revenue — margin pressure."
        return "Moderate growth — neither a rocket nor a stall."

    if name == "profitability":
        pm = float(f.profit_margin) if f.profit_margin is not None else None
        if score >= 4:
            return f"Throws off real cash — every dollar of revenue keeps {pm:.0f}¢ as profit." if pm else "High-quality margins and strong returns on capital."
        if score <= 2:
            return "Thin margins. Operating leverage cuts both ways here."
        return "Average margins for the industry — not the differentiator."

    if name == "health":
        fcf_m = extras.get("fcf_margin_pct")
        de = float(f.debt_to_equity) if f.debt_to_equity is not None else None
        if score >= 4:
            if fcf_m and fcf_m > 0:
                return f"Strong free cash flow ({fcf_m:.0f}% of revenue) and conservative leverage."
            return "Clean balance sheet — low debt, positive cash generation."
        if score <= 2:
            if de and de > 2:
                return f"High leverage (D/E {de:.1f}) — sensitive to rates and earnings stumbles."
            return "Balance sheet warrants attention — debt or negative cash flow."
        return "Reasonable financial position — no red flags, no standout strength."

    return ""


def get_fundamentals(symbol: str, force: bool = False) -> dict:
    symbol = symbol.upper()
    cache_key = f"fundamentals_story:v1:{symbol}"
    if not force:
        cached = cache_get(cache_key)
        if cached:
            cached["from_cache"] = True
            return cached

    model, extras = _fetch_fundamentals(symbol)
    if model is None:
        return {
            "symbol": symbol, "available": False,
            "error": "Fundamentals unavailable from upstream.",
            "archetype": None, "lede": None,
            "overall_score": None,
            "pillars": [],
            "strengths": [], "weaknesses": [],
            "raw": {}, "from_cache": False,
            "last_updated": datetime.utcnow().isoformat() + "Z",
        }

    scores = fundamental_analysis.analyze(model)
    archetype, lede = _compose_story(scores, model)

    def _f(v) -> float | None:
        return float(v) if v is not None else None

    pillars = [
        {
            "name": "valuation",
            "label": "Valuation",
            "score": scores.valuation_score,
            "story": _pillar_story("valuation", scores.valuation_score, model, extras),
            "metrics": [
                {"label": "P/E (trailing)", "value": _f(model.pe_ratio), "unit": "x"},
                {"label": "PEG",            "value": _f(model.peg_ratio), "unit": "x"},
            ],
        },
        {
            "name": "growth",
            "label": "Growth",
            "score": scores.growth_score,
            "story": _pillar_story("growth", scores.growth_score, model, extras),
            "metrics": [
                {"label": "Revenue growth", "value": _f(model.revenue_growth), "unit": "%"},
                {"label": "EPS growth",     "value": _f(model.eps_growth),     "unit": "%"},
            ],
        },
        {
            "name": "profitability",
            "label": "Profitability",
            "score": scores.profitability_score,
            "story": _pillar_story("profitability", scores.profitability_score, model, extras),
            "metrics": [
                {"label": "Profit margin", "value": _f(model.profit_margin), "unit": "%"},
                {"label": "Return on equity", "value": _f(model.roe), "unit": "%"},
                {"label": "Operating margin", "value": extras.get("operating_margin_pct"), "unit": "%"},
            ],
        },
        {
            "name": "health",
            "label": "Balance Sheet",
            "score": scores.health_score,
            "story": _pillar_story("health", scores.health_score, model, extras),
            "metrics": [
                {"label": "Debt / equity",  "value": _f(model.debt_to_equity), "unit": "x"},
                {"label": "FCF margin",     "value": extras.get("fcf_margin_pct"), "unit": "%"},
                {"label": "Dividend yield", "value": _f(model.dividend_yield),  "unit": "%"},
            ],
        },
    ]

    payload = {
        "symbol": symbol,
        "available": True,
        "error": None,
        "archetype": archetype,
        "lede": lede,
        "overall_score": scores.overall_score,
        "pillars": pillars,
        "strengths": [_round_decimals_in_text(s) for s in scores.strengths],
        "weaknesses": [_round_decimals_in_text(w) for w in scores.weaknesses],
        "raw": {
            "market_cap": _f(model.market_cap),
            "sector": model.sector,
            "industry": model.industry,
        },
        "from_cache": False,
        "last_updated": datetime.utcnow().isoformat() + "Z",
    }

    try:
        cache_set(cache_key, payload, ttl_minutes=_CACHE_TTL_MINUTES)
    except Exception:
        pass
    return payload
