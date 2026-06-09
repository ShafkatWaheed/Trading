"""Flow agent selects opportunities with congressional buying or 13F breadth."""
from __future__ import annotations

import api.services.daily_picks_agents as dpa
from src.utils.db import get_connection, init_db


def _card(sym, score=70):
    return {"symbol": sym, "strategy": "Neutral", "score": score,
            "secondary_strategies": [], "sub_scores": {}, "sector": "Tech", "price": 100}


def _seed(monkeypatch):
    init_db()
    c = get_connection()
    c.execute("DELETE FROM congress_trades WHERE source='test'")
    c.execute("DELETE FROM institution_holdings WHERE source='test'")
    for i in range(2):
        c.execute(
            "INSERT INTO congress_trades (filing_uuid, txn_index, chamber, politician_name, "
            "party, ticker, transaction_type, transaction_date, fetched_at, source) "
            "VALUES (?,?,?,?,?,?,?,date('now','-10 day'),datetime('now'),'test')",
            (f"t{i}", i, "House", "Rep X", "R", "SYN_A", "buy"),
        )
    for k in range(5):
        c.execute(
            "INSERT INTO institution_holdings (cik, symbol, value_usd, shares, as_of, source) "
            "VALUES (?,?,?,?,date('now'),'test')",
            (f"CIK{k}", "SYN_B", 1000.0, 10),
        )
    c.commit(); c.close()


def test_flow_selects_congress_and_institutional(monkeypatch):
    _seed(monkeypatch)
    opps = [_card("SYN_A", 88), _card("SYN_B", 80), _card("SYN_C", 75)]
    picks = dpa.discover_for_agent("flow", opportunities=opps, gateway=None)
    syms = {p["symbol"] for p in picks}
    assert "SYN_A" in syms and "SYN_B" in syms
    assert "SYN_C" not in syms
    assert all("evidence" in p and "conviction" in p for p in picks)


def test_flow_empty_when_no_signal(monkeypatch):
    init_db()
    c = get_connection()
    c.execute("DELETE FROM congress_trades"); c.execute("DELETE FROM institution_holdings")
    c.commit(); c.close()
    picks = dpa.discover_for_agent("flow", opportunities=[_card("SYN_C")], gateway=None)
    assert picks == []
