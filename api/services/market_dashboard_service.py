"""Live market header + breadth + top movers — combined into one cached endpoint.

Three sub-payloads share yfinance fetches and pandas processing, so we batch them
together. Sub-cache TTLs:
  - live indices: 5 min (refresh during trading)
  - breadth: 1 hour
  - top movers: 15 min
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from src.utils.db import cache_get, cache_set

_CACHE_TTL_MINUTES = 5  # outer cache for the whole payload


# ── Helpers ───────────────────────────────────────────────────────


def _safe_float(v) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _ny_now() -> datetime:
    return datetime.now(ZoneInfo("America/New_York"))


def _market_status() -> dict:
    """NYSE regular hours: Mon-Fri 09:30–16:00 ET."""
    now = _ny_now()
    weekday = now.weekday()  # 0=Mon 6=Sun
    minutes = now.hour * 60 + now.minute

    if weekday >= 5:
        # Find next Monday 09:30
        days_to_mon = (7 - weekday) % 7 or 1
        next_open = (now + timedelta(days=days_to_mon)).replace(hour=9, minute=30, second=0, microsecond=0)
        return {
            "status": "closed",
            "label": "MARKET CLOSED (weekend)",
            "minutes_to_open": int((next_open - now).total_seconds() / 60),
            "minutes_to_close": None,
        }

    open_min = 9 * 60 + 30
    close_min = 16 * 60
    pre_open_min = 4 * 60        # ECN pre-market opens 04:00 ET
    after_close_max = 20 * 60    # extended hours close 20:00 ET

    if minutes < pre_open_min:
        return {
            "status": "closed",
            "label": "MARKET CLOSED",
            "minutes_to_open": open_min - minutes,
            "minutes_to_close": None,
        }
    if minutes < open_min:
        return {
            "status": "pre_market",
            "label": "PRE-MARKET",
            "minutes_to_open": open_min - minutes,
            "minutes_to_close": None,
        }
    if minutes < close_min:
        return {
            "status": "open",
            "label": "MARKET OPEN",
            "minutes_to_open": None,
            "minutes_to_close": close_min - minutes,
        }
    if minutes < after_close_max:
        return {
            "status": "after_hours",
            "label": "AFTER HOURS",
            "minutes_to_open": (24 * 60 - minutes) + open_min,
            "minutes_to_close": None,
        }
    return {
        "status": "closed",
        "label": "MARKET CLOSED",
        "minutes_to_open": (24 * 60 - minutes) + open_min,
        "minutes_to_close": None,
    }


# ── Index snapshots (live header) ─────────────────────────────────


_INDEX_TICKERS = {
    "spx":   ("^GSPC",   "S&P 500"),
    "ndx":   ("^IXIC",   "Nasdaq"),
    "dow":   ("^DJI",    "Dow Jones"),
    "vix":   ("^VIX",    "VIX"),
    "t10y":  ("^TNX",    "10Y Treasury"),
}


def _fetch_index_snapshot(label_key: str, ticker: str, display: str) -> dict:
    """Return latest price + 1d change + 30-day spark array (close prices, normalized to 100)."""
    out: dict = {
        "key": label_key, "ticker": ticker, "display": display,
        "price": None, "change": None, "change_pct": None,
        "spark": [], "change_30d_pct": None,
    }
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        # Pull ~2 months so we have enough for both the spark and 1d change.
        hist = t.history(period="2mo", interval="1d", auto_adjust=False)
        if hist is None or hist.empty:
            return out
        closes = hist["Close"].dropna().astype(float).tolist()
        if not closes:
            return out
        last = closes[-1]
        prev = closes[-2] if len(closes) >= 2 else last
        out["price"] = round(last, 2)
        out["change"] = round(last - prev, 2)
        out["change_pct"] = round(((last - prev) / prev) * 100.0, 2) if prev else 0.0
        # 30-day spark: last 30 sessions, normalized so frontend can draw any
        # height without re-scaling.
        recent = closes[-30:]
        out["spark"] = [round(c, 4) for c in recent]
        if len(recent) >= 2 and recent[0] > 0:
            out["change_30d_pct"] = round(((recent[-1] - recent[0]) / recent[0]) * 100.0, 2)
    except Exception:
        pass
    return out


def _index_snapshots() -> list[dict]:
    items = list(_INDEX_TICKERS.items())
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(
            lambda kv: _fetch_index_snapshot(kv[0], kv[1][0], kv[1][1]),
            items,
        ))
    return results


# ── Market breadth ────────────────────────────────────────────────


_BREADTH_TICKERS = ["SPY", "RSP", "IWM", "QQQ"]


def _breadth() -> dict:
    """Compute breadth proxies:
      - SPY vs RSP (cap-weighted vs equal-weighted): if RSP lags, rally is narrow
      - IWM (small caps) vs SPY: if IWM trails, breadth is weak
      - VIX regime: <15 calm · 15-25 normal · 25-35 stressed · 35+ panic
    Plus a one-line headline classification.
    """
    out: dict = {
        "spy_vs_rsp_1m_pp":   None,  # SPY % − RSP % over 1M (in percentage points)
        "iwm_vs_spy_1m_pp":   None,
        "vix_level":          None,
        "vix_regime":         None,
        "spy_pct_above_50d":  None,
        "spy_pct_above_200d": None,
        "headline":           "",
    }

    try:
        import yfinance as yf
        df = yf.download(
            _BREADTH_TICKERS + ["^VIX"],
            period="6mo", interval="1d",
            progress=False, auto_adjust=False,
            group_by="ticker", threads=False,
        )

        def _series(tkr: str):
            try:
                if df.columns.nlevels > 1 and tkr in df.columns.get_level_values(0):
                    return df[tkr]["Close"].dropna()
            except Exception:
                pass
            return None

        def _pct_change_1m(s):
            if s is None or len(s) < 21:
                return None
            return round(((s.iloc[-1] - s.iloc[-21]) / s.iloc[-21]) * 100.0, 2)

        spy = _series("SPY")
        rsp = _series("RSP")
        iwm = _series("IWM")
        vix = _series("^VIX")

        spy_1m = _pct_change_1m(spy)
        rsp_1m = _pct_change_1m(rsp)
        iwm_1m = _pct_change_1m(iwm)

        if spy_1m is not None and rsp_1m is not None:
            out["spy_vs_rsp_1m_pp"] = round(spy_1m - rsp_1m, 2)
        if iwm_1m is not None and spy_1m is not None:
            out["iwm_vs_spy_1m_pp"] = round(iwm_1m - spy_1m, 2)

        if spy is not None:
            last = float(spy.iloc[-1])
            sma50 = float(spy.tail(50).mean()) if len(spy) >= 50 else None
            sma200 = float(spy.tail(200).mean()) if len(spy) >= 200 else None
            if sma50:
                out["spy_pct_above_50d"] = round(((last - sma50) / sma50) * 100.0, 2)
            if sma200:
                out["spy_pct_above_200d"] = round(((last - sma200) / sma200) * 100.0, 2)

        if vix is not None and len(vix) > 0:
            v = float(vix.iloc[-1])
            out["vix_level"] = round(v, 2)
            if v < 15:    out["vix_regime"] = "calm"
            elif v < 25:  out["vix_regime"] = "normal"
            elif v < 35:  out["vix_regime"] = "stressed"
            else:         out["vix_regime"] = "panic"
    except Exception:
        pass

    # Headline classification
    bits: list[str] = []
    if out["spy_vs_rsp_1m_pp"] is not None:
        if out["spy_vs_rsp_1m_pp"] > 1.5:
            bits.append("rally is narrow (mega-caps leading)")
        elif out["spy_vs_rsp_1m_pp"] < -1.5:
            bits.append("rally is broad (equal-weight leading)")
    if out["iwm_vs_spy_1m_pp"] is not None and out["iwm_vs_spy_1m_pp"] < -3:
        bits.append("small-caps lagging")
    if out["vix_regime"] == "calm":
        bits.append("low volatility")
    elif out["vix_regime"] in ("stressed", "panic"):
        bits.append(f"volatility {out['vix_regime']}")
    out["headline"] = "; ".join(bits) if bits else "mixed breadth signals"

    return out


# ── Top movers (from S&P 500 / mega-caps universe) ────────────────


_MOVERS_UNIVERSE = [
    # Mega-caps
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AVGO",
    "BRK-B", "LLY", "JPM", "V", "UNH", "XOM", "WMT", "MA", "JNJ",
    "PG", "HD", "MRK", "ABBV", "CVX", "BAC", "KO", "PEP", "COST",
    "ORCL", "ADBE", "CRM", "AMD", "NFLX", "TMO", "MCD", "ACN", "CSCO",
    "INTC", "QCOM", "TXN", "INTU", "DIS", "PYPL", "PFE", "T", "VZ",
    "BA", "CAT", "GE", "RTX", "HON", "LMT", "DE",
    # Higher-volatility mid-caps + popular trade names (mid-caps move more)
    "PLTR", "SHOP", "SNOW", "COIN", "UBER", "ABNB", "RBLX", "DASH",
    "SOFI", "AFRM", "HOOD", "RIVN", "LCID", "PYPL", "SQ", "MARA",
    "RIOT", "CLSK", "PLUG", "FUBO", "DKNG", "PINS", "SNAP", "ROKU",
    "U", "DDOG", "MDB", "NET", "CRWD", "ZS", "PANW", "OKTA",
    # Quantum / disruption names
    "IONQ", "RGTI", "QBTS", "ARQQ",
    # Biotech / pharma volatility
    "MRNA", "BNTX", "REGN", "VRTX", "GILD", "BIIB",
    # Semis (non-mega)
    "MU", "AMAT", "LRCX", "MRVL", "ON", "ARM",
]


def _top_movers(limit: int = 5) -> dict:
    """Biggest gainers / losers for BOTH 1-day and 5-day windows."""
    out: dict = {
        "gainers_1d": [], "losers_1d": [],
        "gainers_5d": [], "losers_5d": [],
        "error": None,
    }
    try:
        import yfinance as yf
        df = yf.download(
            _MOVERS_UNIVERSE, period="10d", interval="1d",
            progress=False, auto_adjust=False, group_by="ticker", threads=False,
        )
        rows_1d: list[dict] = []
        rows_5d: list[dict] = []
        for sym in _MOVERS_UNIVERSE:
            try:
                if df.columns.nlevels > 1 and sym in df.columns.get_level_values(0):
                    s = df[sym]["Close"].dropna()
                    if len(s) >= 2:
                        last = float(s.iloc[-1])
                        prev = float(s.iloc[-2])
                        if prev > 0:
                            pct = ((last - prev) / prev) * 100.0
                            rows_1d.append({
                                "symbol":      sym,
                                "price":       round(last, 2),
                                "change_pct":  round(pct, 2),
                                "change":      round(last - prev, 2),
                            })
                    if len(s) >= 6:
                        last = float(s.iloc[-1])
                        five_ago = float(s.iloc[-6])
                        if five_ago > 0:
                            pct = ((last - five_ago) / five_ago) * 100.0
                            rows_5d.append({
                                "symbol":      sym,
                                "price":       round(last, 2),
                                "change_pct":  round(pct, 2),
                                "change":      round(last - five_ago, 2),
                            })
            except Exception:
                continue

        rows_1d.sort(key=lambda r: r["change_pct"], reverse=True)
        rows_5d.sort(key=lambda r: r["change_pct"], reverse=True)
        out["gainers_1d"] = rows_1d[:limit]
        out["losers_1d"]  = list(reversed(rows_1d[-limit:]))
        out["gainers_5d"] = rows_5d[:limit]
        out["losers_5d"]  = list(reversed(rows_5d[-limit:]))
    except Exception as e:
        out["error"] = str(e)[:120]
    return out


# ── Public entry ──────────────────────────────────────────────────


def get_market_dashboard(force: bool = False) -> dict:
    cache_key = "market_dashboard:v1"

    if not force:
        cached = cache_get(cache_key)
        if cached:
            cached["from_cache"] = True
            return cached

    indices  = _index_snapshots()
    breadth  = _breadth()
    movers   = _top_movers(limit=5)
    status   = _market_status()

    payload = {
        "status":       status,
        "indices":      indices,
        "breadth":      breadth,
        "movers":       movers,
        "last_updated": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "from_cache":   False,
    }

    # Only cache when we got real data. Caching an all-empty payload would
    # stick a broken response in front of users for 5 minutes after a transient
    # upstream blip.
    has_indices = any(i.get("price") is not None for i in indices)
    has_breadth = any(
        breadth.get(k) is not None
        for k in ("vix_level", "spy_pct_above_50d", "spy_vs_rsp_1m_pp")
    )
    if has_indices and has_breadth:
        try:
            cache_set(cache_key, payload, ttl_minutes=_CACHE_TTL_MINUTES)
        except Exception:
            pass
    return payload
