"""Pure tests for contract_selector.select_contract (no I/O)."""
from __future__ import annotations

from decimal import Decimal

from src.analysis.contract_selector import select_contract
from src.models.data_types import OptionContract, OptionsChain


def _contract(ctype, strike, exp, bid, ask, last, iv, delta):
    return OptionContract(
        symbol=f"{ctype}{strike}", underlying="SYN", contract_type=ctype,
        strike=Decimal(str(strike)), expiration=exp,
        bid=Decimal(str(bid)), ask=Decimal(str(ask)), last_price=Decimal(str(last)),
        volume=10, open_interest=100, implied_volatility=Decimal(str(iv)),
        delta=Decimal(str(delta)),
    )


def _chain(exp, calls, puts, price=100):
    return OptionsChain(underlying="SYN", underlying_price=Decimal(str(price)),
                        expiration=exp, calls=calls, puts=puts)


def _two_expiry_chains():
    # underlying at 100; two expiries, strikes 95/100/105
    near = _chain("2026-06-20", calls=[
        _contract("call", 95, "2026-06-20", 6, 6.4, 6.2, 0.30, 0.7),
        _contract("call", 100, "2026-06-20", 3, 3.4, 3.2, 0.28, 0.5),
        _contract("call", 105, "2026-06-20", 1, 1.4, 1.2, 0.27, 0.3),
    ], puts=[
        _contract("put", 100, "2026-06-20", 3, 3.4, 3.2, 0.29, -0.5),
    ])
    far = _chain("2026-08-21", calls=[
        _contract("call", 100, "2026-08-21", 5, 5.4, 5.2, 0.31, 0.55),
    ], puts=[])
    return [near, far]


def test_bullish_picks_nearest_dte_and_strike():
    # now=2026-06-01, dte_target=35 -> 2026-06-20 (19d) vs 2026-08-21 (81d):
    # |19-35|=16 < |81-35|=46 -> near expiry. Nearest strike to 100 -> 100.
    c = select_contract(_two_expiry_chains(), "bullish",
                        dte_target=35, now_date="2026-06-01")
    assert c is not None
    assert c["type"] == "call"
    assert c["strike"] == Decimal("100")
    assert c["expiry"] == "2026-06-20"
    assert c["premium"] == Decimal("3.2")   # mid of 3.0/3.4
    assert c["delta"] == Decimal("0.5")
    assert c["iv"] == Decimal("0.28")
    assert c["dte"] == 19


def test_bearish_picks_put():
    c = select_contract(_two_expiry_chains(), "bearish",
                        dte_target=35, now_date="2026-06-01")
    assert c is not None
    assert c["type"] == "put"
    assert c["strike"] == Decimal("100")


def test_empty_chains_returns_none():
    assert select_contract([], "bullish", now_date="2026-06-01") is None


def test_no_calls_returns_none_for_bullish():
    chain = _chain("2026-06-20", calls=[], puts=[
        _contract("put", 100, "2026-06-20", 3, 3.4, 3.2, 0.29, -0.5)])
    assert select_contract([chain], "bullish", now_date="2026-06-01") is None


def test_unpriced_contract_skipped():
    # only an unpriced call (bid/ask/last all 0) -> None
    chain = _chain("2026-06-20", calls=[
        _contract("call", 100, "2026-06-20", 0, 0, 0, 0.0, 0.5)], puts=[])
    assert select_contract([chain], "bullish", now_date="2026-06-01") is None
