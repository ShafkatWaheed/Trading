"""enrich_symbols builds {symbol: option_plan} from an injected gateway.

Temp-DB fixture (conftest) isolates the cache. No network."""
from __future__ import annotations

import pandas as pd

from api.services import option_picks_service
from src.models.data_types import OptionContract, OptionsChain
from src.utils.db import get_connection, init_db


def _df_uptrend():
    # 60 rows trending up; close ~100 at the end. Gives ATR + S/R.
    rows = []
    for i in range(60):
        base = 80 + i * 0.35
        rows.append({"date": f"2026-0{1+i//28}-{1+i%28:02d}",
                     "open": base, "high": base + 1.5, "low": base - 1.5,
                     "close": base, "volume": 1_000_000})
    return pd.DataFrame(rows)


def _chains():
    c = OptionContract(symbol="C100", underlying="SYN_AAA", contract_type="call",
                       strike=__import__("decimal").Decimal("100"),
                       expiration="2026-07-10",
                       bid=__import__("decimal").Decimal("3"),
                       ask=__import__("decimal").Decimal("3.4"),
                       last_price=__import__("decimal").Decimal("3.2"),
                       volume=10, open_interest=100,
                       implied_volatility=__import__("decimal").Decimal("0.3"),
                       delta=__import__("decimal").Decimal("0.5"))
    return [OptionsChain(underlying="SYN_AAA",
                         underlying_price=__import__("decimal").Decimal("100"),
                         expiration="2026-07-10", calls=[c], puts=[])]


class _FakeGateway:
    def __init__(self, *, chains=None, chain_boom=False):
        self._chains = chains if chains is not None else []
        self._chain_boom = chain_boom

    def get_historical(self, symbol, period_days=180):
        return _df_uptrend()

    def get_options_chain(self, symbol):
        if self._chain_boom:
            raise RuntimeError("rate limited")
        return self._chains


def test_enrich_builds_levels_and_contract():
    gw = _FakeGateway(chains=_chains())
    out = option_picks_service.enrich_symbols(["SYN_AAA"], gateway=gw)
    plan = out["SYN_AAA"]
    assert plan["direction"] == "bullish"
    assert plan["entry"] is not None
    assert plan["stop_loss"] is not None       # serialized as string
    assert plan["contract_status"] == "ok"
    assert plan["contract"]["type"] == "call"
    assert plan["contract"]["strike"] == "100"


def test_enrich_levels_present_when_contract_unavailable():
    gw = _FakeGateway(chains=[])               # no chain -> no contract
    out = option_picks_service.enrich_symbols(["SYN_BBB"], gateway=gw)
    plan = out["SYN_BBB"]
    assert plan["entry"] is not None           # levels still computed
    assert plan["contract"] is None
    assert plan["contract_status"] == "unavailable"


def test_enrich_contract_error_is_best_effort():
    gw = _FakeGateway(chain_boom=True)
    out = option_picks_service.enrich_symbols(["SYN_CCC"], gateway=gw)
    plan = out["SYN_CCC"]
    assert plan["contract"] is None
    assert plan["contract_status"] == "unavailable"
    assert plan["stop_loss"] is not None


def test_enrich_is_cached(monkeypatch):
    calls = {"n": 0}

    class CountingGateway(_FakeGateway):
        def get_historical(self, symbol, period_days=180):
            calls["n"] += 1
            return _df_uptrend()

    gw = CountingGateway(chains=_chains())
    option_picks_service.enrich_symbols(["SYN_DDD"], gateway=gw)
    first = calls["n"]
    option_picks_service.enrich_symbols(["SYN_DDD"], gateway=gw)
    assert calls["n"] == first                 # second call served from cache
