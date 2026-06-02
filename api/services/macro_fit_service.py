"""Macro fit service — does this stock thrive or struggle in the current regime?

Two layers:
  1. Macro regime score from src.analysis.macro.analyze() — a -2..+2 tailwind/
     headwind read on the broader environment (yield curve, VIX, Fed, etc.).
  2. Sector-level macro sensitivity — rule-based map of how each GICS sector
     historically reacts to the active regime factors (rates, growth, vol).

Combined into a per-ticker verdict: "tailwind", "headwind", "neutral", with
explanatory factors so the user understands *why*.
"""
from __future__ import annotations

from datetime import datetime

from src.analysis import macro as macro_analysis
from src.utils.db import cache_get, cache_set

_CACHE_TTL_MINUTES = 60  # macro moves slowly


# Sector sensitivities to common regime factors. Negative entries = headwind
# under that factor; positive = tailwind. Values are illustrative tilts, not
# precise betas — they describe the *direction* most analysts ascribe.
_SECTOR_TILTS: dict[str, dict[str, float]] = {
    # Sector → factor → tilt (-2..+2). Factors:
    #   "tight_monetary"      — Fed > 5% / restrictive policy
    #   "yield_curve_inverted"— recession warning
    #   "high_volatility"     — VIX > 25
    #   "strong_labor"        — unemployment < 4%
    #   "gdp_contraction"     — GDP < 0%
    "Technology":             {"tight_monetary": -1.5, "high_volatility": -1.0, "strong_labor": +0.5,  "gdp_contraction": -1.5},
    "Financial Services":     {"tight_monetary": +1.0, "yield_curve_inverted": -1.5, "gdp_contraction": -2.0},
    "Financials":             {"tight_monetary": +1.0, "yield_curve_inverted": -1.5, "gdp_contraction": -2.0},
    "Healthcare":             {"high_volatility": +0.5, "gdp_contraction": +0.5, "tight_monetary": -0.5},
    "Consumer Defensive":     {"high_volatility": +1.0, "gdp_contraction": +1.0, "strong_labor": -0.3},
    "Consumer Staples":       {"high_volatility": +1.0, "gdp_contraction": +1.0, "strong_labor": -0.3},
    "Consumer Cyclical":      {"tight_monetary": -1.5, "gdp_contraction": -2.0, "strong_labor": +1.0},
    "Consumer Discretionary": {"tight_monetary": -1.5, "gdp_contraction": -2.0, "strong_labor": +1.0},
    "Utilities":              {"tight_monetary": -1.5, "high_volatility": +0.5, "gdp_contraction": +0.5},
    "Real Estate":            {"tight_monetary": -2.0, "yield_curve_inverted": -1.0, "gdp_contraction": -1.0},
    "Energy":                 {"gdp_contraction": -1.5, "high_volatility": -0.5},
    "Materials":              {"gdp_contraction": -1.5, "strong_labor": +0.5},
    "Industrials":            {"gdp_contraction": -1.5, "strong_labor": +1.0, "tight_monetary": -0.5},
    "Communication Services": {"high_volatility": -0.5, "gdp_contraction": -1.0, "tight_monetary": -0.5},
    "Basic Materials":        {"gdp_contraction": -1.5, "strong_labor": +0.5},
}

_SECTOR_NOTES: dict[str, str] = {
    "Technology":             "Long-duration growth — sensitive to rates and risk appetite.",
    "Financial Services":     "Banks earn the spread; net-interest income climbs with rates, falls if curve inverts.",
    "Financials":             "Banks earn the spread; net-interest income climbs with rates, falls if curve inverts.",
    "Healthcare":             "Defensive demand; cash-flow stable through cycles.",
    "Consumer Defensive":     "Recession-resistant staples — bond-like in a downturn.",
    "Consumer Staples":       "Recession-resistant staples — bond-like in a downturn.",
    "Consumer Cyclical":      "Demand swings with the consumer balance sheet — rate-sensitive on the demand side.",
    "Consumer Discretionary": "Demand swings with the consumer balance sheet — rate-sensitive on the demand side.",
    "Utilities":              "Bond proxy — high leverage, high dividends; rate cuts help, hikes hurt.",
    "Real Estate":            "Bond proxy + leverage; one of the most rate-sensitive sectors.",
    "Energy":                 "Tied to oil; benefits from supply shocks, suffers in demand-led recessions.",
    "Materials":              "Cyclical — moves with global growth and the dollar.",
    "Basic Materials":        "Cyclical — moves with global growth and the dollar.",
    "Industrials":            "Cyclical — capex-driven, gains in expansion, loses in recession.",
    "Communication Services": "Mixed — telecom defensive, media/tech-adjacent cyclical.",
}


