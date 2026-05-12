"""AI Analyst — walk-forward backtest with REAL historical context per cycle.

Two modes:
  - "single": one Claude call per cycle (fast, baseline)
  - "multi": 5 personality agents per cycle + majority vote (richer)

Data sources used at each cycle date (no look-ahead leak):
  - VIX, 10Y, 5Y treasuries, S&P 500   → yfinance ^VIX, ^TNX, ^FVX, ^GSPC
  - Sector ETF vs SPY (relative perf)   → yfinance sector ETFs (XLK, XLV, …)
  - Stock indicators                    → computed from price up to cycle date
  - Opportunity score                   → recomputed at each cycle from sliced
                                          history (technicals only)
  - Trailing P/E                        → quarterly EPS (yfinance)
  - News sentiment                      → Polygon news (date-filtered) when
                                          POLYGON_API_KEY is set; momentum proxy otherwise
"""
from __future__ import annotations

import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from src.analysis.backtester import _compute_indicators
from src.data.gateway import DataGateway
from src.utils.db import cache_get, cache_set
from api.constants import PERIOD_DAYS as _PERIOD_DAYS


_MAX_PARALLEL = 4

# Multi-mode runs all personalities within a single cycle simultaneously.
# Setting this to len(_MULTI_AGENTS) avoids the 2-batch wait that doubles
# per-cycle latency. Bumping higher than agent count has no effect.
_PARALLEL_PERSONALITIES = 7

# All 8 personality agents — same lineup as the live AI Agent.
# For the data-driven ones we can't fully backfill, the prompt tells them
# explicitly that their preferred data is missing.
_MULTI_AGENTS = [
    "momentum", "value", "contrarian", "macro",   # opinion-based (full data)
    "disruption",                                  # sector ETF perf
    "insider",                                     # SEC EDGAR + Capitol Trades
    "flow",                                        # FINRA daily short volume
]

# Agents whose preferred data we cannot fully backfill for free.
# Currently empty — Options Whisperer was removed because per-stock historical
# options flow requires Polygon's paid plan ($199/mo) and free alternatives
# (CBOE CSV, Yahoo ^CPC) are blocked or delisted.
_DATA_GAPS: dict[str, str] = {}


# ── Subprocess + parsing ──────────────────────────────────────────


def _ask_claude(prompt: str) -> str | None:
    try:
        env = os.environ.copy()
        env.pop("CLAUDECODE", None)
        proc = subprocess.run(
            ["claude", "-p", prompt, "--model", "haiku", "--allowedTools", ""],
            capture_output=True, text=True, timeout=45, env=env,
        )
        if proc.returncode != 0:
            return None
        return (proc.stdout or "").strip()
    except Exception:
        return None


def _decision_from_text(text: str | None) -> str:
    if not text:
        return "HOLD"
    t = text.upper()
    if "STRONG BUY" in t or "BUY" in t:
        return "BUY"
    if "STRONG SELL" in t or "SELL" in t:
        return "SELL"
    return "HOLD"


def _decision_and_reason(text: str | None) -> tuple[str, str]:
    """Parse `DECISION | REASON` (or just `DECISION`).

    Returns (decision, reason). Reason may be "" if the model didn't include one.
    """
    if not text:
        return "HOLD", ""
    cleaned = text.strip()
    # Try the structured form first
    if "|" in cleaned:
        head, _, rest = cleaned.partition("|")
        decision = _decision_from_text(head)
        reason = rest.strip()
        # Trim trailing punctuation / quotes / leading bullets
        reason = reason.lstrip("-•:* \t").rstrip(' "\'')
        return decision, reason[:200]
    # Fallback: just classify the text
    return _decision_from_text(cleaned), ""


# ── Series helpers ────────────────────────────────────────────────


def _series_at(indicators: dict, name: str, idx: int) -> float | None:
    arr = indicators.get(name)
    if arr is None:
        return None
    try:
        return float(arr.iloc[idx])
    except Exception:
        return None


def _stock_meta(symbol: str) -> dict:
    out: dict = {"sector": None, "industry": None, "name": None,
                 "dividend_yield": None}
    try:
        from api.services.discover_service import _load_stock_meta
        meta = _load_stock_meta().get(symbol, {})
        out["sector"] = meta.get("sector")
        out["name"] = meta.get("name")
    except Exception:
        pass
    try:
        fund = cache_get(f"market:fundamentals:{symbol}") or {}
        out["sector"] = out["sector"] or fund.get("sector")
        out["industry"] = out["industry"] or fund.get("industry")
        out["name"] = out["name"] or fund.get("longName") or fund.get("shortName")
        v = fund.get("dividend_yield")
        try:
            out["dividend_yield"] = float(v) if v is not None else None
        except Exception:
            pass
    except Exception:
        pass
    return out


# ── REAL historical macro ────────────────────────────────────────


def _fetch_macro_history(start: str, end: str) -> dict:
    import yfinance as yf
    out: dict = {"vix": {}, "t10y": {}, "t2y": {}, "spx": {}, "spx_change_20d": {}}
    try:
        start_dt = datetime.strptime(start, "%Y-%m-%d")
        padded = (start_dt - timedelta(days=45)).strftime("%Y-%m-%d")

        df = yf.download(
            "^VIX ^TNX ^FVX ^GSPC",
            start=padded, end=end, progress=False, auto_adjust=False,
            group_by="ticker", threads=False,
        )

        def _series(ticker: str):
            try:
                if df.columns.nlevels > 1 and ticker in df.columns.get_level_values(0):
                    s = df[ticker]["Close"].dropna()
                    return {d.strftime("%Y-%m-%d"): float(v) for d, v in s.items()}
            except Exception:
                pass
            return {}

        out["vix"] = _series("^VIX")
        out["t10y"] = _series("^TNX")
        out["t2y"] = _series("^FVX")
        out["spx"] = _series("^GSPC")

        if out["spx"]:
            sd = sorted(out["spx"].keys())
            for i, d in enumerate(sd):
                if i >= 20:
                    prev = out["spx"][sd[i - 20]]
                    if prev:
                        out["spx_change_20d"][d] = ((out["spx"][d] - prev) / prev) * 100.0
    except Exception:
        pass
    return out


