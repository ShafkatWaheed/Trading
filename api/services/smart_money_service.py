"""Smart-money flow — institutional + insider + congressional activity for a stock.

Combines three independent sources, each best-effort (one failing doesn't kill
the others). Cached for 6h since 13F is quarterly and Form 4 / congressional
filings trickle in daily.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from src.utils.db import cache_get, cache_set
from api.services import ownership_service

_CACHE_TTL_MINUTES = 6 * 60


def _to_float(v) -> float | None:
    try:
        if v is None:
            return None
        if isinstance(v, Decimal):
            return float(v)
        return float(v)
    except (TypeError, ValueError):
        return None


# ── Institutional (top holders + recent additions/trims) ──────────


def _institutional_section(symbol: str) -> dict:
    out: dict = {
        "top_holders": [],
        "total_known_holders": 0,
        "error": None,
    }
    try:
        data = ownership_service.top_holders(symbol, max_results=10)
        out["total_known_holders"] = data.get("total", 0)
        for h in data.get("holders", []):
            out["top_holders"].append({
                "name":              h.get("institution_name") or h.get("cik"),
                "type":              h.get("institution_type"),
                "value_usd":         _to_float(h.get("value_usd")),
                "pct_outstanding":   _to_float(h.get("pct_outstanding")),
                "pct_portfolio":     _to_float(h.get("pct_portfolio")),
                "as_of":             h.get("as_of"),
            })
    except Exception as e:
        out["error"] = f"Institutional fetch failed: {e}"
    return out


# ── Insider (last 90d Form 4) ─────────────────────────────────────


def _insider_section(symbol: str) -> dict:
    out: dict = {
        "total_trades": 0,
        "total_buys": 0,
        "total_sells": 0,
        "unique_insiders": 0,
        "cluster_buy": False,
        "buy_value_usd": None,
        "sell_value_usd": None,
        "net_value_usd": None,
        "signal": "",
        "recent_trades": [],
        "error": None,
    }
    try:
        from src.data.sec_edgar import SECEdgarProvider
        prov = SECEdgarProvider()
        s = prov.get_insider_summary(symbol, days=90)
        buy_v = _to_float(s.buy_value) or 0.0
        sell_v = _to_float(s.sell_value) or 0.0
        out.update({
            "total_trades":     s.total_trades,
            "total_buys":       s.total_buys,
            "total_sells":      s.total_sells,
            "unique_insiders":  s.unique_insiders,
            "cluster_buy":      bool(s.cluster_buy),
            "buy_value_usd":    buy_v,
            "sell_value_usd":   sell_v,
            "net_value_usd":    buy_v - sell_v,
            "signal":           s.signal or "",
        })
        for t in (s.recent_trades or [])[:10]:
            out["recent_trades"].append({
                "filer":             t.filer_name,
                "title":             t.filer_title,
                "transaction":       t.transaction_type,
                "shares":            t.shares,
                "price":             _to_float(t.price),
                "value_usd":         _to_float(t.total_value),
                "transaction_date":  t.transaction_date,
                "filing_date":       t.filing_date,
            })
    except Exception as e:
        out["error"] = f"Insider fetch failed: {e}"
    return out


# ── Congressional (Capitol Trades, last 180d) ─────────────────────


def _congress_section(symbol: str) -> dict:
    out: dict = {
        "total_trades": 0,
        "total_buys": 0,
        "total_sells": 0,
        "unique_politicians": 0,
        "net_sentiment": "neutral",
        "top_buyers": [],
        "top_sellers": [],
        "recent_trades": [],
        "party_breakdown": {},
        "error": None,
    }
    try:
        from src.data.congress import CongressDataProvider
        prov = CongressDataProvider()
        s = prov.get_summary(symbol, days=180)
        out.update({
            "total_trades":       s.total_trades,
            "total_buys":         s.total_buys,
            "total_sells":        s.total_sells,
            "unique_politicians": s.unique_politicians,
            "net_sentiment":      s.net_sentiment or "neutral",
            "top_buyers":         list(s.top_buyers)[:25],
            "top_sellers":        list(s.top_sellers)[:25],
            "party_breakdown":    s.party_breakdown or {},
        })
        for t in (s.recent_trades or [])[:50]:
            out["recent_trades"].append({
                "politician":        t.politician,
                "party":             t.party,
                "chamber":           t.chamber,
                "state":             t.state,
                "transaction":       t.transaction_type,
                "amount_range":      t.amount_range,
                "amount_low_usd":    _to_float(t.amount_low),
                "amount_high_usd":   _to_float(t.amount_high),
                "trade_date":        t.trade_date,
                "filed_date":        t.filed_date,
                "days_to_file":      t.days_to_file,
                "committees":        list(t.committees) if t.committees else [],
            })
    except Exception as e:
        out["error"] = f"Congressional fetch failed: {e}"
    return out


# ── Composite read-out ────────────────────────────────────────────


def _summary_signal(institutional: dict, insider: dict, congress: dict) -> str:
    """One-line plain-English readout combining all three signals."""
    parts: list[str] = []

    # Insider weight
    if insider["cluster_buy"]:
        parts.append("multiple insiders buying together (cluster-buy)")
    elif insider["total_buys"] > insider["total_sells"] and (insider["net_value_usd"] or 0) > 0:
        parts.append(f"insiders net buying (${insider['net_value_usd']:,.0f})")
    elif insider["total_sells"] > insider["total_buys"] and (insider["net_value_usd"] or 0) < 0:
        parts.append(f"insiders net selling (${abs(insider['net_value_usd']):,.0f})")

    # Congress weight
    if congress["net_sentiment"] in ("strong_buy", "buy"):
        parts.append(f"{congress['unique_politicians']} politicians buying")
    elif congress["net_sentiment"] in ("strong_sell", "sell"):
        parts.append(f"{congress['unique_politicians']} politicians selling")

    # Institutional weight
    if institutional["total_known_holders"] > 0:
        parts.append(f"{institutional['total_known_holders']} institutional holders tracked")

    return "; ".join(parts) if parts else "No notable smart-money activity in the tracking window."


def get_smart_money(symbol: str, force: bool = False) -> dict:
    symbol = symbol.upper()
    cache_key = f"smart_money:v1:{symbol}"

    if not force:
        cached = cache_get(cache_key)
        if cached:
            cached["from_cache"] = True
            return cached

    institutional = _institutional_section(symbol)
    insider       = _insider_section(symbol)
    congress      = _congress_section(symbol)

    payload = {
        "symbol":        symbol,
        "institutional": institutional,
        "insider":       insider,
        "congress":      congress,
        "summary":       _summary_signal(institutional, insider, congress),
        "last_updated":  datetime.utcnow().isoformat() + "Z",
        "from_cache":    False,
    }

    try:
        cache_set(cache_key, payload, ttl_minutes=_CACHE_TTL_MINUTES)
    except Exception:
        pass
    return payload
