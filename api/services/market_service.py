"""Market service: rich Market Pulse payload — macro, sectors, regime, advice."""
from __future__ import annotations

from datetime import datetime
from src.data.gateway import DataGateway


_PERIOD_MAP = {"1D": "1d", "1W": "5d", "1M": "1mo", "3M": "3mo", "6M": "6mo", "1Y": "1y"}


# ── Per-metric "WHY" explanations ────────────────────────────────


def _fed_card(v: float) -> dict:
    if v > 5:
        why = "Rates above 5% squeeze corporate borrowing and slow growth. High-debt companies suffer most. Favor cash-rich value stocks."
        status, tone = "Restrictive", "red"
    elif v > 3:
        why = "Moderate rates — balanced policy. Both growth and value stocks can perform. Watch for next Fed meeting signals."
        status, tone = "Moderate", "amber"
    else:
        why = "Low rates fuel borrowing and expansion. Growth stocks and real estate typically outperform. Risk appetite is high."
        status, tone = "Accommodative", "green"
    return {"name": "Fed Funds Rate", "value": f"{v:.2f}%", "status": status, "tone": tone, "why": why, "icon": "bank"}


def _vix_card(v: float) -> dict:
    if v > 30:
        why = "Extreme fear — large price swings expected. Options expensive. Consider hedging or waiting for volatility to settle."
        status, tone = "Extreme Fear", "red"
    elif v > 20:
        why = "Elevated uncertainty — markets pricing in risk events. Tighten stops and reduce position sizes."
        status, tone = "Elevated", "amber"
    else:
        why = "Calm markets — low implied volatility. Good environment for trend-following strategies. Options cheap for protection."
        status, tone = "Calm", "green"
    return {"name": "VIX", "value": f"{v:.1f}", "status": status, "tone": tone, "why": why, "icon": "activity"}


def _unemp_card(v: float) -> dict:
    if v > 6:
        why = "Labor market weakening — consumers cut spending, earnings forecasts drop. Defensive sectors (utilities, healthcare, staples) outperform."
        status, tone = "Weakening", "red"
    elif v < 4.5:
        why = "Healthy job market — consumer spending supports corporate earnings. Broad market exposure reasonable."
        status, tone = "Strong", "green"
    else:
        why = "Mixed signals — employment softening but not alarming. Watch for acceleration in claims data."
        status, tone = "Mixed", "amber"
    return {"name": "Unemployment", "value": f"{v:.1f}%", "status": status, "tone": tone, "why": why, "icon": "users"}


def _t10y_card(v: float) -> dict:
    if v > 4.5:
        why = "High yields compete with stocks for capital. Growth stocks with high P/E ratios most vulnerable. Bonds become attractive."
        status, tone = "Rising", "red"
    elif v > 3:
        why = "Moderate yields — stocks still competitive but high-valuation names face pressure. Balance growth and value."
        status, tone = "Moderate", "amber"
    else:
        why = "Low yields push investors into stocks for returns. Risk assets rally. Growth stocks benefit most."
        status, tone = "Low", "green"
    return {"name": "10Y Treasury", "value": f"{v:.2f}%", "status": status, "tone": tone, "why": why, "icon": "trending"}


def _gdp_card(v: float) -> dict:
    if v > 2:
        why = "Strong economic expansion — corporate revenues growing. Cyclical stocks (industrials, consumer discretionary, tech) typically lead."
        status, tone = "Expanding", "green"
    elif v > 0:
        why = "Growth slowing but still positive. Late-cycle dynamics — focus on quality and profitability over pure growth."
        status, tone = "Slowing", "amber"
    else:
        why = "Economy shrinking — earnings under pressure across sectors. Cash, treasuries, defensive stocks safer. Avoid high-beta names."
        status, tone = "Contracting", "red"
    return {"name": "GDP Growth", "value": f"{v:.1f}%", "status": status, "tone": tone, "why": why, "icon": "factory"}


def _cpi_card(v: float) -> dict:
    if v > 4:
        why = "High inflation erodes purchasing power and forces the Fed to raise rates. Commodities and real assets outperform."
        status, tone = "Hot", "red"
    elif v > 2.5:
        why = "Moderate inflation — the Fed is watching closely. Companies with pricing power (strong brands, monopolies) handle this best."
        status, tone = "Above target", "amber"
    else:
        why = "Low inflation — Goldilocks zone for stocks. The Fed may ease policy, supporting equity valuations across the board."
        status, tone = "Controlled", "green"
    return {"name": "Inflation (CPI YoY)", "value": f"{v:.1f}%", "status": status, "tone": tone, "why": why, "icon": "dollar"}


