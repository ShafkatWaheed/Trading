"""Tests for the yfinance industry loader.

Network is mocked via the same `sys.modules['yfinance']` injection pattern
as `tests/test_backtester_no_lookahead.py`. No real Yahoo calls.
"""

from __future__ import annotations

import sys
import types

import pytest

from src.data.industry_loader import apply_yfinance_industries, pull_industry
from src.data.universe_loader import load_tier_a
from src.utils.db import get_connection, init_db


# ── fake yfinance ──────────────────────────────────────────────────


# A handful of fake industry replies; only a slice of stocks need real-shape
# answers for the tests. Anything else returns an "empty" reply.
_FAKE_REPLIES: dict[str, dict] = {
    "NVDA": {
        "industry": "Semiconductors",
        "sector": "Technology",
        "marketCap": 3_500_000_000_000,
        "longBusinessSummary": "NVIDIA Corp provides graphics and compute platforms.",
    },
    "MSFT": {
        "industry": "Software—Infrastructure",
        "sector": "Technology",
        "marketCap": 3_200_000_000_000,
        "longBusinessSummary": "Microsoft Corp develops, licenses, and supports software.",
    },
    "BROKEN": {
        "industry": "",
        "sector": "",
        "marketCap": None,
        "longBusinessSummary": "",
    },
    "NEW_INDUSTRY_STOCK": {
        "industry": "Quantum Computing Services",   # NOT in industries_seed.py
        "sector": "Technology",
        "marketCap": 5_000_000_000,
        "longBusinessSummary": "Builds quantum compute services.",
    },
}


class _FakeTicker:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol

    @property
    def info(self) -> dict:
        return dict(_FAKE_REPLIES.get(self.symbol, {}))


@pytest.fixture
def fake_yfinance(monkeypatch):
    fake = types.ModuleType("yfinance")
    fake.Ticker = _FakeTicker  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "yfinance", fake)
    yield fake


# ── pull_industry single-symbol behaviour ─────────────────────────


def test_pull_industry_returns_normalised_dict(fake_yfinance):
    info = pull_industry("NVDA")
    assert info["symbol"] == "NVDA"
    assert info["industry"] == "Semiconductors"
    assert info["sector"] == "Technology"
    assert info["market_cap"] == 3_500_000_000_000


def test_pull_industry_returns_empty_strings_for_missing_fields(fake_yfinance):
    info = pull_industry("BROKEN")
    assert info["industry"] == ""
    assert info["sector"] == ""
    assert info["market_cap"] is None


def test_pull_industry_handles_missing_yfinance_gracefully(monkeypatch):
    """If yfinance raises, pull_industry returns None instead of propagating."""
    fake = types.ModuleType("yfinance")
    class BoomTicker:
        def __init__(self, sym): pass
        @property
        def info(self):
            raise RuntimeError("network down")
    fake.Ticker = BoomTicker  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "yfinance", fake)

    assert pull_industry("ANY") is None


# ── batch upsert behaviour ─────────────────────────────────────────


def _seed_universe_with(symbols: list[str]) -> None:
    init_db()
    conn = get_connection()
    try:
        # wipe any previous test rows under the symbols, plus our auto-inserted industries
        for sym in symbols:
            conn.execute("DELETE FROM stock_industry WHERE symbol=?", (sym,))
            conn.execute("DELETE FROM stocks_universe WHERE symbol=?", (sym,))
        for sym in symbols:
            conn.execute(
                "INSERT INTO stocks_universe (symbol, tier, source) VALUES (?, 'B', 'test')",
                (sym,),
            )
        conn.commit()
    finally:
        conn.close()


def test_apply_writes_stock_industry_for_each_seeded_symbol(fake_yfinance):
    _seed_universe_with(["NVDA", "MSFT"])
    out = apply_yfinance_industries(symbols=["NVDA", "MSFT"], force=True, sleep_seconds=0, log=False)

    assert out["rows_written"] == 2
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT symbol, industry_code FROM stock_industry "
            "WHERE source='yfinance' AND symbol IN ('NVDA','MSFT')"
        ).fetchall()
        mapping = {r["symbol"]: r["industry_code"] for r in rows}
        assert mapping == {"NVDA": "Semiconductors", "MSFT": "Software—Infrastructure"}
    finally:
        conn.close()


def test_apply_skips_symbols_with_existing_mappings(fake_yfinance):
    """force=False should skip symbols that already have stock_industry rows."""
    _seed_universe_with(["NVDA"])
    apply_yfinance_industries(symbols=["NVDA"], force=True, sleep_seconds=0, log=False)
    second = apply_yfinance_industries(symbols=["NVDA"], force=False, sleep_seconds=0, log=False)
    # `processed` reports the filtered list size, not the input.
    assert second["rows_written"] == 0


def test_apply_creates_new_industry_rows_for_unseen_codes(fake_yfinance):
    _seed_universe_with(["NEW_INDUSTRY_STOCK"])
    apply_yfinance_industries(symbols=["NEW_INDUSTRY_STOCK"], force=True, sleep_seconds=0, log=False)

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT sector FROM industries WHERE code='Quantum Computing Services'"
        ).fetchone()
        assert row is not None
        assert row["sector"] == "Technology"
    finally:
        conn.close()


def test_apply_counts_failures_when_yfinance_returns_none(monkeypatch):
    fake = types.ModuleType("yfinance")
    class BoomTicker:
        def __init__(self, sym): pass
        @property
        def info(self):
            raise RuntimeError("rate limit")
    fake.Ticker = BoomTicker  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "yfinance", fake)

    _seed_universe_with(["WILLFAIL"])
    out = apply_yfinance_industries(symbols=["WILLFAIL"], force=True, sleep_seconds=0, log=False)
    assert out["fetch_failures"] == 1
    assert out["rows_written"] == 0


def test_apply_backfills_market_cap_on_stocks_universe(fake_yfinance):
    _seed_universe_with(["NVDA"])
    apply_yfinance_industries(symbols=["NVDA"], force=True, sleep_seconds=0, log=False)

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT market_cap FROM stocks_universe WHERE symbol='NVDA'"
        ).fetchone()
        assert row["market_cap"] == 3_500_000_000_000
    finally:
        conn.close()


def test_apply_skips_when_industry_field_is_empty(fake_yfinance):
    """A stock returning industry='' must NOT create a phantom industry row."""
    _seed_universe_with(["BROKEN"])
    out = apply_yfinance_industries(symbols=["BROKEN"], force=True, sleep_seconds=0, log=False)
    assert out["rows_written"] == 0
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM stock_industry WHERE symbol='BROKEN'"
        ).fetchall()
        assert rows == []
    finally:
        conn.close()


def test_apply_uses_universe_when_symbols_arg_is_none(fake_yfinance):
    _seed_universe_with(["NVDA", "MSFT"])
    # With force=True and symbols=None, processes every row in stocks_universe
    # that's been seeded by this test (and any hand-seeded Tier A rows).
    out = apply_yfinance_industries(symbols=None, force=True, sleep_seconds=0, log=False)
    assert out["processed"] >= 2
