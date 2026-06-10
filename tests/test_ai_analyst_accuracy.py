from api.services import predictions_service as ps
from src.utils.db import get_connection, init_db


def _seed_ab():
    init_db()
    conn = get_connection()
    try:
        conn.execute("DELETE FROM stocks_universe WHERE source='test'")
        for i, t in enumerate(["A", "A", "B", "B"]):
            conn.execute(
                "INSERT INTO stocks_universe (symbol, tier, source) VALUES (?,?,'test')",
                (f"SYN_U{i}", t),
            )
        conn.commit()
    finally:
        conn.close()


def test_load_universe_ab_returns_a_and_b_only():
    _seed_ab()
    syms = ps._load_universe_ab()
    conn = get_connection()
    try:
        conn.execute("DELETE FROM stocks_universe WHERE source='test'")
        conn.commit()
    finally:
        conn.close()
    assert {"SYN_U0", "SYN_U1", "SYN_U2", "SYN_U3"} <= set(syms)


def test_threshold_pct_converts_to_rank():
    # 200-symbol universe, top 15% => rank threshold 30.
    assert ps._pct_threshold_to_rank(15, 200) == 30
    assert ps._pct_threshold_to_rank(15, 1000) == 150


def test_record_actuals_uses_ab_universe(monkeypatch):
    # the ranking universe must be A+B, not Tier A
    seen = {}
    def _stub_ab():
        seen["ab"] = True
        return ["SYN_U0"]

    monkeypatch.setattr(ps, "_load_universe_ab", _stub_ab)
    # stub the price/open-close fetch so no network is hit; just assert _load_universe_ab was used
    monkeypatch.setattr(ps, "_score_universe_changes", lambda syms, date: {s: 0.0 for s in syms})
    ps.record_actuals_for_date("2026-02-02")
    assert seen.get("ab") is True