def _macro_at(macro_hist: dict, date_str: str) -> dict:
    def _lookup(series: dict) -> float | None:
        if date_str in series:
            return series[date_str]
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d")
            for back in range(1, 8):
                k = (d - timedelta(days=back)).strftime("%Y-%m-%d")
                if k in series:
                    return series[k]
        except Exception:
            pass
        return None

    return {
        "vix": _lookup(macro_hist.get("vix", {})),
        "t10y": _lookup(macro_hist.get("t10y", {})),
        "t2y": _lookup(macro_hist.get("t2y", {})),
        "spx": _lookup(macro_hist.get("spx", {})),
        "spx_change_20d": _lookup(macro_hist.get("spx_change_20d", {})),
    }


# ── REAL historical sector ETF perf ───────────────────────────────


_SECTOR_ETF = {
    "Technology": "XLK",
    "Healthcare": "XLV",
    "Financials": "XLF",
    "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP",
    "Industrials": "XLI",
    "Energy": "XLE",
    "Materials": "XLB",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Communication Services": "XLC",
}


def _fetch_sector_history(sector: str | None, start: str, end: str) -> dict:
    if not sector:
        return {}
    etf = _SECTOR_ETF.get(sector)
    if not etf:
        return {}
    try:
        import yfinance as yf
        start_dt = datetime.strptime(start, "%Y-%m-%d")
        padded = (start_dt - timedelta(days=45)).strftime("%Y-%m-%d")
        df = yf.download(etf, start=padded, end=end, progress=False, auto_adjust=False, threads=False)
        if df.empty:
            return {}
        s = df["Close"].squeeze().dropna()
        result: dict = {}
        for i in range(len(s)):
            if i >= 20:
                prev = float(s.iloc[i - 20])
                if prev:
                    d = s.index[i]
                    result[d.strftime("%Y-%m-%d")] = ((float(s.iloc[i]) - prev) / prev) * 100.0
        return result
    except Exception:
        return {}


def _sector_perf_at(sector_hist: dict, date_str: str) -> float | None:
    if not sector_hist:
        return None
    if date_str in sector_hist:
        return sector_hist[date_str]
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        for back in range(1, 8):
            k = (d - timedelta(days=back)).strftime("%Y-%m-%d")
            if k in sector_hist:
                return sector_hist[k]
    except Exception:
        pass
    return None


# ── REAL historical trailing P/E ──────────────────────────────────


def _fetch_eps_history(symbol: str) -> list[tuple[str, float]]:
    merged: dict[str, float] = {}
    try:
        import yfinance as yf
        t = yf.Ticker(symbol)
        try:
            qis = t.quarterly_income_stmt
            for label in ("Diluted EPS", "Basic EPS", "BasicEPS", "DilutedEPS"):
                if label in qis.index:
                    series = qis.loc[label]
                    for col, val in series.items():
                        try:
                            eps = float(val)
                            if eps != eps:
                                continue
                            ds = col.strftime("%Y-%m-%d") if hasattr(col, "strftime") else str(col)[:10]
                            merged[ds] = eps
                        except Exception:
                            continue
                    break
        except Exception:
            pass
        try:
            eh = getattr(t, "earnings_history", None)
            if eh is not None and not eh.empty:
                for q, row in eh.iterrows():
                    try:
                        eps = float(row.get("epsActual"))
                        if eps != eps:
                            continue
                        ds = q.strftime("%Y-%m-%d") if hasattr(q, "strftime") else str(q)[:10]
                        merged[ds] = eps
                    except Exception:
                        continue
        except Exception:
            pass
    except Exception:
        return []
    return sorted(merged.items(), key=lambda r: r[0])


def _ttm_eps_at(eps_history: list[tuple[str, float]], date_str: str) -> float | None:
    relevant = [eps for d, eps in eps_history if d <= date_str]
    if len(relevant) >= 4:
        return sum(relevant[-4:])
    if len(relevant) == 3:
        return sum(relevant) * (4 / 3)
    return None


# ── Historical insider + congress trade pool ──────────────────────


def _fetch_historical_insider_pool(symbol: str, lookback_days: int = 720) -> dict:
    """Fetch SEC Form 4 insider trades + Capitol Trades congressional trades for
    a wide window once at the start of the backtest. Per-cycle, we filter this
    pool to only trades that occurred in the 60 days before the cycle date.

    Returns {"insider": [trades…], "congress": [trades…]} where each trade is
    a dict with at least "date", "side" (buy/sell), "filer", "amount" (when known).
    """
    out: dict = {"insider": [], "congress": []}
    gw = DataGateway()

    # SEC Form 4 — `days` is just how far back the provider looks. We pass a
    # large window covering the entire backtest range.
    try:
        sec = gw._get_sec()
        trades = sec.get_insider_trades(symbol, days=lookback_days) or []
        for t in trades:
            try:
                out["insider"].append({
                    "date": str(getattr(t, "transaction_date", "")),
                    "side": (getattr(t, "transaction_type", "") or "").lower(),
                    "filer": str(getattr(t, "filer_name", "Insider")),
                    "title": str(getattr(t, "filer_title", "")),
                    "shares": int(getattr(t, "shares", 0) or 0),
                })
            except Exception:
                continue
    except Exception:
        pass

    # Capitol Trades
    try:
        cong = gw._get_congress()
        trades = cong.get_trades_by_symbol(symbol, days=lookback_days) or []
        for t in trades:
            try:
                out["congress"].append({
                    "date": str(getattr(t, "trade_date", "")),
                    "side": (getattr(t, "transaction_type", "") or "").lower(),
                    "politician": str(getattr(t, "politician_name", "")),
                    "party": str(getattr(t, "party", "")),
                    "amount": str(getattr(t, "amount_range", "")),
                })
            except Exception:
                continue
    except Exception:
        pass

    return out


