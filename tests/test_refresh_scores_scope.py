"""refresh_scores(symbols=...) scores exactly the given symbols (no network)."""
from __future__ import annotations

import pandas as pd

from src import scheduler
from src.utils.db import get_connection, init_db


def _fake_hist():
    rows = []
    for i in range(60):
        base = 80 + i * 0.4
        rows.append({"date": f"2026-0{1+i//28}-{1+i%28:02d}",
                     "open": base, "high": base + 1.5, "low": base - 1.5,
                     "close": base, "volume": 1_000_000})
    return pd.DataFrame(rows)


class _FakeGateway:
    def get_historical(self, symbol, period_days=252):
        return _fake_hist()


def test_refresh_scores_scopes_to_given_symbols(monkeypatch):
    init_db()
    c = get_connection()
    c.execute("DELETE FROM precomputed_scores WHERE symbol LIKE 'SYN_%'")
    c.commit(); c.close()

    import src.data.gateway as gw_mod
    monkeypatch.setattr(gw_mod, "DataGateway", _FakeGateway)
    monkeypatch.setattr(scheduler, "_all_target_symbols",
                        lambda: (_ for _ in ()).throw(AssertionError("default scope used")))

    scheduler.refresh_scores(symbols=["SYN_A", "SYN_B"])

    c = get_connection()
    got = {r["symbol"] for r in c.execute(
        "SELECT symbol FROM precomputed_scores WHERE symbol LIKE 'SYN_%'")}
    c.close()
    assert got == {"SYN_A", "SYN_B"}
