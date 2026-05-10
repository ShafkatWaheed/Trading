"""Point-in-time guard — runtime enforcement of the no-lookahead rule.

This complements the static audit in scripts/audit_data_integrity.py. The audit
catches *syntactic* leaks (`shift(-1)`, `center=True`, `future_*` names). This
module catches *semantic* leaks: data that the syntax looks innocent for, but
that came back from a provider with rows dated after the decision timestamp.

Typical use inside a backtest loop:

    from src.utils.point_in_time import point_in_time, enforce

    for as_of in trading_days:
        with point_in_time(as_of):
            quotes = market.get_historical("AAPL", period_days=365)
            quotes = enforce(quotes, "date")
            # signal computed below cannot see any row dated > as_of
            ...

To enforce automatically across the data layer, register the read methods that
return DataFrames and the date column they should be cut on:

    from src.data.market import MarketDataService
    from src.utils.point_in_time import install_guards

    install_guards([(MarketDataService, "get_historical", "date")])

Modes:
- "strict" (default) — raises LookaheadError if the underlying source returned
  any row dated after as_of. Use this in tests / CI.
- "filter" — silently truncates to rows on or before as_of. Use this in
  production backtests where you trust the source but want a defensive cut.

Outside a `point_in_time(...)` block this module is a no-op, so wrapping a
provider with `install_guards` is safe to leave on in non-backtest paths.
"""

from __future__ import annotations

import contextvars
import functools
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Callable, Iterable, Iterator

import pandas as pd

__all__ = [
    "LookaheadError",
    "PointInTimeGuard",
    "point_in_time",
    "current_guard",
    "enforce",
    "install_guards",
]


class LookaheadError(BaseException):  # audit: allow lookahead
    """Raised when data dated after the active as-of timestamp is observed.

    Extends BaseException (not Exception) on purpose: the backtester and many
    data-layer helpers wrap their bodies in `except Exception:` for resilience,
    and a lookahead leak is the kind of programming error that must NOT be
    silently swallowed. Catch it explicitly with `except LookaheadError:` if
    you need to handle it; otherwise let it propagate to the test/CI boundary.
    """


@dataclass(frozen=True)
class PointInTimeGuard:
    as_of: pd.Timestamp
    mode: str  # "strict" | "filter"

    def __post_init__(self) -> None:
        if self.mode not in ("strict", "filter"):
            raise ValueError(f"mode must be 'strict' or 'filter', got {self.mode!r}")

    def check(self, df: pd.DataFrame, date_col: str, *, source: str = "") -> pd.DataFrame:
        if df is None or len(df) == 0:
            return df
        if date_col not in df.columns:
            raise KeyError(f"point-in-time guard: column {date_col!r} not in DataFrame from {source or '<unknown>'}")
        col = pd.to_datetime(df[date_col], errors="coerce", utc=False)
        future_mask = col > self.as_of  # audit: allow lookahead
        if not future_mask.any():
            return df
        if self.mode == "strict":
            n = int(future_mask.sum())
            sample = col[future_mask].head(3).tolist()
            raise LookaheadError(
                f"{source or 'data'} returned {n} row(s) dated after as_of={self.as_of.date()}: e.g. {sample}"
            )
        return df.loc[~future_mask].copy()


_active: contextvars.ContextVar[PointInTimeGuard | None] = contextvars.ContextVar(
    "point_in_time_guard", default=None
)


def _coerce_as_of(value: str | date | datetime | pd.Timestamp) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    # Strip tz so comparison with naive provider data doesn't blow up.
    if ts.tzinfo is not None:
        ts = ts.tz_convert(None) if ts.tz is not None else ts.tz_localize(None)
    return ts


@contextmanager
def point_in_time(
    as_of: str | date | datetime | pd.Timestamp,
    mode: str = "strict",
) -> Iterator[PointInTimeGuard]:
    """Activate a point-in-time guard for the duration of the block."""
    guard = PointInTimeGuard(as_of=_coerce_as_of(as_of), mode=mode)
    token = _active.set(guard)
    try:
        yield guard
    finally:
        _active.reset(token)


def current_guard() -> PointInTimeGuard | None:
    """Return the active guard, or None if no `point_in_time(...)` block is open."""
    return _active.get()


def enforce(df: pd.DataFrame, date_col: str, *, source: str = "") -> pd.DataFrame:
    """Apply the active guard to `df`. No-op outside a `point_in_time(...)` block."""
    guard = _active.get()
    if guard is None:
        return df
    return guard.check(df, date_col, source=source)


def install_guards(registry: Iterable[tuple[type, str, str]]) -> Callable[[], None]:
    """Monkey-patch each (class, method, date_col) so the return value is enforced.

    Returns a callable that uninstalls the patches — useful in test teardown.
    Patches stack: calling install_guards twice on the same method nests, and
    the returned uninstall functions undo in LIFO order.
    """
    uninstallers: list[Callable[[], None]] = []
    for cls, method_name, date_col in registry:
        original = getattr(cls, method_name)
        source = f"{cls.__name__}.{method_name}"

        @functools.wraps(original)
        def wrapper(self: Any, *args: Any, _orig: Any = original, _src: str = source, _col: str = date_col, **kwargs: Any) -> Any:
            result = _orig(self, *args, **kwargs)
            guard = _active.get()
            if guard is None or not isinstance(result, pd.DataFrame):
                return result
            return guard.check(result, _col, source=_src)

        setattr(cls, method_name, wrapper)
        uninstallers.append(lambda c=cls, m=method_name, o=original: setattr(c, m, o))

    def uninstall() -> None:
        for fn in reversed(uninstallers):
            fn()

    return uninstall
