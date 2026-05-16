"""Risk-adjusted action recommendation.

Synthesizes verdict × bubble score × analyst consensus × smart money × trade plan
into a SINGLE recommended action with concrete reasoning and a wait-condition
price level when applicable. Rule-based for speed (no extra Claude call).
"""
from __future__ import annotations

from datetime import datetime

from src.utils.db import cache_get, cache_set, log_ai_decision
from api.services import (
    deep_dive_service, bubble_score_service, analyst_consensus_service,
    smart_money_service,
)

_CACHE_TTL_MINUTES = 60  # short — components update independently


def _safe(d: dict | None, *keys, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return cur if cur is not None else default


def _insider_signal(sm: dict) -> str:
    """Return 'buying' / 'selling' / 'neutral' for insider section."""
    ins = sm.get("insider") or {}
    if ins.get("cluster_buy"):
        return "buying"
    buys = ins.get("total_buys") or 0
    sells = ins.get("total_sells") or 0
    net = ins.get("net_value_usd") or 0
    if buys > sells and net > 0:
        return "buying"
    if sells > buys and net < 0:
        return "selling"
    return "neutral"


def _congress_signal(sm: dict) -> str:
    s = (_safe(sm, "congress", "net_sentiment", default="neutral") or "").lower()
    if "buy" in s or s == "bullish":
        return "buying"
    if "sell" in s or s == "bearish":
        return "selling"
    return "neutral"


def _action_label(code: str) -> str:
    return {
        "STRONG_BUY":  "Strong Buy",
        "BUY":         "Buy",
        "BUY_ON_DIP":  "Wait for Pullback",
        "HOLD":        "Hold",
        "TRIM":        "Trim Position",
        "SELL":        "Sell",
        "STRONG_SELL": "Strong Sell",
    }.get(code, code)


def _action_tone(code: str) -> str:
    return {
        "STRONG_BUY":  "strong_bullish",
        "BUY":         "bullish",
        "BUY_ON_DIP":  "cautious_bullish",
        "HOLD":        "neutral",
        "TRIM":        "cautious_bearish",
        "SELL":        "bearish",
        "STRONG_SELL": "strong_bearish",
    }.get(code, "neutral")


def get_recommendation(symbol: str, force: bool = False) -> dict:
    symbol = symbol.upper()
    cache_key = f"recommendation:v1:{symbol}"
    if not force:
        cached = cache_get(cache_key)
        if cached:
            cached["from_cache"] = True
            return cached

    # Pull components — each is independently cached
    dd     = deep_dive_service.get_deep_dive(symbol, period="3M")
    bubble = bubble_score_service.get_bubble_score(symbol)
    analyst = analyst_consensus_service.get_analyst_consensus(symbol)
    sm      = smart_money_service.get_smart_money(symbol)

    verdict     = (dd.get("verdict") or "Hold")
    risk_rating = int(dd.get("risk_rating") or 3)
    price       = dd.get("price")
    plan        = dd.get("trade_plan") or {}
    stop        = plan.get("stop")
    target1     = plan.get("target1")

    bubble_score = float(bubble.get("score") or 0)
    bubble_label = bubble.get("label") or "Fair Value"

    rating = (analyst.get("rating") or "").lower()
    upside = analyst.get("upside_pct")
    target_mean = analyst.get("target_mean")

    insider = _insider_signal(sm)
    congress = _congress_signal(sm)

    # ── Decision rules ──────────────────────────────────────────
    bullish_verdict = verdict in ("Buy", "Strong Buy")
    bearish_verdict = verdict in ("Sell", "Strong Sell")

    overpriced = bubble_score >= 70
    cheap      = bubble_score < 25

    analyst_bullish = rating in ("buy", "strong_buy")
    analyst_bearish = rating in ("sell", "strong_sell")

    confirms_bull = analyst_bullish or insider == "buying" or congress == "buying"
    confirms_bear = analyst_bearish or insider == "selling" or congress == "selling"

    # Pick the action
    if bullish_verdict and overpriced:
        action = "BUY_ON_DIP"
    elif bullish_verdict and confirms_bull and not overpriced:
        action = "STRONG_BUY"
    elif bullish_verdict:
        action = "BUY"
    elif bearish_verdict and overpriced and confirms_bear:
        action = "STRONG_SELL"
    elif bearish_verdict:
        action = "SELL"
    else:  # Hold
        if cheap and analyst_bullish:
            action = "BUY"
        elif overpriced and confirms_bear:
            action = "TRIM"
        else:
            action = "HOLD"

    # ── Build the one-line reasoning ────────────────────────────
    parts: list[str] = []
    parts.append(f"verdict {verdict}")
    parts.append(f"Bubble Score {bubble_score:.0f} ({bubble_label})")
    if rating:
        if upside is not None:
            parts.append(f"analysts {rating.replace('_', ' ')} ({upside:+.1f}% to target)")
        else:
            parts.append(f"analysts {rating.replace('_', ' ')}")
    if insider != "neutral":
        parts.append(f"insiders net {insider}")
    if congress != "neutral":
        parts.append(f"politicians net {congress}")

    reasoning = " · ".join(parts)

    # ── Wait condition for BUY_ON_DIP ───────────────────────────
    wait_until_price = None
    wait_reason = None
    if action == "BUY_ON_DIP":
        # Suggest waiting for SMA50 / stop level retest as entry
        if stop is not None and price is not None and stop < price:
            wait_until_price = round(stop * 1.02, 2)  # slight cushion above stop
            wait_reason = f"Wait for pullback to ~${wait_until_price} (just above trade-plan stop) before entering."
        elif price is not None:
            cushion = round(price * 0.93, 2)
            wait_until_price = cushion
            wait_reason = f"Wait for ~7% pullback (~${cushion}) before entering."

    # ── Re-evaluate trigger ─────────────────────────────────────
    reevaluate = None
    earnings = dd.get("earnings") or []
    if earnings:
        # Closest future earnings
        for e in earnings:
            d = e.get("date") or e.get("transaction_date")
            if d and d >= datetime.utcnow().date().isoformat():
                reevaluate = f"Re-evaluate after next earnings on {d}."
                break

    # ── Headline summary (one sentence) ─────────────────────────
    label = _action_label(action)
    if action in ("STRONG_BUY", "BUY"):
        headline = f"{label} — multiple signals align bullish."
    elif action == "BUY_ON_DIP":
        headline = f"{label} — bullish setup but valuation is stretched; better entry on weakness."
    elif action == "HOLD":
        headline = f"{label} — signals mixed; wait for clearer direction."
    elif action == "TRIM":
        headline = f"{label} — overvalued and signals deteriorating; reduce exposure."
    elif action in ("SELL", "STRONG_SELL"):
        headline = f"{label} — signals align bearish; capital better deployed elsewhere."
    else:
        headline = label

    payload = {
        "symbol":           symbol,
        "action":           action,
        "action_label":     label,
        "tone":             _action_tone(action),
        "headline":         headline,
        "reasoning":        reasoning,
        "wait_until_price": wait_until_price,
        "wait_reason":      wait_reason,
        "reevaluate":       reevaluate,
        "components": {
            "verdict":        verdict,
            "risk_rating":    risk_rating,
            "bubble_score":   bubble_score,
            "bubble_label":   bubble_label,
            "analyst_rating": rating or None,
            "analyst_upside": upside,
            "analyst_target": target_mean,
            "insider":        insider,
            "congress":       congress,
            "price":          price,
        },
        "last_updated":     datetime.utcnow().isoformat() + "Z",
        "from_cache":       False,
    }

    try:
        cache_set(cache_key, payload, ttl_minutes=_CACHE_TTL_MINUTES)
    except Exception:
        pass

    # Track for accuracy grading. Only log fresh computations (cache hits return
    # earlier above), and only when we have a price to anchor the call to.
    if price is not None:
        log_ai_decision(
            symbol, "recommendation", action, float(price),
            score=bubble_score,
            context={
                "verdict": verdict,
                "bubble_score": bubble_score,
                "bubble_label": bubble_label,
                "analyst_rating": rating or None,
                "analyst_upside": upside,
                "insider": insider,
                "congress": congress,
            },
            prediction_window_days=30,
        )

    return payload
