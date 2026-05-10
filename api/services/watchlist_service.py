"""Watchlist service: read + add + remove."""
from __future__ import annotations

from src.utils.db import (
    init_db, get_watchlist, add_watchlist_item, remove_watchlist_item,
)
from src.data.gateway import DataGateway


def list_watchlist() -> list[dict]:
    init_db()
    return [
        {"symbol": item["symbol"]}
        for item in (get_watchlist() or [])
    ]


def add(symbol: str) -> dict:
    init_db()
    symbol = symbol.upper().strip()
    if not symbol:
        return {"ok": False, "error": "Empty symbol"}

    # Validate via Yahoo Finance — quote should resolve
    try:
        gw = DataGateway()
        q = gw.get_quote(symbol)
        if not q or getattr(q, "price", None) is None:
            return {"ok": False, "error": f"Ticker '{symbol}' not found"}
    except Exception as e:
        return {"ok": False, "error": f"Could not validate '{symbol}': {e}"}

    add_watchlist_item(symbol)
    return {"ok": True, "symbol": symbol}


def remove(symbol: str) -> dict:
    init_db()
    remove_watchlist_item(symbol.upper().strip())
    return {"ok": True}


def add_top5(top5: list[str]) -> dict:
    init_db()
    existing = {item["symbol"] for item in (get_watchlist() or [])}
    added = []
    for s in top5:
        sym = s.upper().strip()
        if sym and sym not in existing:
            add_watchlist_item(sym)
            added.append(sym)
    return {"ok": True, "added": added}
