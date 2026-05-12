"""Peer valuation strip — shows the stock's P/E, P/S, 1Y next to a handful of peers.

Reuses peer_service.get_peers() for the peer list, then fetches lightweight
valuation snapshots for each via yfinance (cached separately).
"""
from __future__ import annotations

from datetime import datetime

from src.utils.db import cache_get, cache_set
from api.services import peer_service

_CACHE_TTL_MINUTES = 6 * 60
_MAX_PEERS = 6  # keep the strip scannable


def _safe_float(v) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _fetch_snapshot(symbol: str) -> dict:
    """Cheap yf snapshot of P/E, P/S, P/FCF, 1Y change."""
    cache_key = f"peer_snapshot:v1:{symbol}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    out: dict = {
        "symbol": symbol,
        "pe_ratio": None, "ps_ratio": None, "pfcf_ratio": None,
        "price_change_1y_pct": None,
    }
    try:
        import yfinance as yf
        t = yf.Ticker(symbol)
        info = t.info or {}
        out["pe_ratio"] = _safe_float(info.get("trailingPE"))
        out["ps_ratio"] = _safe_float(info.get("priceToSalesTrailing12Months"))
        mc = _safe_float(info.get("marketCap"))
        fcf = _safe_float(info.get("freeCashflow"))
        if mc and fcf and fcf > 0:
            out["pfcf_ratio"] = round(mc / fcf, 1)

        hist = t.history(period="1y")
        if hist is not None and len(hist) >= 2:
            start = float(hist["Close"].iloc[0])
            end = float(hist["Close"].iloc[-1])
            if start > 0:
                out["price_change_1y_pct"] = round(((end - start) / start) * 100.0, 1)
    except Exception:
        pass

    # round
    for k in ("pe_ratio", "ps_ratio"):
        if out[k] is not None:
            out[k] = round(out[k], 1)

    try:
        cache_set(cache_key, out, ttl_minutes=_CACHE_TTL_MINUTES)
    except Exception:
        pass
    return out


def get_peer_valuation(symbol: str, force: bool = False) -> dict:
    symbol = symbol.upper()
    cache_key = f"peer_valuation:v1:{symbol}"
    if not force:
        cached = cache_get(cache_key)
        if cached:
            cached["from_cache"] = True
            return cached

    peers_raw = peer_service.get_peers(symbol, max_results=_MAX_PEERS)
    peer_syms = [p["symbol"] for p in (peers_raw.get("peers") or [])][:_MAX_PEERS]

    all_syms = [symbol] + [p for p in peer_syms if p != symbol]
    rows: list[dict] = []
    for s in all_syms:
        snap = _fetch_snapshot(s)
        rows.append({
            "symbol": s,
            "is_self": s == symbol,
            "pe_ratio": snap["pe_ratio"],
            "ps_ratio": snap["ps_ratio"],
            "pfcf_ratio": snap["pfcf_ratio"],
            "price_change_1y_pct": snap["price_change_1y_pct"],
        })

    # Compute peer medians (excluding self)
    def _median(values: list[float]) -> float | None:
        clean = sorted([v for v in values if v is not None])
        if not clean:
            return None
        mid = len(clean) // 2
        if len(clean) % 2:
            return round(clean[mid], 1)
        return round((clean[mid - 1] + clean[mid]) / 2, 1)

    peers_only = [r for r in rows if not r["is_self"]]
    medians = {
        "pe_ratio":  _median([r["pe_ratio"]  for r in peers_only]),
        "ps_ratio":  _median([r["ps_ratio"]  for r in peers_only]),
        "pfcf_ratio": _median([r["pfcf_ratio"] for r in peers_only]),
        "price_change_1y_pct": _median([r["price_change_1y_pct"] for r in peers_only]),
    }

    payload = {
        "symbol": symbol,
        "rows": rows,
        "medians": medians,
        "from_cache": False,
        "last_updated": datetime.utcnow().isoformat() + "Z",
    }

    try:
        cache_set(cache_key, payload, ttl_minutes=_CACHE_TTL_MINUTES)
    except Exception:
        pass
    return payload
