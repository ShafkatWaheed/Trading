"""Pure contract selection from an already-fetched options chain.

Per CLAUDE.md: analysis layer is pure -- operates on the passed OptionsChain
list, no network. Returns None (never a fabricated contract) when there is no
usable, priced contract on the needed side. `now_date` is injectable so DTE math
is deterministic in tests.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal


def _today(now_date: str | None) -> date:
    if now_date:
        return datetime.strptime(now_date, "%Y-%m-%d").date()
    return datetime.utcnow().date()


def _dte(expiration: str, today: date) -> int | None:
    try:
        return (datetime.strptime(expiration, "%Y-%m-%d").date() - today).days
    except Exception:
        return None


def _premium(c) -> Decimal | None:
    """Mid of bid/ask when both positive, else last_price when positive."""
    if c.bid and c.ask and c.bid > 0 and c.ask > 0:
        return (c.bid + c.ask) / 2
    if c.last_price and c.last_price > 0:
        return c.last_price
    return None


def select_contract(chains, direction: str, *, dte_target: int = 35,
                    now_date: str | None = None) -> dict | None:
    """Pick a near-the-money, priced contract on the side implied by direction.

    chains: list[OptionsChain] (one per expiration), as returned by
    DataGateway.get_options_chain. Bullish -> call, bearish -> put. Chooses the
    expiry whose DTE is closest to dte_target (only expiries that have a priced
    contract on the needed side), then the strike nearest the underlying price.
    Returns {type, strike, expiry, premium, delta, iv, dte} or None.
    """
    if not chains:
        return None
    today = _today(now_date)
    want = "put" if direction == "bearish" else "call"

    # Candidate expiries: those with at least one priced contract on our side.
    scored = []
    for ch in chains:
        side = ch.puts if want == "put" else ch.calls
        priced = [c for c in side if _premium(c) is not None]
        if not priced:
            continue
        d = _dte(ch.expiration, today)
        if d is None:
            continue
        scored.append((abs(d - dte_target), d, ch, priced))
    if not scored:
        return None

    scored.sort(key=lambda t: (t[0], t[1]))
    _, dte, chosen, priced = scored[0]
    price = chosen.underlying_price
    best = min(priced, key=lambda c: abs(c.strike - price))
    return {
        "type": want,
        "strike": best.strike,
        "expiry": chosen.expiration,
        "premium": _premium(best),
        "delta": best.delta,
        "iv": best.implied_volatility,
        "dte": dte,
    }