def _insider_window(pool: dict, date_str: str, window_days: int = 60) -> dict:
    """Filter the insider/congress pool to trades within the 60 days BEFORE
    the cycle date — strictly historical, no look-ahead leak."""
    try:
        cycle = datetime.strptime(date_str, "%Y-%m-%d")
        since = (cycle - timedelta(days=window_days)).strftime("%Y-%m-%d")
        until = date_str
    except Exception:
        return {"insider_buys": 0, "insider_sells": 0, "congress_buys": 0,
                "congress_sells": 0, "cluster_buy": False,
                "recent_filers": [], "recent_politicians": []}

    insider_in_window = [t for t in pool.get("insider", []) if since <= t["date"] <= until]
    congress_in_window = [t for t in pool.get("congress", []) if since <= t["date"] <= until]

    insider_buys = [t for t in insider_in_window if "buy" in t["side"] or t["side"] == "p"]
    insider_sells = [t for t in insider_in_window if "sell" in t["side"] or t["side"] == "s"]
    congress_buys = [t for t in congress_in_window if "buy" in t["side"] or "p" in t["side"]]
    congress_sells = [t for t in congress_in_window if "sell" in t["side"] or "s" in t["side"]]

    # Cluster buy: 2+ insider buys within any 7-day rolling window
    cluster_buy = False
    if len(insider_buys) >= 2:
        dates = sorted(t["date"] for t in insider_buys if t["date"])
        for i in range(len(dates) - 1):
            try:
                d1 = datetime.strptime(dates[i], "%Y-%m-%d")
                d2 = datetime.strptime(dates[i + 1], "%Y-%m-%d")
                if (d2 - d1).days <= 7:
                    cluster_buy = True
                    break
            except Exception:
                continue

    recent_filers = [t["filer"] for t in insider_buys[-3:] if t.get("filer")]
    recent_politicians = [
        f"{t['politician']} ({t['party']}) {t.get('amount', '')}".strip()
        for t in congress_buys[-3:] if t.get("politician")
    ]

    return {
        "insider_buys": len(insider_buys),
        "insider_sells": len(insider_sells),
        "congress_buys": len(congress_buys),
        "congress_sells": len(congress_sells),
        "cluster_buy": cluster_buy,
        "recent_filers": recent_filers,
        "recent_politicians": recent_politicians,
        "window_days": window_days,
    }


# ── FINRA daily short volume (free, per-stock historical) ────────


def _fetch_finra_short_at(symbol: str, date_str: str) -> dict | None:
    """FINRA REG SHO daily short volume — free, public, full historical.

    Each daily file (CNMSshvolYYYYMMDD.txt) is a pipe-delimited table with
    columns: Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market.
    We read it and pull the row for `symbol`. Cached aggressively per
    (symbol, date) since old daily files don't change.
    """
    cache_key = f"finra_short:{symbol}:{date_str}"
    cached = cache_get(cache_key)
    if cached is not None:
        # cache_get returns None when missing OR expired; we use the empty dict
        # marker for "tried, no data" so we don't refetch a missing day.
        return cached if cached else None

    try:
        import httpx
        ds = date_str.replace("-", "")
        url = f"https://cdn.finra.org/equity/regsho/daily/CNMSshvol{ds}.txt"
        r = httpx.get(url, timeout=10, follow_redirects=True)
        if r.status_code != 200:
            cache_set(cache_key, {}, ttl_minutes=60 * 24)  # negative-cache 1 day
            return None
        for line in r.text.split("\n"):
            parts = line.split("|")
            if len(parts) >= 5 and parts[1].upper() == symbol.upper():
                try:
                    short_vol = float(parts[2])
                    total_vol = float(parts[4]) if parts[4] else 0.0
                    if total_vol <= 0:
                        return None
                    payload = {
                        "short_volume": short_vol,
                        "total_volume": total_vol,
                        "short_ratio": short_vol / total_vol,
                    }
                    cache_set(cache_key, payload, ttl_minutes=60 * 24 * 30)  # 30 days
                    return payload
                except Exception:
                    return None
    except Exception:
        pass

    cache_set(cache_key, {}, ttl_minutes=60 * 24)
    return None


def _finra_short_window(symbol: str, date_str: str, lookback_days: int = 5) -> dict | None:
    """Average short ratio over the last N trading days. Walks back day-by-day."""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
    except Exception:
        return None
    samples: list[dict] = []
    for back in range(lookback_days):
        d_check = (d - timedelta(days=back)).strftime("%Y-%m-%d")
        # Skip weekends
        weekday = (d - timedelta(days=back)).weekday()
        if weekday >= 5:
            continue
        row = _fetch_finra_short_at(symbol, d_check)
        if row:
            samples.append(row)
        if len(samples) >= 3:
            break
    if not samples:
        return None
    avg_ratio = sum(s["short_ratio"] for s in samples) / len(samples)
    avg_total = sum(s["total_volume"] for s in samples) / len(samples)
    avg_short = sum(s["short_volume"] for s in samples) / len(samples)
    if avg_ratio < 0.30:
        regime = "LOW (bullish positioning)"
    elif avg_ratio < 0.50:
        regime = "Normal"
    elif avg_ratio < 0.70:
        regime = "ELEVATED (bearish institutional positioning)"
    else:
        regime = "HEAVY shorting (potential squeeze setup)"
    return {
        "short_ratio": avg_ratio,
        "avg_total_volume": avg_total,
        "avg_short_volume": avg_short,
        "samples": len(samples),
        "regime": regime,
    }


# ── Polygon news + sentiment ──────────────────────────────────────


def _fetch_polygon_news(symbol: str, since: str, until: str) -> list[str]:
    api_key = os.environ.get("POLYGON_API_KEY", "")
    if not api_key:
        return []
    try:
        import httpx
        r = httpx.get(
            "https://api.polygon.io/v2/reference/news",
            params={
                "ticker": symbol,
                "published_utc.gte": since,
                "published_utc.lte": until,
                "limit": 20,
                "apiKey": api_key,
            },
            timeout=10,
        )
        if r.status_code != 200:
            return []
        return [item.get("title", "") for item in (r.json().get("results") or []) if item.get("title")]
    except Exception:
        return []


def _historical_sentiment(symbol: str, date_str: str,
                          change_5d: float | None, change_20d: float | None) -> dict:
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        since = (d - timedelta(days=7)).strftime("%Y-%m-%d")
        headlines = _fetch_polygon_news(symbol, since, date_str)
    except Exception:
        headlines = []

    if headlines:
        try:
            from src.sentiment.analyzer import score_headlines_batch
            scored = score_headlines_batch(headlines)
            scores = [float(s) for _, s in scored if s is not None]
            if scores:
                avg = sum(scores) / len(scores)
                label = "Bullish" if avg > 0.3 else "Bearish" if avg < -0.3 else "Mixed"
                return {"label": label, "score": round(avg, 2),
                        "source": "polygon-news",
                        "notes": [f'"{h[:80]}"' for h in headlines[:3]]}
        except Exception:
            pass

    score = 0
    notes: list[str] = []
    if change_5d is not None:
        if change_5d > 5: score += 2; notes.append(f"+{change_5d:.1f}% over 5d (strong momentum)")
        elif change_5d > 1: score += 1; notes.append(f"+{change_5d:.1f}% over 5d")
        elif change_5d < -5: score -= 2; notes.append(f"{change_5d:.1f}% over 5d (selloff)")
        elif change_5d < -1: score -= 1; notes.append(f"{change_5d:.1f}% over 5d")
    if change_20d is not None:
        if change_20d > 8: score += 1; notes.append(f"+{change_20d:.1f}% over 20d (uptrend)")
        elif change_20d < -8: score -= 1; notes.append(f"{change_20d:.1f}% over 20d (downtrend)")
    label = "Bullish" if score >= 2 else "Bearish" if score <= -2 else "Mixed"
    return {"label": label, "score": score,
            "source": "momentum-proxy (no POLYGON_API_KEY)",
            "notes": notes}


