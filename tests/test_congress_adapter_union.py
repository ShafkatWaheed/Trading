"""CongressDataProvider reads House + Senate from the unified congress_trades
table and tags chamber + party correctly (incl. through the cache round-trip)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.data.congress import CongressDataProvider
from src.utils.db import get_connection, init_db


def _insert(conn, **kw):
    today = datetime.now(tz=timezone.utc).date().isoformat()
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    row = {
        "filing_uuid": "F1", "txn_index": 0, "chamber": "House",
        "politician_name": "Nancy Pelosi", "party": "Democrat", "state": "",
        "bioguide_id": "P000197", "ticker": "SYN1", "asset_type": "Stock",
        "transaction_type": "buy", "transaction_date": today, "filing_date": today,
        "amount_low": 1001, "amount_high": 15000, "raw_text": "raw",
        "source": "test", "fetched_at": now_iso,
    }
    row.update(kw)
    conn.execute(
        """INSERT INTO congress_trades
           (filing_uuid, txn_index, chamber, politician_name, party, state,
            bioguide_id, ticker, asset_type, transaction_type, transaction_date,
            filing_date, amount_low, amount_high, raw_text, source, fetched_at)
           VALUES (:filing_uuid,:txn_index,:chamber,:politician_name,:party,:state,
            :bioguide_id,:ticker,:asset_type,:transaction_type,:transaction_date,
            :filing_date,:amount_low,:amount_high,:raw_text,:source,:fetched_at)""",
        row,
    )


@pytest.fixture
def seeded_both():
    init_db()
    conn = get_connection()
    conn.execute("DELETE FROM congress_trades")
    _insert(conn, filing_uuid="H1", chamber="House", politician_name="Nancy Pelosi",
            party="Democrat", ticker="SYN1", transaction_type="buy")
    _insert(conn, filing_uuid="S1", chamber="Senate", politician_name="Mark Warner",
            party="Democrat", state="VA", ticker="SYN1", transaction_type="sell",
            amount_low=15001, amount_high=50000)
    conn.execute("DELETE FROM cache WHERE key LIKE 'congress:%'")
    conn.commit()
    conn.close()
    yield
    conn = get_connection()
    conn.execute("DELETE FROM congress_trades")
    conn.execute("DELETE FROM cache WHERE key LIKE 'congress:%'")
    conn.commit()
    conn.close()


def test_symbol_unions_house_and_senate(seeded_both):
    trades = CongressDataProvider().get_trades_by_symbol("SYN1", days=90)
    assert {t.chamber for t in trades} == {"House", "Senate"}
    assert len(trades) == 2
    assert all(t.party == "Democrat" for t in trades)
    senate = next(t for t in trades if t.chamber == "Senate")
    assert senate.state == "VA"
    assert senate.transaction_type == "sell"

    # Second call hits the congress cache; chamber + party + state must survive
    # the _trade_to_dict / _dict_to_trade round-trip.
    cached = CongressDataProvider().get_trades_by_symbol("SYN1", days=90)
    assert {t.chamber for t in cached} == {"House", "Senate"}
    cached_senate = next(t for t in cached if t.chamber == "Senate")
    assert cached_senate.state == "VA"
    assert cached_senate.party == "Democrat"


def test_top_traded_merges_counts(seeded_both):
    top = CongressDataProvider().get_top_traded_stocks(days=90)
    by_sym = {r["symbol"]: r["trade_count"] for r in top}
    assert by_sym["SYN1"] == 2  # 1 House + 1 Senate
