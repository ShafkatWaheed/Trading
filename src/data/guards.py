"""Default point-in-time guards for the data layer.

`install_default_guards()` monkey-patches every DataFrame-returning provider
method whose date column we know, so that any read inside an active
`point_in_time(...)` block is filtered (or strict-raises) automatically.

Idempotent: subsequent calls are no-ops. Returns the uninstall callable so
tests can isolate themselves.

Design note: this lives in src/data/, not src/utils/, on purpose. Keeping the
provider registry next to the providers (instead of inside point_in_time.py)
respects the dependency rule that utils/ stays generic — point_in_time.py
knows nothing about MarketDataService etc.

Adding a new guarded method:
  1. Confirm the method returns a `pd.DataFrame` with a column whose values
     are real *availability* timestamps (publish/filing date, NOT period end).
  2. Add a (Class, "method", "date_col") entry to _REGISTRY below.
  3. Add a test that drives a future-dated frame through it under
     `point_in_time(..., mode="strict")` and asserts LookaheadError.
"""

from __future__ import annotations

from typing import Callable

from src.data.macro import MacroProvider
from src.data.market import MarketDataService
from src.data.polygon import PolygonProvider
from src.utils.point_in_time import install_guards

# (class, method_name, date_col). Every method here must return a DataFrame
# with `date_col` populated by an availability date — not a period end / fiscal
# date that lags the actual disclosure.
_REGISTRY: list[tuple[type, str, str]] = [
    (MarketDataService, "get_historical", "date"),
    (PolygonProvider, "get_aggregates", "date"),
    (MacroProvider, "get_historical_df", "date"),
]

_installed: bool = False
_uninstall: Callable[[], None] | None = None


def install_default_guards() -> Callable[[], None]:
    """Install guards on every method in `_REGISTRY`. Idempotent."""
    global _installed, _uninstall
    if _installed:
        # Return the existing uninstall so callers can still tear down if they want.
        return _uninstall or (lambda: None)
    _uninstall = install_guards(_REGISTRY)
    _installed = True
    return _uninstall


def uninstall_default_guards() -> None:
    """Restore original methods. Idempotent."""
    global _installed, _uninstall
    if not _installed:
        return
    if _uninstall is not None:
        _uninstall()
    _uninstall = None
    _installed = False


def is_installed() -> bool:
    return _installed
