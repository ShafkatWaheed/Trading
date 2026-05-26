"""Co-holders service — top institutional holders + the stocks they ALSO own.

Composes two queries the frontend would otherwise need to N+1:
  1. ownership_service.top_holders(symbol)  — who owns this stock
  2. for each holder, ownership_service.also_held(cik) — what else they hold

Then aggregates: which OTHER stocks are most frequently held by this stock's
top holders. That aggregated "co-held with" list is the interconnection story —
when Vanguard, BlackRock, and Renaissance all hold NVDA + AMD + AVGO, that
overlap signals an institutional thesis.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from src.utils.db import cache_get, cache_set
from api.services import ownership_service

_CACHE_TTL_MINUTES = 6 * 60
_TOP_HOLDERS = 10           # how many holders to introspect
_PEEK_HOLDINGS = 25         # how many of each holder's other holdings to scan
_MAX_OVERLAP_STOCKS = 10    # cap the aggregated co-held list


def get_co_holders(symbol: str, force: bool = False) -> dict:
    symbol = symbol.upper()
    cache_key = f"co_holders:v1:{symbol}"
    if not force:
        cached = cache_get(cache_key)
        if cached:
            cached["from_cache"] = True
            return cached

    top = ownership_service.top_holders(symbol, max_results=_TOP_HOLDERS)
    holders_raw = top.get("holders") or []

    # For each holder, peek at their other top holdings (excluding this symbol).
    enriched_holders: list[dict] = []
    overlap: dict[str, dict] = defaultdict(
        lambda: {"symbol": "", "stock_name": None, "co_holder_count": 0, "total_value_usd": 0.0, "holders": []}
    )

    for h in holders_raw:
        cik = h.get("cik")
        also = ownership_service.also_held(cik, max_results=_PEEK_HOLDINGS) if cik else {"holdings": []}
        other = [r for r in (also.get("holdings") or []) if (r.get("symbol") or "").upper() != symbol][:5]
        enriched_holders.append({
            "cik": cik,
            "name": h.get("institution_name"),
            "type": h.get("institution_type"),
            "value_usd": h.get("value_usd"),
            "pct_outstanding": h.get("pct_outstanding"),
            "pct_portfolio": h.get("pct_portfolio"),
            "as_of": h.get("as_of"),
            "also_holds": [
                {
                    "symbol": (r.get("symbol") or "").upper(),
                    "stock_name": r.get("stock_name"),
                    "pct_portfolio": r.get("pct_portfolio"),
                    "value_usd": r.get("value_usd"),
                }
                for r in other
            ],
        })

        # Aggregate overlap across ALL their holdings (not just top 5)
        for r in (also.get("holdings") or []):
            other_sym = (r.get("symbol") or "").upper()
            if not other_sym or other_sym == symbol:
                continue
            o = overlap[other_sym]
            o["symbol"] = other_sym
            o["stock_name"] = r.get("stock_name") or o["stock_name"]
            o["co_holder_count"] += 1
            o["total_value_usd"] += float(r.get("value_usd") or 0)
            holder_name = h.get("institution_name")
            if holder_name and holder_name not in o["holders"]:
                o["holders"].append(holder_name)

    # Rank co-held stocks by count first, then by total $ overlap
    overlap_list = sorted(
        overlap.values(),
        key=lambda x: (-x["co_holder_count"], -x["total_value_usd"]),
    )[:_MAX_OVERLAP_STOCKS]

    # Story line — synthesized from counts
    n_holders = len(enriched_holders)
    n_overlap = len(overlap_list)
    if n_holders == 0:
        lede = f"No institutional holdings of {symbol} tracked yet."
    elif n_overlap == 0:
        lede = f"{n_holders} institutions hold {symbol}, but they share no other major positions."
    else:
        top_two = ", ".join(o["symbol"] for o in overlap_list[:2])
        lede = (
            f"{n_holders} of the biggest institutional investors hold {symbol}. "
            f"They also tend to hold {top_two} — a shared thesis runs through their books."
        )

    payload = {
        "symbol": symbol,
        "available": n_holders > 0,
        "lede": lede,
        "holders": enriched_holders,
        "co_held": overlap_list,
        "total_holders": n_holders,
        "from_cache": False,
        "last_updated": datetime.utcnow().isoformat() + "Z",
    }

    try:
        cache_set(cache_key, payload, ttl_minutes=_CACHE_TTL_MINUTES)
    except Exception:
        pass
    return payload
