"""Enrich picked symbols with a real-data bullish option trade plan.

Orchestration (data + analysis), per CLAUDE.md -- lives in the service layer.
For each symbol: historical bars -> technical.analyze (price/ATR/support/
resistance) -> build_trade_plan; options chain -> select_contract (best-effort,
nullable). Decimals serialized to strings. Cached per symbol+day. No fabrication
-- any failure yields null contract (levels still computed) or omits the symbol.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from src.analysis import technical
from src.analysis.contract_selector import select_contract
from src.analysis.option_trade_plan import build_trade_plan
from src.utils.db import cache_get, cache_set, init_db, log_api_call

_CACHE_TTL_HOURS = 8
_DIRECTION = "bullish"  # agent daily picks are all BUY ideas


def _s(v) -> str | None:
    """Decimal/number -> string, passthrough None."""
    return None if v is None else str(v)


def _serialize_contract(c: dict | None) -> dict | None:
    if c is None:
        return None
    return {
        "type": c["type"],
        "strike": _s(c["strike"]),
        "expiry": c["expiry"],
        "premium": _s(c["premium"]),
        "delta": _s(c["delta"]),
        "iv": _s(c["iv"]),
        "dte": c["dte"],
    }


def _plan_for(symbol: str, gateway) -> dict | None:
    """Build one symbol's plan dict, or None if levels can't be computed."""
    try:
        df = gateway.get_historical(symbol, period_days=180)
    except Exception as exc:
        log_api_call("option_picks", symbol, "error", error=f"historical: {exc}")
        return None
    if df is None or len(df) < 20:
        return None

    ind = technical.analyze(symbol, df)
    if ind.current_price is None:
        return None

    plan = build_trade_plan(
        direction=_DIRECTION,
        price=ind.current_price,
        atr=ind.atr_14,
        support=ind.support,
        resistance=ind.resistance,
    )

    # Best-effort contract.
    contract = None
    try:
        chains = gateway.get_options_chain(symbol)
        contract = select_contract(chains, _DIRECTION) if chains else None
    except Exception as exc:
        log_api_call("option_picks", symbol, "error", error=f"chain: {exc}")
        contract = None

    return {
        "direction": plan["direction"],
        "entry": _s(plan["entry"]),
        "stop_loss": _s(plan["stop_loss"]),
        "take_profit": _s(plan["take_profit"]),
        "technical_target": _s(plan["technical_target"]),
        "support": _s(ind.support),
        "resistance": _s(ind.resistance),
        "atr": _s(ind.atr_14),
        "rr_ratio": plan["rr_ratio"],
        "rr_basis": plan["rr_basis"],
        "contract": _serialize_contract(contract),
        "contract_status": "ok" if contract is not None else "unavailable",
    }


def enrich_symbols(symbols: list[str], *, gateway=None) -> dict[str, dict]:
    """Return {symbol: plan} for the unique uppercased symbols. gateway is
    injectable for tests; defaults to a fresh DataGateway. Cached per symbol+day.
    Symbols whose levels can't be computed are omitted."""
    if gateway is None:
        from src.data.gateway import DataGateway
        gateway = DataGateway()

    init_db()
    today = date.today().isoformat()
    out: dict[str, dict] = {}
    seen = set()
    for raw in symbols:
        sym = (raw or "").upper().strip()
        if not sym or sym in seen:
            continue
        seen.add(sym)

        cache_key = f"option_plans:v1:{sym}:{today}"
        cached = cache_get(cache_key)
        if cached:
            out[sym] = cached
            continue

        plan = _plan_for(sym, gateway)
        if plan is not None:
            cache_set(cache_key, plan, ttl_minutes=_CACHE_TTL_HOURS * 60)
            out[sym] = plan
    return out
