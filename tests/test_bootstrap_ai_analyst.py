from scripts import bootstrap_ai_analyst as boot
from src.utils.db import get_connection, init_db


def test_walk_forward_skips_already_predicted(monkeypatch):
    init_db()
    calls = []
    monkeypatch.setattr(boot, "_trading_days", lambda n: ["2026-02-02", "2026-02-03", "2026-02-04"])
    monkeypatch.setattr(boot, "_prefetch", lambda syms: {})
    monkeypatch.setattr(boot, "predict_for_date",
                        lambda d, mode, history=None: calls.append(d) or {"count": 10})
    monkeypatch.setattr(boot, "record_actuals_for_date", lambda d, history=None: {"recorded": 10})
    monkeypatch.setattr(boot, "_is_week_end", lambda d: False)
    monkeypatch.setattr(boot, "get_accuracy_window", lambda **k: {"hit_rate": 0.0})
    # pre-seed one date as already predicted. The daily_predictions FK points
    # at prediction_strategies(version); bootstrap the baseline via the real
    # service path so a valid version exists on a fresh temp DB.
    from api.services.predictions_service import get_active_strategy
    sv = get_active_strategy()["version"]   # bootstraps 5d_momentum_v1 as version 1
    conn = get_connection()
    try:
        conn.execute("INSERT OR IGNORE INTO daily_predictions "
                     "(prediction_date, rank, symbol, strategy_version, created_at, mode) "
                     "VALUES ('2026-02-03', 1, 'SYN_X', ?, datetime('now'), 'bootstrap')",
                     (sv,))
        conn.commit()
    finally:
        conn.close()
    boot.run(days=3)
    conn = get_connection()
    try:
        conn.execute("DELETE FROM daily_predictions WHERE symbol='SYN_X'")
        # Leave the shared session DB exactly as found: drop the baseline this
        # test bootstrapped and rewind the AUTOINCREMENT counter. Otherwise the
        # leftover sequence value makes the next bootstrap land on version 2,
        # breaking test_predictions_service's "fresh DB -> version 1" assertion.
        conn.execute("DELETE FROM prediction_strategies")
        conn.execute("DELETE FROM sqlite_sequence WHERE name = 'prediction_strategies'")
        conn.commit()
    finally:
        conn.close()
    assert "2026-02-03" not in calls   # skipped (resumable)
    assert "2026-02-02" in calls and "2026-02-04" in calls


def test_week_end_triggers_rewrite(monkeypatch):
    init_db()
    rewrites = []
    monkeypatch.setattr(boot, "_trading_days", lambda n: ["2026-02-06"])  # a Friday
    monkeypatch.setattr(boot, "_prefetch", lambda syms: {})
    monkeypatch.setattr(boot, "predict_for_date", lambda d, mode, history=None: {"count": 10})
    monkeypatch.setattr(boot, "record_actuals_for_date", lambda d, history=None: {"recorded": 10})
    monkeypatch.setattr(boot, "_is_week_end", lambda d: True)
    monkeypatch.setattr(boot, "get_accuracy_window", lambda **k: {"hit_rate": 0.0})
    monkeypatch.setattr(boot, "_rewrite_playbook_window", lambda d: rewrites.append(d))
    boot.run(days=1)
    assert rewrites == ["2026-02-06"]


def test_run_aborts_loudly_on_poor_prefetch_coverage(monkeypatch):
    import pytest
    from scripts import bootstrap_ai_analyst as boot
    monkeypatch.setattr(boot, "_load_universe_ab", lambda: ["A", "B", "C", "D"])
    monkeypatch.setattr(boot, "_prefetch", lambda syms: {"A": object()})  # 1/4 = 25% < 50%
    with pytest.raises(RuntimeError, match="throttling"):
        boot.run(days=3)


def test_final_rewrite_always_runs_even_without_a_walked_friday(monkeypatch):
    # In a short (1-week) cold-start the only Friday is often already-predicted
    # and thus skipped, so the in-loop rewrite never fires. The unconditional
    # final rewrite must still run, windowed over the cold-start `days`.
    init_db()
    called = []
    monkeypatch.setattr(boot, "_trading_days", lambda n: ["2026-02-02"])
    monkeypatch.setattr(boot, "_prefetch", lambda syms: {})
    monkeypatch.setattr(boot, "predict_for_date", lambda d, mode, history=None: {"count": 10})
    monkeypatch.setattr(boot, "record_actuals_for_date", lambda d, history=None: {"recorded": 10})
    monkeypatch.setattr(boot, "_is_week_end", lambda d: False)   # no in-loop rewrite
    monkeypatch.setattr(boot, "get_accuracy_window", lambda **k: {"hit_rate": 0.0})
    monkeypatch.setattr(boot, "_final_playbook_rewrite", lambda wd: called.append(wd))
    boot.run(days=7)
    assert called == [7]   # final rewrite ran once, windowed over the 1-week run
