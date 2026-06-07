"""Pure option trade-plan math: entry / stop / target / R:R from technicals.

Per CLAUDE.md: analysis layer is pure -- input values, output a dict. No I/O,
no imports from data/reports/app. Money is Decimal. Returns null levels rather
than dividing by zero or fabricating a target.
"""
from __future__ import annotations

from decimal import Decimal


def build_trade_plan(
    *,
    direction: str,
    price: Decimal,
    atr: Decimal | None,
    support: Decimal | None,
    resistance: Decimal | None,
    atr_mult: Decimal = Decimal("2"),
    rr_fallback: Decimal = Decimal("2"),
) -> dict:
    """Compute a directional trade plan.

    direction: "bullish" (target above, stop below) or "bearish" (mirror).
    Returns keys: direction, entry, stop_loss, take_profit, technical_target,
    rr_ratio, rr_basis. stop_loss/take_profit/rr_ratio are None when ATR is
    missing/non-positive (cannot place a stop). rr_basis is "technical" when the
    target is a real S/R level, "ratio" when it falls back to a fixed R:R, or
    None when levels are null.
    """
    plan = {
        "direction": direction,
        "entry": price,
        "stop_loss": None,
        "take_profit": None,
        "technical_target": None,
        "rr_ratio": None,
        "rr_basis": None,
    }
    if atr is None or atr <= 0:
        return plan

    if direction == "bearish":
        stop = price + atr_mult * atr
        tech = support if (support is not None and support < price) else None
        target = tech if tech is not None else price - rr_fallback * (stop - price)
        risk = stop - price
        reward = price - target
    else:  # bullish (default)
        stop = price - atr_mult * atr
        tech = resistance if (resistance is not None and resistance > price) else None
        target = tech if tech is not None else price + rr_fallback * (price - stop)
        risk = price - stop
        reward = target - price

    plan["stop_loss"] = stop
    plan["take_profit"] = target
    plan["technical_target"] = tech
    plan["rr_basis"] = "technical" if tech is not None else "ratio"
    if risk and risk != 0:
        plan["rr_ratio"] = round(float(reward / risk), 2)
    return plan
