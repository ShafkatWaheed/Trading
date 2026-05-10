"""Tests for the auto-installed point-in-time guards in src/data/guards.py.

Importing src.data triggers install_default_guards(), so by the time any of
these tests run the registered provider methods are already wrapped. We verify:

  1. The registry methods are wrapped (functools.wraps preserves __wrapped__).
  2. is_installed() is True after import.
  3. Calling install_default_guards() again is a no-op (idempotent).
  4. End-to-end: a future-dated frame returned by an inner fetcher is filtered
     in mode="filter" and raises LookaheadError in mode="strict".
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest

import src.data  # noqa: F401  -- triggers install_default_guards()
from src.data.guards import (
    _REGISTRY,
    install_default_guards,
    is_installed,
    uninstall_default_guards,
)
from src.data.market import MarketDataService
from src.utils.point_in_time import LookaheadError, point_in_time


def test_guards_installed_on_import():
    assert is_installed() is True


def test_every_registered_method_is_wrapped():
    for cls, method_name, _date_col in _REGISTRY:
        method = getattr(cls, method_name)
        # functools.wraps stamps __wrapped__ on the wrapper, pointing at the original.
        assert hasattr(method, "__wrapped__"), f"{cls.__name__}.{method_name} not wrapped"


def test_install_is_idempotent():
    # Currently installed (auto). Calling again must not double-wrap.
    method_before = MarketDataService.get_historical
    install_default_guards()
    method_after = MarketDataService.get_historical
    assert method_before is method_after


def test_uninstall_then_reinstall_round_trips():
    original = MarketDataService.get_historical.__wrapped__  # the real method
    uninstall_default_guards()
    try:
        assert is_installed() is False
        assert MarketDataService.get_historical is original
    finally:
        install_default_guards()
    assert is_installed() is True
    assert MarketDataService.get_historical is not original


# --- end-to-end through MarketDataService.get_historical ---------------------


def _future_dated_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": ["2024-01-31", "2024-06-30", "2024-12-31"],
            "open": [100.0, 110.0, 120.0],
            "high": [101.0, 111.0, 121.0],
            "low": [99.0, 109.0, 119.0],
            "close": [100.5, 110.5, 120.5],
            "volume": [1_000_000, 1_100_000, 1_200_000],
        }
    )


@pytest.fixture
def market_with_fake_fetch(monkeypatch):
    """MarketDataService whose cache and inner fetch return our future-dated frame."""
    from src.utils import db as db_module

    monkeypatch.setattr(db_module, "cache_get", lambda *a, **kw: None)
    monkeypatch.setattr(
        MarketDataService,
        "_try_sources_df",
        lambda self, *a, **kw: _future_dated_frame(),
    )
    return MarketDataService()


def test_strict_mode_raises_on_market_get_historical_leak(market_with_fake_fetch):
    with point_in_time("2024-06-30", mode="strict"):
        with pytest.raises(LookaheadError) as exc:
            market_with_fake_fetch.get_historical("FAKE", period_days=365)
    assert "MarketDataService.get_historical" in str(exc.value)
    assert "2024-06-30" in str(exc.value)


def test_filter_mode_truncates_market_get_historical(market_with_fake_fetch):
    with point_in_time("2024-06-30", mode="filter"):
        df = market_with_fake_fetch.get_historical("FAKE", period_days=365)
    assert list(df["date"]) == ["2024-01-31", "2024-06-30"]


def test_no_active_block_returns_full_frame(market_with_fake_fetch):
    df = market_with_fake_fetch.get_historical("FAKE", period_days=365)
    assert len(df) == 3
