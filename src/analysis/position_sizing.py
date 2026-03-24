"""Position sizing calculators. Pure computation, no I/O."""

import math


def fixed_risk(account: float, risk_pct: float, entry: float, stop: float) -> dict:
    """Calculate position size based on fixed percentage risk.

    Args:
        account: Total account value ($).
        risk_pct: Max risk per trade (e.g. 1.0 = 1%).
        entry: Entry price.
        stop: Stop loss price.
    """
    if entry <= 0 or stop <= 0 or account <= 0 or risk_pct <= 0:
        return {"shares": 0, "position_value": 0, "risk_amount": 0, "error": "Invalid inputs"}

    risk_per_share = abs(entry - stop)
    if risk_per_share == 0:
        return {"shares": 0, "position_value": 0, "risk_amount": 0, "error": "Entry = Stop"}

    risk_amount = account * (risk_pct / 100)
    shares = int(risk_amount / risk_per_share)
    position_value = shares * entry

    return {
        "shares": shares,
        "position_value": round(position_value, 2),
        "risk_amount": round(risk_amount, 2),
        "risk_per_share": round(risk_per_share, 2),
        "pct_of_account": round((position_value / account) * 100, 1),
    }


def kelly_criterion(win_rate: float, avg_win: float, avg_loss: float) -> dict:
    """Kelly Criterion for optimal position sizing.

    Args:
        win_rate: Historical win rate (0-1).
        avg_win: Average winning trade return (%).
        avg_loss: Average losing trade return (%, positive number).
    """
    if avg_loss == 0 or win_rate <= 0 or win_rate >= 1:
        return {"kelly_pct": 0, "half_kelly_pct": 0}

    b = avg_win / avg_loss  # win/loss ratio
    q = 1 - win_rate

    kelly = (win_rate * b - q) / b
    kelly = max(0, min(kelly, 1))  # clamp 0-100%

    return {
        "kelly_pct": round(kelly * 100, 1),
        "half_kelly_pct": round(kelly * 50, 1),  # conservative
        "win_loss_ratio": round(b, 2),
        "expectancy": round(win_rate * avg_win - q * avg_loss, 2),
    }


def atr_stop(entry: float, atr: float, multiplier: float = 2.0, direction: str = "long") -> dict:
    """Calculate stop loss based on ATR.

    Args:
        entry: Entry price.
        atr: Average True Range value.
        multiplier: ATR multiplier (default 2.0).
        direction: "long" or "short".
    """
    distance = atr * multiplier
    if direction == "long":
        stop = entry - distance
    else:
        stop = entry + distance

    return {
        "stop_loss": round(stop, 2),
        "distance": round(distance, 2),
        "distance_pct": round((distance / entry) * 100, 2),
    }
