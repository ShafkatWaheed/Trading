"""Shared pytest fixtures.

The production `trading.db` is sacred — graph nodes, industry mappings,
peer edges, supplier/customer relations, and commodity exposure all live
there and were expensively curated. Tests must NEVER read or write that
file.

The session-scoped `_isolated_test_db` fixture below redirects
`src.utils.db.DB_PATH` to a per-session temp file BEFORE any test runs,
so every call to `get_connection()`, `init_db()`, and every seed loader
operates against the temp DB. Production `trading.db` is untouched no
matter what a test does — including unscoped DELETEs.

Past landmines this prevents: tests that ran
`DELETE FROM stocks_universe WHERE source='index_loader'` and similar
broad-scope wipes against the live DB.
"""

from __future__ import annotations

import pytest


@pytest.fixture(scope="session", autouse=True)
def _isolated_test_db(tmp_path_factory):
    """Redirect all DB access to a per-session temp file.

    Runs once before any test; restores DB_PATH after the session ends.
    """
    from src.utils import db

    tmp_db = tmp_path_factory.mktemp("trading_test_db") / "test.db"
    original_path = db.DB_PATH
    db.DB_PATH = tmp_db
    try:
        yield tmp_db
    finally:
        db.DB_PATH = original_path


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """Per-test fresh temp DB.

    Layered on top of `_isolated_test_db` for tests that need a guaranteed-empty
    DB (e.g., asserting exact insert counts). The `monkeypatch.setattr` swap is
    automatically reverted after the test, so the session-scoped temp DB
    resumes for subsequent tests.

    Tests that previously called `_wipe_X_rows()` against production sources
    should use this fixture instead.
    """
    from src.utils import db

    test_db = tmp_path / "test.db"
    monkeypatch.setattr(db, "DB_PATH", test_db)
    yield test_db
