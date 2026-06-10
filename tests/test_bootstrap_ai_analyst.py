from scripts import bootstrap_ai_analyst as boot
from src.utils.db import get_connection, init_db


def test_walk_forward_skips_already_predicted(monkeypatch):
    init_db()
    calls = []
    monkeypatch.setattr(boot, "_trading_days", lambda n: ["2026-02-02", "2026-02-03", "2026-02-04"])
    monkeypatch.setattr(boot, "predict_for_date",
                        lambda d, mode: calls.append(d) or {"count": 10})
    monkeypatch.setattr(boot, "record_actuals_for_date", lambda d: {"recorded": 10})
    monkeypatch.setattr(boot, "_is_week_end", lambda d: False)
    monkeypatch.setattr(boot, "get_accuracy_window", lambda **k: {"hit_rate": 0.0})
    # pre-seed one date as already predicted
    conn = get_connection()
    try:
        conn.execute("INSERT OR IGNORE INTO daily_predictions "
                     "(prediction_date, rank, symbol, strategy_version, created_at, mode) "
                     "VALUES ('2026-02-03', 1, 'SYN_X', 1, datetime('now'), 'bootstrap')")
        conn.commit()
    finally:
        conn.close()
    boot.run(days=3)
    conn = get_connection()
    try:
        conn.execute("DELETE FROM daily_predictions WHERE symbol='SYN_X'")
        conn.commit()
    finally:
        conn.close()
    assert "2026-02-03" not in calls   # skipped (resumable)
    assert "2026-02-02" in calls and "2026-02-04" in calls


def test_week_end_triggers_rewrite(monkeypatch):
    init_db()
    rewrites = []
    monkeypatch.setattr(boot, "_trading_days", lambda n: ["2026-02-06"])  # a Friday
    monkeypatch.setattr(boot, "predict_for_date", lambda d, mode: {"count": 10})
    monkeypatch.setattr(boot, "record_actuals_for_date", lambda d: {"recorded": 10})
    monkeypatch.setattr(boot, "_is_week_end", lambda d: True)
    monkeypatch.setattr(boot, "get_accuracy_window", lambda **k: {"hit_rate": 0.0})
    monkeypatch.setattr(boot, "_rewrite_playbook_window", lambda d: rewrites.append(d))
    boot.run(days=1)
    assert rewrites == ["2026-02-06"]
