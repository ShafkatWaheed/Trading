"""scores_need_refresh: detects a stale/unscored opportunity universe."""
from __future__ import annotations

from src import scheduler
from src.utils.db import get_connection, init_db, save_precomputed_score


def _clear():
    init_db()
    c = get_connection()
    c.execute("DELETE FROM precomputed_scores WHERE symbol LIKE 'SYN_%'")
    c.commit(); c.close()


def test_stale_when_no_fresh_scores():
    _clear()
    # wipe everything so the fresh count is 0
    init_db(); c = get_connection(); c.execute("DELETE FROM precomputed_scores"); c.commit(); c.close()
    assert scheduler.scores_need_refresh() is True


def test_not_stale_when_enough_fresh_scores():
    _clear()
    init_db(); c = get_connection(); c.execute("DELETE FROM precomputed_scores"); c.commit(); c.close()
    # save_precomputed_score stamps computed_at = now → fresh
    for i in range(100):
        save_precomputed_score(f"SYN_{i:03d}", {"total_score": 50, "strategy": "Momentum"})
    assert scheduler.scores_need_refresh() is False
    # with a higher bar than we seeded, it's stale again
    assert scheduler.scores_need_refresh(min_fresh=101) is True
