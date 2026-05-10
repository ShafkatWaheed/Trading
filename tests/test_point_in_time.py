"""Tests for the point-in-time / no-lookahead guard."""

from __future__ import annotations

import pandas as pd
import pytest

from src.utils.point_in_time import (
    LookaheadError,
    current_guard,
    enforce,
    install_guards,
    point_in_time,
)


def _frame(dates: list[str]) -> pd.DataFrame:
    return pd.DataFrame({"date": pd.to_datetime(dates), "close": range(len(dates))})


# --- enforce() ----------------------------------------------------------------


def test_enforce_is_noop_without_active_guard():
    df = _frame(["2024-01-01", "2024-12-31"])
    out = enforce(df, "date")
    assert out is df


def test_enforce_strict_raises_on_future_rows():
    df = _frame(["2024-01-01", "2024-06-30", "2024-07-01"])
    with point_in_time("2024-06-30", mode="strict"):
        with pytest.raises(LookaheadError) as exc:
            enforce(df, "date", source="market.get_historical")
    assert "market.get_historical" in str(exc.value)
    assert "2024-06-30" in str(exc.value)


def test_enforce_filter_silently_truncates():
    df = _frame(["2024-01-01", "2024-06-30", "2024-07-01", "2024-12-31"])
    with point_in_time("2024-06-30", mode="filter"):
        out = enforce(df, "date")
    assert list(out["date"].dt.strftime("%Y-%m-%d")) == ["2024-01-01", "2024-06-30"]


def test_enforce_passes_when_all_rows_on_or_before_as_of():
    df = _frame(["2024-01-01", "2024-06-29", "2024-06-30"])
    with point_in_time("2024-06-30"):
        out = enforce(df, "date")
    assert len(out) == 3


def test_enforce_handles_empty_frame():
    df = pd.DataFrame({"date": pd.to_datetime([])})
    with point_in_time("2024-06-30"):
        out = enforce(df, "date")
    assert len(out) == 0


def test_enforce_raises_keyerror_when_date_column_missing():
    df = pd.DataFrame({"close": [1, 2, 3]})
    with point_in_time("2024-06-30"):
        with pytest.raises(KeyError):
            enforce(df, "date")


# --- context manager ----------------------------------------------------------


def test_current_guard_is_none_outside_block():
    assert current_guard() is None


def test_current_guard_visible_inside_block_and_cleared_after():
    with point_in_time("2024-06-30") as g:
        assert current_guard() is g
        assert g.as_of == pd.Timestamp("2024-06-30")
    assert current_guard() is None


def test_invalid_mode_rejected():
    with pytest.raises(ValueError):
        with point_in_time("2024-06-30", mode="loose"):
            pass


# --- install_guards monkey-patching ------------------------------------------


class _FakeProvider:
    """Stand-in provider used only inside this test module."""

    def get_historical(self, end: str) -> pd.DataFrame:
        # Simulates a source that always returns a year of data ending at `end`,
        # ignoring point-in-time. The guard's job is to catch this.
        return pd.DataFrame(
            {
                "date": pd.date_range(end=end, periods=5, freq="D"),
                "close": [100, 101, 102, 103, 104],
            }
        )


def test_install_guards_filter_mode_truncates_provider_output():
    uninstall = install_guards([(_FakeProvider, "get_historical", "date")])
    try:
        with point_in_time("2024-06-30", mode="filter"):
            df = _FakeProvider().get_historical(end="2024-07-04")
        # Source returned 2024-06-30 .. 2024-07-04. Guard should keep only
        # the row exactly on as_of and drop the four after it.
        assert list(df["date"].dt.strftime("%Y-%m-%d")) == ["2024-06-30"]
    finally:
        uninstall()


def test_install_guards_strict_mode_raises_on_provider_leak():
    uninstall = install_guards([(_FakeProvider, "get_historical", "date")])
    try:
        with point_in_time("2024-06-30", mode="strict"):
            with pytest.raises(LookaheadError) as exc:
                _FakeProvider().get_historical(end="2024-07-04")
        assert "_FakeProvider.get_historical" in str(exc.value)
    finally:
        uninstall()


def test_install_guards_inactive_outside_point_in_time_block():
    uninstall = install_guards([(_FakeProvider, "get_historical", "date")])
    try:
        # No active guard -> wrapper passes through untouched.
        df = _FakeProvider().get_historical(end="2024-07-04")
        assert len(df) == 5
    finally:
        uninstall()


def test_uninstall_restores_original_method():
    original = _FakeProvider.get_historical
    uninstall = install_guards([(_FakeProvider, "get_historical", "date")])
    assert _FakeProvider.get_historical is not original
    uninstall()
    assert _FakeProvider.get_historical is original
