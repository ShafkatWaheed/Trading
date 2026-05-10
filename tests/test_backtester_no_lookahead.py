"""Integration test: the backtester's yfinance call sites are now guarded by
the point-in-time context. With a mocked yfinance, we drive a future-dated
earnings table through `_get_earnings_event_dates` and verify that:

  * with no point_in_time block -> behaviour is unchanged (all dates returned)
  * mode="filter" -> future earnings are silently dropped
  * mode="strict" -> LookaheadError is raised

This closes the loop on the runtime guard for the backtester path. It does NOT
exercise the orchestrator/provider path — that lives behind MarketDataService
and will need install_guards() wired separately.
"""

from __future__ import annotations

import sys
import types

import pandas as pd
import pytest

from src.analysis import backtester
from src.utils.point_in_time import LookaheadError, point_in_time


class _FakeTicker:
    """Minimum yfinance.Ticker stand-in: only earnings_dates is read."""

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol

    @property
    def earnings_dates(self) -> pd.DataFrame:
        # Date as the index, mirroring real yfinance output.
        df = pd.DataFrame(
            {
                "EPS Estimate": [1.0, 1.2, 1.4, 1.6],
                "Reported EPS": [1.1, 1.1, 1.5, 1.5],  # beat, miss, beat, miss
            },
            index=pd.to_datetime(
                ["2024-01-31", "2024-04-30", "2024-07-31", "2024-10-31"],
                utc=False,
            ),
        )
        df.index.name = "Earnings Date"
        return df


@pytest.fixture
def fake_yfinance(monkeypatch):
    """Inject a fake `yfinance` module so the backtester's local import resolves to us."""
    fake = types.ModuleType("yfinance")
    fake.Ticker = _FakeTicker  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "yfinance", fake)
    yield fake


def test_no_guard_returns_all_beats(fake_yfinance):
    dates = backtester._get_earnings_event_dates("FAKE", "earnings_beat")
    assert dates == ["2024-01-31", "2024-07-31"]


def test_filter_mode_drops_earnings_after_as_of(fake_yfinance):
    # as_of in mid-2024: only Jan and April should be visible; July/October are future.
    with point_in_time("2024-06-30", mode="filter"):
        dates = backtester._get_earnings_event_dates("FAKE", "earnings_beat")
    assert dates == ["2024-01-31"]


def test_filter_mode_drops_earnings_misses_too(fake_yfinance):
    with point_in_time("2024-06-30", mode="filter"):
        dates = backtester._get_earnings_event_dates("FAKE", "earnings_miss")
    assert dates == ["2024-04-30"]


def test_strict_mode_raises_when_yfinance_returns_future_earnings(fake_yfinance):
    with point_in_time("2024-06-30", mode="strict"):
        with pytest.raises(LookaheadError) as exc:
            backtester._get_earnings_event_dates("FAKE", "earnings_beat")
    msg = str(exc.value)
    assert "yfinance:earnings_dates" in msg
    assert "2024-06-30" in msg


def test_strict_mode_passes_when_as_of_after_all_earnings(fake_yfinance):
    # Far-future as_of: nothing is "future" relative to it, no error.
    with point_in_time("2025-12-31", mode="strict"):
        dates = backtester._get_earnings_event_dates("FAKE", "earnings_beat")
    assert dates == ["2024-01-31", "2024-07-31"]
