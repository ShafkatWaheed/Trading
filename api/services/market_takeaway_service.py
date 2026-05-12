"""One-sentence "what does the market favor today" synthesis.

Reads the existing market pulse + dashboard payloads and applies a small rule
set to generate a headline + 2-3 bullet positioning notes. No Claude call —
this needs to be fast since it's at the top of the home page.
"""
from __future__ import annotations

from datetime import datetime

from src.utils.db import cache_get, cache_set
from api.services import market_dashboard_service, market_service

_CACHE_TTL_MINUTES = 15


def _stance_from_regime(regime: str | None, vix_regime: str | None,
                       spy_pct_50d: float | None) -> tuple[str, str]:
    """Return (stance, tone) tone = 'bullish'|'cautious'|'defensive'|'neutral'."""
    r = (regime or "").lower()
    v = (vix_regime or "").lower()

    if v == "panic":
        return ("defensive — preserve capital, wait for stabilization", "defensive")
    if v == "stressed":
        return ("cautious — reduce position size, prefer quality", "cautious")
    if "risk-on" in r or "expansion" in r or "bull" in r:
        if v == "calm" and (spy_pct_50d or 0) > 0:
            return ("favors adding risk — momentum is in", "bullish")
        return ("constructive but not aggressive", "cautious_bullish")
    if "risk-off" in r or "recession" in r or "bear" in r:
        return ("defensive — keep dry powder", "defensive")
    return ("neutral — wait for a setup", "neutral")


def get_market_takeaway(force: bool = False) -> dict:
    cache_key = "market_takeaway:v1"

    if not force:
        cached = cache_get(cache_key)
        if cached:
            cached["from_cache"] = True
            return cached

    # Pull pieces — each independently cached
    try:
        dash = market_dashboard_service.get_market_dashboard()
    except Exception:
        dash = {}
    try:
        pulse = market_service.market_pulse(period="1M") if hasattr(market_service, "market_pulse") else {}
    except Exception:
        pulse = {}

    breadth = dash.get("breadth") or {}
    indices = {i["key"]: i for i in (dash.get("indices") or [])}

    spx_change = (indices.get("spx") or {}).get("change_pct")
    vix_level  = breadth.get("vix_level")
    vix_regime = breadth.get("vix_regime")
    spy_50d    = breadth.get("spy_pct_above_50d")
    spy_200d   = breadth.get("spy_pct_above_200d")

    regime = (pulse.get("regime") or {}).get("label") if isinstance(pulse, dict) else None
    if not regime:
        # Derive a quick regime from VIX + SPY trend
        if vix_regime == "panic":
            regime = "Risk-off"
        elif vix_regime in ("stressed",):
            regime = "Defensive"
        elif (spy_200d or 0) > 0 and vix_regime in ("calm", "normal"):
            regime = "Risk-on"
        else:
            regime = "Mixed"

    stance, tone = _stance_from_regime(regime, vix_regime, spy_50d)

    # Build evidence bullets
    bullets: list[str] = []
    if vix_level is not None and vix_regime:
        bullets.append(
            f"VIX at {vix_level:.0f} — {vix_regime} volatility regime."
        )
    if spy_50d is not None:
        bullets.append(
            f"S&P 500 is {abs(spy_50d):.1f}% {'above' if spy_50d >= 0 else 'below'} its 50-day moving average."
        )
    if breadth.get("spy_vs_rsp_1m_pp") is not None:
        pp = breadth["spy_vs_rsp_1m_pp"]
        if pp > 1.5:
            bullets.append(
                f"Rally is narrow — cap-weighted SPY beating equal-weighted RSP by {pp:.1f} pp over 1M (mega-caps leading)."
            )
        elif pp < -1.5:
            bullets.append(
                f"Rally is broad — equal-weighted RSP beating SPY by {abs(pp):.1f} pp over 1M (healthy participation)."
            )
    if breadth.get("iwm_vs_spy_1m_pp") is not None and breadth["iwm_vs_spy_1m_pp"] < -3:
        bullets.append(
            f"Small caps lagging — IWM trailing SPY by {abs(breadth['iwm_vs_spy_1m_pp']):.1f} pp over 1M."
        )

    # Headline
    spx_part = f"S&P {('+' if (spx_change or 0) >= 0 else '')}{spx_change:.1f}% today" if spx_change is not None else "Market mixed"
    headline = f"{regime} regime — {spx_part}, {breadth.get('headline') or 'mixed signals'}."

    payload = {
        "regime":   regime,
        "stance":   stance,
        "tone":     tone,
        "headline": headline,
        "bullets":  bullets[:4],
        "last_updated": datetime.utcnow().isoformat() + "Z",
        "from_cache": False,
    }

    try:
        cache_set(cache_key, payload, ttl_minutes=_CACHE_TTL_MINUTES)
    except Exception:
        pass
    return payload