# ── Real macro-driven market pulse ────────────────────────────────


def _market_pulse(macro: dict, sma50: float | None, sma200: float | None,
                  price: float, atr_pct: float | None) -> dict:
    notes: list[str] = []
    regime = "Normal"
    vix = macro.get("vix")
    t10y = macro.get("t10y")
    t2y = macro.get("t2y")
    spx20 = macro.get("spx_change_20d")
    inverted = (t10y is not None and t2y is not None and t2y > t10y)

    if inverted:
        regime = "Recession Warning"
        notes.append(f"Inverted yield curve ({t2y:.2f}% > {t10y:.2f}%)")
    elif vix is not None and vix > 30:
        regime = "High Volatility / Risk-Off"
        notes.append(f"VIX at {vix:.1f} (extreme fear)")
    elif vix is not None and vix > 20:
        regime = "Elevated Volatility"
        notes.append(f"VIX at {vix:.1f}")
    elif spx20 is not None and spx20 < -5:
        regime = "Broad Selloff"
        notes.append(f"S&P 500 down {spx20:.1f}% over 20d")
    elif spx20 is not None and spx20 > 5:
        regime = "Risk-On"
        notes.append(f"S&P 500 up +{spx20:.1f}% over 20d")
    else:
        notes.append("Macro within normal range")

    if sma50 and sma200:
        if sma50 > sma200 * 1.01 and price > sma50:
            notes.append("Stock in bull trend (price > SMA50 > SMA200)")
        elif sma50 < sma200 * 0.99 and price < sma50:
            notes.append("Stock in bear trend (price < SMA50 < SMA200)")
    if atr_pct is not None and atr_pct > 0.04:
        notes.append(f"Stock-level high volatility (ATR ≈ {atr_pct*100:.1f}%)")

    return {"regime": regime, "notes": notes}


def _trade_plan(price: float, sma50: float | None, recent_low: float,
                recent_high: float, atr: float | None) -> dict:
    candidates = [v for v in (sma50, recent_low) if v and v < price]
    if atr and atr > 0:
        candidates.append(price - 1.5 * atr)
    stop = round(max(candidates) if candidates else price * 0.92, 2)
    target1 = round(recent_high if recent_high > price else price * 1.06, 2)
    risk_per_share = max(0.01, round(price - stop, 2))
    reward1 = round(target1 - price, 2)
    rr = round(reward1 / risk_per_share, 2) if risk_per_share > 0 else 0.0
    target2 = round(price + 2 * risk_per_share, 2)
    return {
        "entry": round(price, 2),
        "stop": stop, "target1": target1, "target2": target2,
        "risk_per_share": risk_per_share, "rr": rr,
        "stop_pct": round((risk_per_share / price) * 100, 1),
    }


# ── Historical opportunity score (Discover-equivalent) ────────────


def _historical_opportunity(symbol: str, df_slice, stock_change_20d: float | None,
                            spx_change_20d: float | None) -> dict | None:
    try:
        from src.analysis import technical
        from src.analysis.opportunity import compute_opportunity
        if df_slice is None or df_slice.empty or len(df_slice) < 30:
            return None
        tech = technical.analyze(symbol, df_slice)
        score = compute_opportunity(
            symbol, technicals=tech,
            stock_change_pct=stock_change_20d,
            benchmark_change_pct=spx_change_20d,
        )
        return {
            "total": int(getattr(score, "total_score", 0) or 0),
            "label": str(getattr(score, "label", "—")),
            "strategy": str(getattr(score, "strategy", "Neutral")),
            "secondaries": list(getattr(score, "secondary_strategies", []) or []),
            "vol": int(getattr(score, "volume_score", 0) or 0),
            "price": int(getattr(score, "price_score", 0) or 0),
            "flow": int(getattr(score, "flow_score", 0) or 0),
            "rr": int(getattr(score, "risk_reward_score", 0) or 0),
            "rr_ratio": str(getattr(score, "risk_reward_ratio", "")),
            "trend_pullback": bool(getattr(score, "trend_pullback", False)),
            "relative_strength": bool(getattr(score, "relative_strength", False)),
            "volume_confirmed": bool(getattr(score, "volume_confirmed", False)),
        }
    except Exception:
        return None


# ── Signal categorization (Deep-Dive equivalent) ──────────────────