def _active_factors(snapshot) -> list[str]:
    """Translate the snapshot into a set of active regime factor keys."""
    factors: list[str] = []
    if snapshot.yield_curve_inverted:
        factors.append("yield_curve_inverted")
    if snapshot.vix is not None and snapshot.vix > 25:
        factors.append("high_volatility")
    if snapshot.fed_funds_rate is not None and snapshot.fed_funds_rate > 5:
        factors.append("tight_monetary")
    if snapshot.unemployment_rate is not None and snapshot.unemployment_rate < 4:
        factors.append("strong_labor")
    if snapshot.gdp_growth is not None and snapshot.gdp_growth < 0:
        factors.append("gdp_contraction")
    return factors


def _sector_fit(sector: str | None, factors: list[str]) -> tuple[float, list[str]]:
    """Sum sector tilts across active factors → return (sector_score, drivers)."""
    if not sector or sector not in _SECTOR_TILTS:
        return 0.0, []
    tilts = _SECTOR_TILTS[sector]
    score = 0.0
    drivers: list[str] = []
    for f in factors:
        t = tilts.get(f)
        if t is None:
            continue
        score += t
        if t >= 0.5:
            drivers.append(f"{sector} historically benefits from {f.replace('_', ' ')} (+{t:.1f})")
        elif t <= -0.5:
            drivers.append(f"{sector} historically hurt by {f.replace('_', ' ')} ({t:.1f})")
    return score, drivers


def _verdict(macro_score: int, sector_score: float) -> tuple[str, str]:
    """Combine macro + sector tilts into a single label."""
    combined = macro_score + sector_score
    if combined >= 1.5:
        return ("tailwind", "Both the macro backdrop and the sector tilt favor this stock right now.")
    if combined >= 0.5:
        return ("mild_tailwind", "Modestly positive setup — macro and sector tilts mostly support this stock.")
    if combined <= -1.5:
        return ("headwind", "Both the macro backdrop and the sector tilt work against this stock right now.")
    if combined <= -0.5:
        return ("mild_headwind", "Modestly negative setup — the regime works against this stock more than for it.")
    return ("neutral", "The current regime is broadly neutral for this stock — no strong macro tailwind or headwind.")


def _fetch_snapshot():
    """Lazy import to avoid pulling httpx etc. on cold module load."""
    from src.data.macro import MacroProvider
    return MacroProvider().get_macro_snapshot()


def _lookup_sector(symbol: str) -> str | None:
    """Best-effort sector lookup via yfinance — same source the rest of the
    app uses; failures return None and the verdict falls back to macro only.
    """
    try:
        import yfinance as yf
        info = yf.Ticker(symbol).info or {}
        return info.get("sector") or None
    except Exception:
        return None


def get_macro_fit(symbol: str, force: bool = False) -> dict:
    symbol = symbol.upper()
    cache_key = f"macro_fit:v1:{symbol}"
    if not force:
        cached = cache_get(cache_key)
        if cached:
            cached["from_cache"] = True
            return cached

    try:
        snap = _fetch_snapshot()
    except Exception as e:
        return {
            "symbol": symbol,
            "available": False,
            "reason": f"Macro snapshot unavailable: {e}",
            "regime": None, "regime_score": 0, "regime_factors": [],
            "sector": None, "sector_score": 0.0, "sector_drivers": [], "sector_note": None,
            "active_factors": [], "verdict": "neutral", "verdict_lede": None,
            "snapshot": {}, "from_cache": False,
            "last_updated": datetime.utcnow().isoformat() + "Z",
        }

    macro_score = macro_analysis.analyze(snap)
    active = _active_factors(snap)
    sector = _lookup_sector(symbol)
    sec_score, sec_drivers = _sector_fit(sector, active)
    verdict, verdict_lede = _verdict(macro_score.score, sec_score)

    snapshot_view = {
        "regime": snap.regime,
        "fed_funds_rate": float(snap.fed_funds_rate) if snap.fed_funds_rate is not None else None,
        "treasury_10y":   float(snap.treasury_10y)   if snap.treasury_10y   is not None else None,
        "treasury_2y":    float(snap.treasury_2y)    if snap.treasury_2y    is not None else None,
        "vix":            float(snap.vix)            if snap.vix            is not None else None,
        "unemployment":   float(snap.unemployment_rate) if snap.unemployment_rate is not None else None,
        "gdp_growth":     float(snap.gdp_growth)     if snap.gdp_growth     is not None else None,
        "yield_curve_inverted": snap.yield_curve_inverted,
    }

    payload = {
        "symbol": symbol,
        "available": True,
        "reason": None,
        "regime": macro_score.regime,
        "regime_score": macro_score.score,
        "regime_factors": macro_score.factors,
        "sector": sector,
        "sector_score": round(sec_score, 1),
        "sector_drivers": sec_drivers,
        "sector_note": _SECTOR_NOTES.get(sector or "", None),
        "active_factors": active,
        "verdict": verdict,
        "verdict_lede": verdict_lede,
        "snapshot": snapshot_view,
        "from_cache": False,
        "last_updated": datetime.utcnow().isoformat() + "Z",
    }

    try:
        cache_set(cache_key, payload, ttl_minutes=_CACHE_TTL_MINUTES)
    except Exception:
        pass
    return payload