def _t2y_card(v: float) -> dict:
    return {"name": "2Y Treasury", "value": f"{v:.2f}%", "status": None, "tone": "neutral", "why": None, "icon": "trending"}


# ── Regime detection ─────────────────────────────────────────────


def _regime(snapshot) -> tuple[str, str]:
    """Return (regime_label, explanation)."""
    if not snapshot:
        return "Unknown", "No macro data available."

    # Pull fields safely
    def _f(name):
        v = getattr(snapshot, name, None)
        try:
            return float(v) if v is not None else None
        except Exception:
            return None

    t10y = _f("treasury_10y")
    t2y = _f("treasury_2y")
    vix = _f("vix")
    fed = _f("fed_funds_rate")
    cpi = _f("cpi_yoy")
    inverted = getattr(snapshot, "yield_curve_inverted", False)

    if inverted or (t10y is not None and t2y is not None and t2y > t10y):
        return "⚠ Recession Warning", (
            "Inverted yield curve — 2Y above 10Y. Historically precedes recession by 6-18 months. "
            "Rotate to defensive sectors (utilities, healthcare, consumer staples), raise cash, avoid cyclicals."
        )

    if vix is not None and vix > 25:
        return "High Volatility", (
            f"VIX at {vix:.1f} — markets pricing in significant uncertainty. "
            "Tighten stops, reduce position sizes, and consider hedging with protective puts."
        )

    if fed is not None and fed > 5 and cpi is not None and cpi > 4:
        return "Tight Monetary Policy", (
            "Fed restrictive while inflation runs hot. High-debt companies suffer most. "
            "Favor cash-rich value stocks and pricing-power names over speculative growth."
        )

    return "Normal Market Conditions", (
        "Macro indicators within typical ranges. Standard portfolio construction with diversification "
        "across growth, value, and defensive names works well."
    )


# ── Trading implications ─────────────────────────────────────────


def _trading_implications(snapshot, flows: list[dict], period: str) -> list[dict]:
    """Build a list of actionable bullet points based on macro + sector flows."""
    out = []

    def _f(name):
        v = getattr(snapshot, name, None) if snapshot else None
        try:
            return float(v) if v is not None else None
        except Exception:
            return None

    vix = _f("vix")
    if vix is not None:
        if vix > 30:
            out.append({"tone": "red", "text": f"VIX at {vix:.1f} (extreme fear) — reduce position sizes to 50% of normal. Selling premium strategies have an edge."})
        elif vix > 20:
            out.append({"tone": "amber", "text": f"VIX at {vix:.1f} (elevated) — tighten stops, hedge with protective puts."})
        else:
            out.append({"tone": "green", "text": f"VIX at {vix:.1f} (calm) — favors trend-following and breakouts. Options cheap for protection."})

    fed = _f("fed_funds_rate")
    if fed is not None:
        if fed > 5:
            out.append({"tone": "red", "text": f"Fed at {fed:.2f}% (restrictive) — avoid high-debt names. Value stocks with strong free cash flow outperform."})
        elif fed > 3.5:
            out.append({"tone": "amber", "text": f"Fed at {fed:.2f}% (moderate) — watch direction. Pause favors growth, hikes favor value."})
        else:
            out.append({"tone": "green", "text": f"Fed at {fed:.2f}% (accommodative) — cheap money fuels expansion. Growth and REITs benefit most."})

    spread = _f("yield_spread_10y2y")
    if getattr(snapshot, "yield_curve_inverted", False):
        spread_str = f"{spread:+.2f}%" if spread is not None else "—"
        out.append({"tone": "red", "text": f"Yield curve inverted ({spread_str}) — bond market pricing in recession. Rotate defensive."})
    elif spread is not None:
        if spread < 0.3:
            out.append({"tone": "amber", "text": f"Yield curve flattening ({spread:+.2f}% spread) — start building defensive positions."})
        else:
            out.append({"tone": "green", "text": f"Yield curve normal ({spread:+.2f}% spread) — no recession signal from bonds."})

    gdp = _f("gdp_growth")
    if gdp is not None:
        if gdp > 3:
            out.append({"tone": "green", "text": f"GDP growing {gdp:.1f}% — strong expansion. Cyclical stocks have earnings tailwinds. Small-caps often lead."})
        elif gdp > 0:
            out.append({"tone": "amber", "text": f"GDP growing {gdp:.1f}% (slowing) — late cycle. Quality over quantity, strong balance sheets."})
        else:
            out.append({"tone": "red", "text": f"GDP at {gdp:.1f}% (contracting) — raise cash 30-50%. Defensive sectors only."})

    cpi = _f("cpi_yoy")
    if cpi is not None and cpi > 5:
        out.append({"tone": "red", "text": f"Inflation {cpi:.1f}% (hot) — Fed stays restrictive. Commodities, energy, pricing-power names favored."})
    elif cpi is not None and cpi > 3:
        out.append({"tone": "amber", "text": f"Inflation {cpi:.1f}% (sticky) — above 2% target. Strong-brand companies handle this best."})

    if flows:
        sorted_flows = sorted(flows, key=lambda f: f.get("change_pct", 0), reverse=True)
        gaining = [f for f in flows if f.get("change_pct", 0) > 0]
        losing = [f for f in flows if f.get("change_pct", 0) < 0]
        period_name = period or "this period"

        if sorted_flows[:2] and sorted_flows[0].get("change_pct", 0) > 0:
            top = sorted_flows[:2]
            out.append({
                "tone": "green",
                "text": f"Capital flowing into {top[0]['sector']} ({top[0]['change_pct']:+.1f}%) and {top[1]['sector']} ({top[1]['change_pct']:+.1f}%) over {period_name}. Look for leading stocks here.",
            })

        if sorted_flows[-2:] and sorted_flows[-1].get("change_pct", 0) < 0:
            bot = sorted_flows[-2:]
            out.append({
                "tone": "red",
                "text": f"Money rotating out of {bot[-1]['sector']} ({bot[-1]['change_pct']:+.1f}%) and {bot[-2]['sector']} ({bot[-2]['change_pct']:+.1f}%). Avoid new entries; tighten stops on existing.",
            })

        if len(gaining) >= 8:
            out.append({"tone": "green", "text": f"Broad strength — {len(gaining)}/{len(flows)} sectors positive. Risk-on mode."})
        elif len(losing) >= 8:
            out.append({"tone": "red", "text": f"Broad weakness — {len(losing)}/{len(flows)} sectors red. Risk-off mode."})

    return out