def _signal_summary(snap: dict) -> dict:
    signals: list[dict] = []
    rsi = snap.get("rsi")
    if rsi is not None:
        if rsi < 30: signals.append({"name": "RSI Oversold", "dir": "bullish", "note": f"RSI {rsi:.0f} < 30"})
        elif rsi > 70: signals.append({"name": "RSI Overbought", "dir": "bearish", "note": f"RSI {rsi:.0f} > 70"})
        elif 50 < rsi < 65: signals.append({"name": "RSI Healthy", "dir": "bullish", "note": f"RSI {rsi:.0f} in 50-65 zone"})
        else: signals.append({"name": "RSI Neutral", "dir": "neutral", "note": f"RSI {rsi:.0f}"})

    macd = snap.get("macd_hist")
    if macd is not None:
        if macd > 0.5: signals.append({"name": "MACD Bullish", "dir": "bullish", "note": f"MACD-hist {macd:+.2f}"})
        elif macd < -0.5: signals.append({"name": "MACD Bearish", "dir": "bearish", "note": f"MACD-hist {macd:+.2f}"})
        else: signals.append({"name": "MACD Flat", "dir": "neutral", "note": f"MACD-hist {macd:+.2f}"})

    sma50 = snap.get("sma_50")
    sma200 = snap.get("sma_200")
    price = snap.get("price")
    if sma50 and sma200 and price:
        if sma50 > sma200 and price > sma50:
            signals.append({"name": "Above SMA50 + Golden setup", "dir": "bullish", "note": "Price > SMA50 > SMA200"})
        elif sma50 < sma200 and price < sma50:
            signals.append({"name": "Below SMA50 + Death setup", "dir": "bearish", "note": "Price < SMA50 < SMA200"})

    bb_low = snap.get("bb_lower")
    bb_up = snap.get("bb_upper")
    if bb_low and bb_up and price and bb_up > bb_low:
        pos = (price - bb_low) / (bb_up - bb_low)
        if pos > 0.95: signals.append({"name": "BB Upper Touch", "dir": "bearish", "note": "Near upper Bollinger"})
        elif pos < 0.05: signals.append({"name": "BB Lower Touch", "dir": "bullish", "note": "Near lower Bollinger"})

    vol = snap.get("vol_ratio")
    if vol is not None:
        if vol > 2: signals.append({"name": "Volume Spike", "dir": "bullish", "note": f"{vol:.1f}× avg"})
        elif vol < 0.5: signals.append({"name": "Volume Drying Up", "dir": "bearish", "note": f"{vol:.1f}× avg"})

    chg5 = snap.get("change_5d")
    if chg5 is not None:
        if chg5 > 5: signals.append({"name": "Strong Short-Term Momentum", "dir": "bullish", "note": f"+{chg5:.1f}% / 5d"})
        elif chg5 < -5: signals.append({"name": "Selloff Pressure", "dir": "bearish", "note": f"{chg5:.1f}% / 5d"})

    bull = sum(1 for s in signals if s["dir"] == "bullish")
    bear = sum(1 for s in signals if s["dir"] == "bearish")
    neut = sum(1 for s in signals if s["dir"] == "neutral")
    total = max(1, bull + bear + neut)
    dominant = "bullish" if bull >= bear else "bearish"
    alignment = round((max(bull, bear) / total) * 100)
    return {
        "signals": signals,
        "bull": bull, "bear": bear, "neutral": neut,
        "alignment_pct": alignment, "dominant": dominant,
    }


# ── Prompt composition ───────────────────────────────────────────


def _insider_block(insider_window: dict | None) -> str:
    """Format the insider/congress activity block for the prompt."""
    if not insider_window:
        return (
            "=== SMART MONEY (insider + congress trades) ===\n"
            "  No data available\n"
        )
    iw = insider_window
    cluster = " · ⚡ CLUSTER BUY (2+ insiders within 7d)" if iw.get("cluster_buy") else ""
    filers = ", ".join(iw.get("recent_filers", []) or [])
    pols = ", ".join(iw.get("recent_politicians", []) or [])
    out = (
        f"=== SMART MONEY (last {iw.get('window_days', 60)}d, real SEC + Capitol Trades) ===\n"
        f"  Insider trades: {iw['insider_buys']} buys · {iw['insider_sells']} sells{cluster}\n"
        f"  Congress trades: {iw['congress_buys']} buys · {iw['congress_sells']} sells\n"
    )
    if filers:
        out += f"  Recent insider buyers: {filers}\n"
    if pols:
        out += f"  Recent congressional buyers: {pols}\n"
    return out


def _flow_block(flow: dict | None) -> str:
    if not flow:
        return (
            "=== FLOW (FINRA short volume) ===\n"
            "  No data available for this date\n"
        )
    return (
        f"=== FLOW (FINRA daily short volume — real, free, public) ===\n"
        f"  Short ratio: {flow['short_ratio']*100:.1f}% "
        f"({int(flow['avg_short_volume'])/1000:.0f}K of {int(flow['avg_total_volume'])/1000:.0f}K volume)\n"
        f"  Regime: {flow['regime']}  (avg over last {flow['samples']} sessions)\n"
        f"  Note: Level 2 / dark-pool prints not available (would need Polygon paid plan)\n"
    )


