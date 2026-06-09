"""Tests for yf_options.get_options_chain (free yfinance fallback)."""
from __future__ import annotations

from decimal import Decimal

import pandas as pd
import pytest
import yfinance

import src.data.yf_options as yfo
from src.utils.db import init_db


@pytest.fixture(autouse=True)
def _init_schema():
    """Ensure the temp test DB has the api_log table before any test runs."""
    init_db()


def _frame(strikes):
    """Build a minimal options DataFrame with the columns yfinance returns."""
    return pd.DataFrame([
        {
            "strike": s,
            "bid": 1.0,
            "ask": 1.2,
            "lastPrice": 1.1,
            "volume": 10,
            "openInterest": 100,
            "impliedVolatility": 0.3,
            "contractSymbol": f"X{s}",
        }
        for s in strikes
    ])


class _OC:
    def __init__(self, calls, puts):
        self.calls = calls
        self.puts = puts


class _FakeTicker:
    """Fake yf.Ticker with 3 expirations at ~10, ~35, ~80 DTE from 2026-06-01."""

    def __init__(self, sym):
        self.fast_info = {"lastPrice": 100.0}
        self.options = ["2026-06-11", "2026-07-06", "2026-08-20"]

    def option_chain(self, exp):
        return _OC(_frame([95, 100, 105]), _frame([95, 100, 105]))


class _NoOptTicker:
    fast_info = {"lastPrice": 5.0}
    options = []

    def option_chain(self, exp):
        raise AssertionError("should not be called")


def test_builds_chain_and_picks_near_dte(monkeypatch):
    """get_options_chain returns max_expirations chains, choosing by DTE proximity."""
    monkeypatch.setattr(yfinance, "Ticker", _FakeTicker)

    chains = yfo.get_options_chain("AAA", dte_target=35, max_expirations=2, now_date="2026-06-01")

    assert len(chains) == 2
    exps = {c.expiration for c in chains}
    # ~35 DTE from 2026-06-01 → 2026-07-06 (35 days) should be chosen
    assert "2026-07-06" in exps
    c0 = next(c for c in chains if c.expiration == "2026-07-06")
    assert c0.underlying == "AAA"
    assert c0.underlying_price == Decimal("100")
    assert len(c0.calls) == 3
    assert len(c0.puts) == 3
    assert c0.calls[0].delta is None
    assert c0.calls[0].implied_volatility == Decimal("0.3")


def test_contract_fields_coerced(monkeypatch):
    """OptionContract fields are Decimal, not float; symbol set from contractSymbol."""
    monkeypatch.setattr(yfinance, "Ticker", _FakeTicker)

    chains = yfo.get_options_chain("AAA", dte_target=35, max_expirations=1, now_date="2026-06-01")
    assert len(chains) == 1
    contract = chains[0].calls[0]
    assert isinstance(contract.strike, Decimal)
    assert isinstance(contract.bid, Decimal)
    assert isinstance(contract.ask, Decimal)
    assert isinstance(contract.last_price, Decimal)
    assert isinstance(contract.implied_volatility, Decimal)
    # symbol should be the contractSymbol from the frame
    assert contract.symbol.startswith("X")


def test_no_options_returns_empty(monkeypatch):
    """Tickers with no listed options (e.g. micro-caps) return []."""
    monkeypatch.setattr(yfinance, "Ticker", lambda s: _NoOptTicker())

    result = yfo.get_options_chain("MNTS", now_date="2026-06-01")
    assert result == []
