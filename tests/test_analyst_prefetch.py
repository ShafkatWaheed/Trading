import pandas as pd
from api.services import analyst_pit_service as pit
from api.services import predictions_service as ps


def _frame(rows):
    return pd.DataFrame(rows)  # cols: date, open, close


def test_assemble_compact_uses_injected_history_no_network():
    hist = {"SYN_H": _frame([
        {"date": "2026-01-05", "open": 10.0, "close": 10.0},
        {"date": "2026-01-06", "open": 10.0, "close": 11.0},
        {"date": "2026-01-07", "open": 11.0, "close": 12.0},
        {"date": "2026-01-08", "open": 12.0, "close": 13.0},
        {"date": "2026-01-09", "open": 13.0, "close": 14.0},
        {"date": "2026-01-12", "open": 14.0, "close": 16.0},
        {"date": "2026-02-01", "open": 99.0, "close": 99.0},  # AFTER as_of — must be excluded
    ])}
    rows = pit.assemble_compact(["SYN_H"], "2026-01-12", history=hist)
    assert len(rows) == 1
    # momentum computed from the sliced (<= as_of) closes; the 2026-02-01 bar excluded
    assert rows[0]["symbol"] == "SYN_H"
    assert rows[0]["momentum_pct"] is not None


def test_score_universe_changes_uses_history_open_close():
    hist = {"SYN_H": _frame([
        {"date": "2026-01-12", "open": 10.0, "close": 11.0},   # +10%
    ])}
    changes = ps._score_universe_changes(["SYN_H"], "2026-01-12", history=hist)
    assert round(changes["SYN_H"], 2) == 10.0


def test_score_universe_changes_omits_missing_history_symbol():
    changes = ps._score_universe_changes(["SYN_MISSING"], "2026-01-12", history={})
    assert "SYN_MISSING" not in changes


def test_prefetch_retries_empty_batch_then_succeeds(monkeypatch):
    import pandas as pd
    from api.services import analyst_pit_service as pit
    calls = {"n": 0}
    def fake_batch(batch, period_days):
        calls["n"] += 1
        if calls["n"] == 1:
            return {}                      # first attempt: throttled/empty
        return {s: pd.DataFrame([{"date": "2026-01-02", "open": 1.0, "high": 1.0,
                                  "low": 1.0, "close": 1.0, "volume": 1}]) for s in batch}
    monkeypatch.setattr(pit, "_download_batch", fake_batch)
    out = pit.prefetch_price_history(["SYN_A", "SYN_B"], batch_size=50,
                                     max_retries=3, sleep_fn=lambda *_a: None)
    assert set(out) == {"SYN_A", "SYN_B"}      # retried and recovered
    assert calls["n"] == 2                       # one retry happened


def test_prefetch_gives_up_after_max_retries(monkeypatch):
    from api.services import analyst_pit_service as pit
    monkeypatch.setattr(pit, "_download_batch", lambda batch, period_days: {})
    out = pit.prefetch_price_history(["SYN_A"], max_retries=2, sleep_fn=lambda *_a: None)
    assert out == {}                              # never raises; just empty


def test_prefetch_batches_by_size(monkeypatch):
    from api.services import analyst_pit_service as pit
    seen = []
    def fake_batch(batch, period_days):
        seen.append(tuple(batch)); return {}
    monkeypatch.setattr(pit, "_download_batch", fake_batch)
    pit.prefetch_price_history([f"S{i}" for i in range(120)], batch_size=50,
                               max_retries=0, sleep_fn=lambda *_a: None)
    assert [len(b) for b in seen] == [50, 50, 20]   # 120 -> 50/50/20