# ── Yield curve summary ──────────────────────────────────────────


def _yield_curve(snapshot) -> dict | None:
    if not snapshot:
        return None
    def _f(name):
        v = getattr(snapshot, name, None)
        try:
            return float(v) if v is not None else None
        except Exception:
            return None
    t2y = _f("treasury_2y")
    t10y = _f("treasury_10y")
    spread = _f("yield_spread_10y2y")
    if t2y is None or t10y is None:
        return None
    inverted = bool(getattr(snapshot, "yield_curve_inverted", False)) or (t2y > t10y)
    return {
        "two_year": t2y,
        "ten_year": t10y,
        "spread": spread if spread is not None else (t10y - t2y),
        "inverted": inverted,
        "label": "Inverted" if inverted else ("Flattening" if (spread is not None and spread < 0.3) else "Normal"),
    }


# ── Sector summary ───────────────────────────────────────────────


_SECTOR_ETFS = {
    "Technology": "XLK", "Healthcare": "XLV", "Financials": "XLF",
    "Consumer Discretionary": "XLY", "Consumer Staples": "XLP",
    "Energy": "XLE", "Industrials": "XLI", "Real Estate": "XLRE",
    "Utilities": "XLU", "Materials": "XLB", "Communication Services": "XLC",
}

# Period → (sessions for current window, sessions for prior window)
_PERIOD_TO_SESSIONS = {
    "1D": (1, 1),   # too short for meaningful delta
    "1W": (5, 5),
    "1M": (21, 21),
    "3M": (63, 63),
    "6M": (126, 126),
    "1Y": (252, 252),
}


