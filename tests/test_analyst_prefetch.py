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