def _format_context(symbol: str, snap: dict, pulse: dict, sentiment: dict,
                    plan: dict, meta: dict, fundamentals: dict,
                    opportunity: dict | None, signal_sum: dict,
                    sector_perf: float | None,
                    insider_window: dict | None,
                    flow_window: dict | None,
                    open_trade: dict | None) -> str:
    """Shared rich context — same for all agents in multi mode."""
    sector = meta.get("sector") or "Unknown"
    industry = meta.get("industry") or ""
    div = f"{meta['dividend_yield']*100:.2f}%" if meta.get("dividend_yield") else "n/a"
    pe_s = f"{fundamentals['pe_ratio']:.1f}" if fundamentals.get("pe_ratio") else "n/a"
    eps_ttm_s = f"${fundamentals['ttm_eps']:.2f}" if fundamentals.get("ttm_eps") else "n/a"

    macro = pulse.get("macro_real", {})
    vix_s = f"{macro['vix']:.1f}" if macro.get("vix") is not None else "n/a"
    t10y_s = f"{macro['t10y']:.2f}%" if macro.get("t10y") is not None else "n/a"
    t2y_s = f"{macro['t2y']:.2f}%" if macro.get("t2y") is not None else "n/a"
    spx20_s = f"{macro['spx_change_20d']:+.1f}%" if macro.get("spx_change_20d") is not None else "n/a"
    sect_s = f"{sector_perf:+.1f}%" if sector_perf is not None else "n/a"

    rsi_s = f"{snap['rsi']:.1f}" if snap.get("rsi") is not None else "n/a"
    macd_s = f"{snap['macd_hist']:.2f}" if snap.get("macd_hist") is not None else "n/a"
    sma50_s = f"${snap['sma_50']:.2f}" if snap.get("sma_50") is not None else "n/a"
    sma200_s = f"${snap['sma_200']:.2f}" if snap.get("sma_200") is not None else "n/a"
    bb_s = (f"${snap['bb_lower']:.2f} – ${snap['bb_upper']:.2f}"
            if snap.get("bb_lower") and snap.get("bb_upper") else "n/a")
    vol_s = f"{snap['vol_ratio']:.2f}× 20-day avg" if snap.get("vol_ratio") is not None else "n/a"
    chg5 = f"{snap['change_5d']:+.1f}%" if snap.get("change_5d") is not None else "n/a"
    chg20 = f"{snap['change_20d']:+.1f}%" if snap.get("change_20d") is not None else "n/a"

    pulse_notes = "\n  - " + "\n  - ".join(pulse["notes"]) if pulse["notes"] else ""
    sent_notes = "\n  - " + "\n  - ".join(sentiment["notes"]) if sentiment["notes"] else ""

    if opportunity:
        opp_block = (
            f"=== OPPORTUNITY SCORE (Discover-equivalent, recomputed at this date) ===\n"
            f"  Total: {opportunity['total']}/100 — {opportunity['label']}\n"
            f"  Sub-scores: Volume {opportunity['vol']}/25 · Price {opportunity['price']}/25 · "
            f"Flow {opportunity['flow']}/25 · R/R {opportunity['rr']}/25\n"
            f"  Strategy: {opportunity['strategy']} (R/R {opportunity['rr_ratio']})\n"
            f"  Also detected: {', '.join(opportunity['secondaries']) if opportunity['secondaries'] else 'none'}\n"
            f"  Confirmations: TP={'✓' if opportunity['trend_pullback'] else '✗'} · "
            f"RS={'✓' if opportunity['relative_strength'] else '✗'} · "
            f"VOL={'✓' if opportunity['volume_confirmed'] else '✗'}\n"
        )
    else:
        opp_block = "=== OPPORTUNITY SCORE === insufficient history to compute\n"

    sig_lines = "\n".join(
        f"  - {s['name']:30} → {s['dir'].upper():8} ({s['note']})"
        for s in signal_sum["signals"]
    ) or "  - (insufficient indicators)"
    sig_block = (
        f"=== SIGNALS (Deep-Dive equivalent, technical only) ===\n"
        f"  Alignment: {signal_sum['alignment_pct']}% {signal_sum['dominant']}\n"
        f"  Counts: ↑ {signal_sum['bull']} bullish · ↓ {signal_sum['bear']} bearish · "
        f"– {signal_sum['neutral']} neutral\n"
        f"{sig_lines}\n"
        f"  Note: options/congress/buzz signals not available in backtest\n"
    )

    position_block = (
        f"OPEN long at ${open_trade['entry_price']:.2f} on {open_trade['entry_date']} "
        f"(currently {((snap['price']-open_trade['entry_price'])/open_trade['entry_price'])*100:+.1f}% P&L)"
        if open_trade else "NONE"
    )

    return (
        f"=== STOCK ===\n"
        f"  {symbol} · {meta.get('name') or symbol}\n"
        f"  Sector: {sector} | Industry: {industry or 'n/a'}\n"
        f"  Date: {snap['date']} | Price: ${snap['price']:.2f}\n"
        f"\n"
        f"=== MARKET PULSE (real macro at this date) ===\n"
        f"  Regime: {pulse['regime']}\n"
        f"  VIX: {vix_s} | 10Y: {t10y_s} | 5Y: {t2y_s} | S&P 20d: {spx20_s}\n"
        f"  {sector} ETF 20d perf: {sect_s} (vs S&P {spx20_s})"
        f"{pulse_notes}\n"
        f"\n"
        f"=== TECHNICAL ===\n"
        f"  RSI: {rsi_s} | MACD-hist: {macd_s} | Volume: {vol_s}\n"
        f"  SMA50: {sma50_s} | SMA200: {sma200_s} | BB: {bb_s}\n"
        f"  Change 5d: {chg5} | 20d: {chg20}\n"
        f"\n"
        f"{sig_block}"
        f"\n"
        f"{opp_block}"
        f"\n"
        f"=== SENTIMENT ({sentiment['source']}) ===\n"
        f"  {sentiment['label']} (score {sentiment['score']:+}){sent_notes}\n"
        f"\n"
        f"=== FUNDAMENTALS (point-in-time) ===\n"
        f"  Trailing P/E: {pe_s} | TTM EPS: {eps_ttm_s} | Dividend yield: {div}\n"
        f"\n"
        f"{_insider_block(insider_window)}"
        f"\n"
        f"{_flow_block(flow_window)}"
        f"\n"
        f"=== TRADE PLAN ===\n"
        f"  Entry: ${plan['entry']} | Stop: ${plan['stop']} (-{plan['stop_pct']}%)\n"
        f"  Target 1: ${plan['target1']} | Target 2: ${plan['target2']} | R/R: {plan['rr']}:1\n"
        f"\n"
        f"=== POSITION ===\n"
        f"  {position_block}\n"
    )


def _build_single_prompt(context: str) -> str:
    return (
        f"You are a disciplined equity trader. Decide based on this snapshot only — no future data.\n\n"
        f"{context}\n"
        f"Decision rule:\n"
        f"  - BUY when oversold (RSI<35) OR a clear bullish setup is present.\n"
        f"  - SELL when overbought (RSI>70) OR a clear bearish breakdown is present.\n"
        f"  - HOLD only when signals are genuinely mixed.\n"
        f"Reply with EXACTLY ONE WORD: BUY, SELL, or HOLD. No explanation."
    )


def _build_personality_prompt(agent_key: str, context: str) -> str:
    from src.personalities import AGENT_PERSONALITIES
    p = AGENT_PERSONALITIES.get(agent_key, {})
    name = p.get("name", agent_key)
    icon = p.get("icon", "🤖")
    philosophy = p.get("philosophy", "")
    prioritizes = p.get("prioritizes", []) or []
    avoids = p.get("avoids", []) or []
    risk = p.get("risk_tolerance", "")

    prio_block = ("\n  - " + "\n  - ".join(prioritizes)) if prioritizes else ""
    avoid_block = ("\n  - " + "\n  - ".join(avoids)) if avoids else ""

    # Honest disclosure for agents whose preferred data we can't backfill
    data_gap = _DATA_GAPS.get(agent_key)
    gap_block = ""
    if data_gap:
        gap_block = (
            f"\n⚠ DATA NOTE — your preferred data ({data_gap}) is NOT available in this\n"
            f"   backtest. You must reason from the technical, macro, fundamentals,\n"
            f"   sentiment, and sector signals shown below. Be appropriately less confident.\n"
        )

    return (
        f"You are the {icon} {name} agent.\n"
        f"Philosophy: {philosophy}\n"
        f"You prioritize:{prio_block}\n"
        f"You avoid:{avoid_block}\n"
        f"Risk tolerance: {risk}\n"
        f"{gap_block}"
        f"\n"
        f"Apply your personality to this snapshot — no future data:\n\n"
        f"{context}\n"
        f"Reply on a SINGLE LINE in this exact format:\n"
        f"  DECISION | REASON\n"
        f"where DECISION is BUY, SELL, or HOLD (one word), and REASON is one short sentence\n"
        f"(<= 25 words) naming the 1-2 specific factors driving your call from your lens.\n"
        f'Example: "BUY | RSI deeply oversold + sector outperforming S&P + bullish regime"\n'
        f'Example: "HOLD | Mixed signals; no clear edge for a momentum trader here"'
    )