def _attach_sector_deltas(flows: list[dict], period_key: str) -> None:
    """Mutate `flows` in place, adding `change_pct_prior`, `delta_pp`, and
    `accel` ('accelerating' | 'decelerating' | 'steady') per sector."""
    if not flows:
        return
    cur_sessions, prior_sessions = _PERIOD_TO_SESSIONS.get(period_key, (21, 21))
    if cur_sessions <= 1:
        return  # 1D too short

    try:
        import yfinance as yf
        tickers = list(_SECTOR_ETFS.values())
        # We need 2× the window for prior-period math, plus headroom.
        lookback_days = (cur_sessions + prior_sessions + 5) * 1.6  # buffer for weekends
        period = "6mo"  # safe coverage for up to 1Y windows? no — bump if needed
        if cur_sessions + prior_sessions > 100:
            period = "1y"
        if cur_sessions + prior_sessions > 200:
            period = "2y"

        df = yf.download(
            tickers, period=period, interval="1d",
            progress=False, auto_adjust=True, group_by="ticker", threads=False,
        )

        def _series(tkr: str):
            try:
                if df.columns.nlevels > 1 and tkr in df.columns.get_level_values(0):
                    return df[tkr]["Close"].dropna().astype(float).tolist()
            except Exception:
                pass
            return []

        # Build sector→prior_pct map
        prior_map: dict[str, float | None] = {}
        for sector, ticker in _SECTOR_ETFS.items():
            closes = _series(ticker)
            n = len(closes)
            needed = cur_sessions + prior_sessions + 1
            if n < needed:
                prior_map[sector] = None
                continue
            # last index of prior window = n - cur_sessions
            prior_end   = closes[n - cur_sessions - 1]
            prior_start = closes[n - cur_sessions - prior_sessions - 1]
            if prior_start <= 0:
                prior_map[sector] = None
                continue
            prior_map[sector] = round(((prior_end - prior_start) / prior_start) * 100.0, 2)

        for s in flows:
            sector = s.get("sector")
            prior = prior_map.get(sector)
            s["change_pct_prior"] = prior
            if prior is None:
                s["delta_pp"] = None
                s["accel"] = None
                continue
            current = float(s.get("change_pct", 0))
            delta = round(current - prior, 2)
            s["delta_pp"] = delta
            if delta > 1.0:
                s["accel"] = "accelerating"
            elif delta < -1.0:
                s["accel"] = "decelerating"
            else:
                s["accel"] = "steady"
    except Exception:
        return


def _sector_summary(flows: list[dict]) -> dict:
    if not flows:
        return {"net": 0.0, "inflow": 0.0, "outflow": 0.0, "gaining": 0, "losing": 0, "total": 0}
    inflow = sum(f.get("change_pct", 0) for f in flows if f.get("change_pct", 0) > 0)
    outflow = sum(f.get("change_pct", 0) for f in flows if f.get("change_pct", 0) < 0)
    return {
        "net": inflow + outflow,
        "inflow": inflow,
        "outflow": outflow,
        "gaining": len([f for f in flows if f.get("change_pct", 0) > 0]),
        "losing": len([f for f in flows if f.get("change_pct", 0) < 0]),
        "total": len(flows),
    }


# ── Public entry point ───────────────────────────────────────────


def get_pulse(period: str = "1M") -> dict:
    """Return a rich 'Market Pulse' payload."""
    period_key = period if period in _PERIOD_MAP else "1M"
    yf_period = _PERIOD_MAP[period_key]

    gw = DataGateway()
    snapshot = None
    flows: list[dict] = []
    try:
        snapshot = gw.get_macro_snapshot()
    except Exception:
        pass
    try:
        flows = gw.get_sector_flows(yf_period) or []
    except Exception:
        pass

    # Build KPI cards with explanations
    kpis: list[dict] = []
    if snapshot:
        def _f(name):
            v = getattr(snapshot, name, None)
            try:
                return float(v) if v is not None else None
            except Exception:
                return None

        builders = [
            ("fed_funds_rate", _fed_card),
            ("vix", _vix_card),
            ("unemployment_rate", _unemp_card),
            ("treasury_10y", _t10y_card),
            ("treasury_2y", _t2y_card),
            ("gdp_growth", _gdp_card),
            ("cpi_yoy", _cpi_card),
        ]
        for attr, fn in builders:
            v = _f(attr)
            if v is not None:
                try:
                    kpis.append(fn(v))
                except Exception:
                    continue

    regime, explanation = _regime(snapshot)

    sector_flows = []
    for s in flows:
        try:
            change = float(s.get("change_pct", 0))
            sector_flows.append({
                "sector": s.get("sector", "Unknown"),
                "change_pct": change,
                "flow": "inflow" if change >= 0 else "outflow",
            })
        except Exception:
            continue

    # ── Sector rotation deltas — compare current period vs prior period of
    #    same length to detect accelerating / decelerating sectors.
    try:
        _attach_sector_deltas(sector_flows, period_key)
    except Exception:
        pass

    return {
        "regime": regime,
        "regime_explanation": explanation,
        "kpis": kpis,
        "yield_curve": _yield_curve(snapshot),
        "sectors": sector_flows,
        "sector_summary": _sector_summary(sector_flows),
        "implications": _trading_implications(snapshot, sector_flows, period_key),
        "period": period_key,
        "available_periods": list(_PERIOD_MAP.keys()),
        "last_updated": datetime.utcnow().isoformat() + "Z",
    }
