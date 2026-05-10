"""Shared pytest fixtures.

The DB-backed universe tests insert synthetic rows tagged with
`source='test'` to verify loader behaviour. Without explicit teardown
those rows would persist in the live `trading.db` between runs and
contaminate any UI / API that queries `stocks_universe`.

The autouse fixture below wipes every `source='test'` row at the end of
every test, regardless of pass/fail. Production-source rows
(`tier_a_seed`, `index_loader`, `yfinance`, `hand_conglomerate`) are
never touched.
"""

from __future__ import annotations

import pytest

from src.utils.db import get_connection, init_db


@pytest.fixture(autouse=True)
def _purge_test_universe_rows():
    """Clean up any rows tagged with source='test' after every test."""
    yield
    try:
        init_db()
        conn = get_connection()
        try:
            conn.execute("DELETE FROM stock_industry WHERE source='test'")
            conn.execute("DELETE FROM stocks_universe WHERE source='test'")
            conn.commit()
        finally:
            conn.close()
    except Exception:
        # Don't let teardown errors mask test failures.
        pass