def _vote_majority(votes: dict[str, str]) -> str:
    """Majority across the active agents — need at least half (rounded up) and a plurality."""
    buys = sum(1 for v in votes.values() if v == "BUY")
    sells = sum(1 for v in votes.values() if v == "SELL")
    threshold = (len(votes) + 1) // 2  # 7 → 4, 8 → 4
    if buys >= threshold and buys > sells: return "BUY"
    if sells >= threshold and sells > buys: return "SELL"
    return "HOLD"


# ── Public entry ─────────────────────────────────────────────────


def run_ai_backtest(symbol: str, period: str = "1M", cycles: int = 12,
                    mode: str = "single") -> dict:
    period = period if period in _PERIOD_DAYS else "1M"
    if mode not in ("single", "multi"):
        mode = "single"
    hold_days = _PERIOD_DAYS[period]
    symbol = symbol.upper()

    gw = DataGateway()
    hist = gw.get_historical(symbol, period_days=max(365, hold_days * cycles + 100))
    if hist is None or hist.empty or len(hist) < 60:
        return {"symbol": symbol, "period": period, "mode": mode,
                "error": "Not enough data", "decisions": []}

    df = hist.reset_index(drop=True)
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    volume = df["volume"].astype(float)
    indicators = _compute_indicators(close, high, low, volume)

    n = len(df)
    cycle_step = max(1, hold_days)
    end_idx = n - 1
    start_idx = max(60, end_idx - cycles * cycle_step)
    time_points = list(range(start_idx, end_idx + 1, cycle_step))
    if len(time_points) < 2:
        return {"symbol": symbol, "period": period, "mode": mode,
                "error": "Not enough cycles", "decisions": []}

    start_date = str(df["date"].iloc[start_idx])[:10]
    end_date = (datetime.strptime(str(df["date"].iloc[end_idx])[:10], "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    macro_hist = _fetch_macro_history(start_date, end_date)
    eps_history = _fetch_eps_history(symbol)
    meta = _stock_meta(symbol)
    sector_hist = _fetch_sector_history(meta.get("sector"), start_date, end_date)

    # Pull a wide insider/congress trade pool once. Per cycle we filter to the
    # 60-day window before that cycle date — strictly historical, no leakage.
    insider_lookback = max(720, hold_days * cycles + 90)
    insider_pool = _fetch_historical_insider_pool(symbol, lookback_days=insider_lookback)

    # ── Phase 1 — build per-cycle context ──────────────────────
    contexts: list[dict] = []
    for idx in time_points:
        if idx >= n:
            break

        date_str = str(df["date"].iloc[idx])[:10]
        price_now = float(close.iloc[idx])
        rsi = _series_at(indicators, "rsi", idx)
        macd_hist = _series_at(indicators, "macd_hist", idx)
        sma_50 = _series_at(indicators, "sma_50", idx)
        sma_200 = _series_at(indicators, "sma_200", idx)
        bb_lower = _series_at(indicators, "bb_lower", idx)
        bb_upper = _series_at(indicators, "bb_upper", idx)
        atr = _series_at(indicators, "atr", idx)

        vol_ratio = None
        if idx >= 20:
            try:
                vol_ratio = float(volume.iloc[idx]) / max(1.0, float(volume.iloc[idx - 20:idx].mean()))
            except Exception:
                pass

        lookback_range = max(0, idx - 20)
        recent_low = float(low.iloc[lookback_range:idx + 1].min())
        recent_high = float(high.iloc[lookback_range:idx + 1].max())

        change_5d = None
        change_20d = None
        if idx >= 5:
            p5 = float(close.iloc[idx - 5])
            change_5d = ((price_now - p5) / p5) * 100 if p5 else None
        if idx >= 20:
            p20 = float(close.iloc[idx - 20])
            change_20d = ((price_now - p20) / p20) * 100 if p20 else None

        atr_pct = (atr / price_now) if atr and price_now else None

        macro_real = _macro_at(macro_hist, date_str)
        sector_perf = _sector_perf_at(sector_hist, date_str)
        ttm_eps = _ttm_eps_at(eps_history, date_str)
        pe_ratio = (price_now / ttm_eps) if ttm_eps and ttm_eps > 0 else None
        fundamentals = {"ttm_eps": ttm_eps, "pe_ratio": pe_ratio}
        sentiment = _historical_sentiment(symbol, date_str, change_5d, change_20d)

        snap = {
            "date": date_str, "price": price_now,
            "rsi": rsi, "macd_hist": macd_hist,
            "sma_50": sma_50, "sma_200": sma_200,
            "bb_upper": bb_upper, "bb_lower": bb_lower,
            "vol_ratio": vol_ratio,
            "change_5d": change_5d, "change_20d": change_20d,
        }

        pulse = _market_pulse(macro_real, sma_50, sma_200, price_now, atr_pct)
        pulse["macro_real"] = macro_real
        plan = _trade_plan(price_now, sma_50, recent_low, recent_high, atr)
        opportunity = _historical_opportunity(
            symbol, df.iloc[: idx + 1], change_20d, macro_real.get("spx_change_20d"),
        )
        signal_sum = _signal_summary(snap)
        insider_win = _insider_window(insider_pool, date_str)
        flow_win = _finra_short_window(symbol, date_str)

        ctx_text = _format_context(
            symbol, snap, pulse, sentiment, plan, meta, fundamentals,
            opportunity, signal_sum, sector_perf, insider_win, flow_win, None,
        )

        contexts.append({
            "idx": idx, "snap": snap, "pulse": pulse,
            "sentiment": sentiment, "plan": plan, "fundamentals": fundamentals,
            "opportunity": opportunity, "signal_sum": signal_sum,
            "sector_perf": sector_perf,
            "insider_window": insider_win,
            "flow_window": flow_win,
            "context_text": ctx_text,
        })

    # ── Phase 2 — fan out Claude calls ────────────────────────
    if mode == "single":
        def _eval_single(ctx: dict):
            prompt = _build_single_prompt(ctx["context_text"])
            text = _ask_claude(prompt)
            return ctx, prompt, _decision_from_text(text), text, None

        with ThreadPoolExecutor(max_workers=_MAX_PARALLEL) as pool:
            raw = list(pool.map(_eval_single, contexts))
    else:
        # multi: 8 personality calls per cycle, parallelized within each cycle
        def _eval_one_agent(args):
            ctx, agent_key = args
            prompt = _build_personality_prompt(agent_key, ctx["context_text"])
            text = _ask_claude(prompt)
            decision, reason = _decision_and_reason(text)
            return agent_key, decision, reason, (text or "")[:200]

        raw = []
        for ctx in contexts:
            jobs = [(ctx, k) for k in _MULTI_AGENTS]
            # Fire all personalities at once so per-cycle latency equals the
            # SLOWEST agent (~13s) instead of two batches' slowest-of-each.
            with ThreadPoolExecutor(max_workers=_PARALLEL_PERSONALITIES) as pool:
                results = list(pool.map(_eval_one_agent, jobs))
            votes_map = {k: v for k, v, _, _ in results}
            agent_votes = [
                {"agent": k, "vote": v, "reason": r, "raw": rr}
                for k, v, r, rr in results
            ]
            decision = _vote_majority(votes_map)
            chosen = next((r for r in agent_votes if r["vote"] == decision), agent_votes[0])
            top_text = chosen["raw"]
            raw.append((ctx, ctx["context_text"], decision, top_text, agent_votes))

    # ── Phase 3 — replay sequentially to track open/close ─────
    decisions: list[dict] = []
    open_trade: dict | None = None
    closed_trades: list[dict] = []

    for entry in raw:
        ctx, prompt, decision, text, agent_votes = entry
        snap = ctx["snap"]
        idx = ctx["idx"]
        record = {
            "date": snap["date"],
            "price": snap["price"],
            "decision": decision,
            "raw_response": (text or "")[:200],
            "rsi": snap["rsi"],
            "regime": ctx["pulse"]["regime"],
            "sentiment": ctx["sentiment"]["label"],
            "trade_plan": ctx["plan"],
            "prompt": prompt,
            "agent_votes": agent_votes or [],
        }

        if decision == "BUY" and not open_trade:
            open_trade = {
                "symbol": symbol, "entry_date": snap["date"],
                "entry_price": snap["price"], "entry_idx": idx,
            }
            record["action"] = "OPEN"
        elif decision == "SELL" and open_trade:
            pnl_pct = ((snap["price"] - open_trade["entry_price"]) / open_trade["entry_price"]) * 100
            closed_trades.append({
                "symbol": symbol,
                "entry_date": open_trade["entry_date"],
                "entry_price": open_trade["entry_price"],
                "exit_date": snap["date"],
                "exit_price": snap["price"],
                "pnl_percent": pnl_pct,
                "hold_days": idx - open_trade["entry_idx"],
                "outcome": "win" if pnl_pct > 0 else "loss",
            })
            record["action"] = "CLOSE"
            record["pnl_percent"] = pnl_pct
            open_trade = None
        else:
            record["action"] = "HOLD"

        decisions.append(record)

    if open_trade:
        last_price = float(close.iloc[end_idx])
        pnl_pct = ((last_price - open_trade["entry_price"]) / open_trade["entry_price"]) * 100
        closed_trades.append({
            "symbol": symbol,
            "entry_date": open_trade["entry_date"],
            "entry_price": open_trade["entry_price"],
            "exit_date": str(df["date"].iloc[end_idx])[:10],
            "exit_price": last_price,
            "pnl_percent": pnl_pct,
            "hold_days": end_idx - open_trade["entry_idx"],
            "outcome": "win" if pnl_pct > 0 else "loss",
        })

    wins = [t for t in closed_trades if t["outcome"] == "win"]
    losses = [t for t in closed_trades if t["outcome"] == "loss"]
    win_rate = (len(wins) / len(closed_trades)) if closed_trades else 0.0
    avg_return = (sum(t["pnl_percent"] for t in closed_trades) / len(closed_trades)) if closed_trades else 0.0

    return {
        "symbol": symbol,
        "period": period,
        "mode": mode,
        "agents_used": _MULTI_AGENTS if mode == "multi" else [],
        "hold_days": hold_days,
        "cycles_run": len(decisions),
        "decisions": decisions,
        "trades": closed_trades,
        "win_count": len(wins),
        "loss_count": len(losses),
        "win_rate": win_rate,
        "avg_return": avg_return,
        "total_trades": len(closed_trades),
        "last_updated": datetime.utcnow().isoformat() + "Z",
    }


def run_ai_backtest_multi(symbols: list[str], period: str = "1M", cycles: int = 8,
                         mode: str = "single") -> dict:
    """Run AI Analyst on each symbol and return per-stock comparison rows.

    Each `run_ai_backtest()` call is cached for 6h on (symbol, period, cycles, mode),
    so the second pass over the same params is near-instant. Stocks are run
    sequentially to keep total Claude-subprocess concurrency bounded — peak load
    on multi mode (7 personalities × M stocks) would otherwise hit plan rate
    limits and slow each call down. With caching, the user re-running on the same
    list returns fast.
    """
    clean = [s.upper().strip() for s in (symbols or []) if s and s.strip()]
    clean = list(dict.fromkeys(clean))[:8]  # dedupe, cap at 8
    if not clean:
        return {
            "period": period, "mode": mode, "cycles": cycles,
            "rows": [], "error": "No symbols supplied.",
            "last_updated": datetime.utcnow().isoformat() + "Z",
        }

    rows: list[dict] = []
    for sym in clean:
        try:
            result = run_ai_backtest(sym, period=period, cycles=cycles, mode=mode)
        except Exception as e:
            result = {
                "symbol": sym, "period": period, "mode": mode,
                "cycles_run": 0, "decisions": [], "trades": [],
                "win_count": 0, "loss_count": 0, "win_rate": 0.0,
                "avg_return": 0.0, "total_trades": 0,
                "error": f"AI backtest failed for {sym}: {e}",
                "last_updated": datetime.utcnow().isoformat() + "Z",
            }
        rows.append(result)

    return {
        "period": period,
        "mode": mode,
        "cycles": cycles,
        "rows": rows,
        "last_updated": datetime.utcnow().isoformat() + "Z",
    }
