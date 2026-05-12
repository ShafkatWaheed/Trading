"""Economic calendar — FOMC, CPI, NFP, GDP, plus watchlist earnings."""
from __future__ import annotations

from datetime import datetime, timedelta


# 2026 FOMC meeting dates (publicly announced schedule; static).
FOMC_DATES = [
    "2026-01-29", "2026-03-19", "2026-05-07", "2026-06-18",
    "2026-07-29", "2026-09-17", "2026-11-05", "2026-12-17",
]


def _next_recurring(month_offset_max: int, day_of_month: int) -> list[str]:
    """Next N monthly dates starting from current month."""
    now = datetime.utcnow()
    out = []
    for m_offset in range(month_offset_max):
        m = now.month + m_offset
        y = now.year
        if m > 12:
            m -= 12
            y += 1
        out.append(f"{y}-{m:02d}-{day_of_month:02d}")
    return out


def _gdp_dates() -> list[str]:
    """Quarterly GDP releases: late Jan, Apr, Jul, Oct."""
    y = datetime.utcnow().year
    out = []
    for yr in (y, y + 1):
        out.extend([f"{yr}-01-30", f"{yr}-04-30", f"{yr}-07-30", f"{yr}-10-30"])
    return out


def _watchlist_earnings(now: datetime, days_window: int) -> list[dict]:
    """Pull next earnings dates for watchlist symbols (cached/best-effort)."""
    from src.utils.db import get_watchlist
    from src.data.gateway import DataGateway

    out = []
    try:
        watchlist = get_watchlist()
    except Exception:
        return out
    if not watchlist:
        return out

    gw = DataGateway()
    for w in watchlist[:10]:
        symbol = w.get("symbol")
        if not symbol:
            continue
        try:
            earnings = gw.get_earnings_calendar(symbol)
        except Exception:
            continue
        if not earnings:
            continue
        for e in earnings[:1]:
            e_date = e.get("date") or ""
            if len(e_date) < 10:
                continue
            try:
                dt = datetime.strptime(e_date[:10], "%Y-%m-%d")
            except Exception:
                continue
            days = (dt - now).days
            if days < -1 or days > days_window:
                continue
            out.append({
                "date": e_date[:10],
                "name": f"{symbol} Earnings",
                "icon": "💰",
                "category": "earnings",
                "impact": "high" if days <= 7 else "medium",
                "days_away": days,
                "warning": (
                    "Expect 5-15% move. Consider options or reduced size."
                    if days <= 5 else ""
                ),
            })
    return out


def get_economic_calendar(days_window: int = 60, limit: int = 12) -> dict:
    """Return upcoming high-impact events sorted by days away."""
    now = datetime.utcnow()
    events: list[dict] = []

    # FOMC meetings
    for d in FOMC_DATES:
        try:
            dt = datetime.strptime(d, "%Y-%m-%d")
        except Exception:
            continue
        days = (dt - now).days
        if days < -1 or days > days_window:
            continue
        events.append({
            "date": d,
            "name": "FOMC Rate Decision",
            "icon": "%",
            "category": "fed",
            "impact": "high",
            "days_away": days,
            "warning": (
                "Expect significant volatility. Reduce position sizes day-of."
                if days <= 3 else ""
            ),
        })

    # CPI (10th of month, 3 months out)
    for d in _next_recurring(3, 10):
        try:
            dt = datetime.strptime(d, "%Y-%m-%d")
        except Exception:
            continue
        days = (dt - now).days
        if days < -1 or days > days_window:
            continue
        events.append({
            "date": d,
            "name": "CPI Inflation Data",
            "icon": "📊",
            "category": "cpi",
            "impact": "high",
            "days_away": days,
            "warning": (
                "Inflation surprise can move all stocks. Watch bond yields."
                if days <= 3 else ""
            ),
        })

    # NFP (1st Friday of month, approximated 7th)
    for d in _next_recurring(3, 7):
        try:
            dt = datetime.strptime(d, "%Y-%m-%d")
        except Exception:
            continue
        days = (dt - now).days
        if days < -1 or days > days_window:
            continue
        events.append({
            "date": d,
            "name": "Jobs Report (NFP)",
            "icon": "👥",
            "category": "jobs",
            "impact": "high",
            "days_away": days,
            "warning": (
                "Strong jobs = rates stay high (bearish growth). Weak jobs = rate cut hopes (bullish)."
                if days <= 3 else ""
            ),
        })

    # GDP (quarterly)
    for d in _gdp_dates():
        try:
            dt = datetime.strptime(d, "%Y-%m-%d")
        except Exception:
            continue
        days = (dt - now).days
        if days < -1 or days > days_window:
            continue
        events.append({
            "date": d,
            "name": "GDP Report",
            "icon": "🏭",
            "category": "gdp",
            "impact": "medium",
            "days_away": days,
            "warning": "",
        })

    # Watchlist earnings
    events.extend(_watchlist_earnings(now, days_window))

    events.sort(key=lambda x: x["days_away"])

    # Most-imminent high-impact event for the "Next 24h" pill
    high_impact = [e for e in events if e.get("impact") == "high" and e.get("days_away", 999) >= 0]
    next_high_impact = high_impact[0] if high_impact else None

    # The most-imminent ANY event (for the broader "next" callout)
    upcoming = [e for e in events if e.get("days_away", 999) >= 0]
    next_event = upcoming[0] if upcoming else None

    return {
        "events": events[:limit],
        "next_event": next_event,
        "next_high_impact": next_high_impact,
        "last_updated": now.isoformat() + "Z",
    }
