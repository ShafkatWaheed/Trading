"""_tier_ab_symbols pulls Tier A+B from stocks_universe, falls back when empty."""
from __future__ import annotations

from src import scheduler
from src.utils.db import get_connection, init_db


def _seed_universe(rows):
    init_db()
    c = get_connection()
    c.execute("DELETE FROM stocks_universe WHERE source='test'")
    for sym, tier in rows:
        c.execute(
            "INSERT OR REPLACE INTO stocks_universe (symbol, tier, source) VALUES (?, ?, 'test')",
            (sym, tier),
        )
    c.commit(); c.close()


def test_tier_ab_returns_only_a_and_b():
    _seed_universe([("SYN_A1", "A"), ("SYN_B1", "B"), ("SYN_C1", "C"), ("SYN_D1", "D")])
    out = scheduler._tier_ab_symbols()
    assert "SYN_A1" in out and "SYN_B1" in out
    assert "SYN_C1" not in out and "SYN_D1" not in out


def test_tier_ab_falls_back_when_universe_empty():
    init_db()
    c = get_connection(); c.execute("DELETE FROM stocks_universe"); c.commit(); c.close()
    out = scheduler._tier_ab_symbols()
    assert out == scheduler._all_target_symbols()
    assert len(out) > 0


def test_tier_ab_falls_back_on_query_error(monkeypatch):
    # If the stocks_universe query raises, _tier_ab_symbols falls back gracefully.
    def boom():
        raise RuntimeError("db unavailable")
    monkeypatch.setattr(scheduler, "get_connection", boom)
    out = scheduler._tier_ab_symbols()
    assert out == scheduler._all_target_symbols()
