"""The CongressDataProvider unions House + Senate rows and tags chamber."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.data.congress import CongressDataProvider
from src.utils.db import get_connection, init_db


@pytest.fixture
def seeded_both():
    init_db()
    conn = get_connection()
    conn.execute("DELETE FROM house_clerk_trades")
    conn.execute("DELETE FROM senate_efd_trades")
    today = datetime.now(tz=timezone.utc).date().isoformat()
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO house_clerk_trades
           (doc_id, txn_index, politician_name, state_dst, filing_date, ticker,
            asset_type, transaction_type, transaction_date, notification_date,
            amount_low, amount_high, raw_text, fetched_at)
           VALUES ('H1', 0, 'Nancy Pelosi', 'CA11', ?, 'NVDA', 'ST', 'buy',
                   ?, ?, 1001, 15000, 'raw', ?)""",
        (today, today, today, now_iso),
    )
    conn.execute(
        """INSERT INTO senate_efd_trades
           (filing_uuid, txn_index, politician_name, state, filing_date, ticker,
            asset_type, transaction_type, transaction_date, notification_date,
            amount_low, amount_high, raw_text, fetched_at)
           VALUES ('S1', 0, 'Mark Warner', 'VA', ?, 'NVDA', 'Stock', 'sell',
                   ?, ?, 15001, 50000, 'raw', ?)""",
        (today, today, today, now_iso),
    )
    conn.commit()
    conn.close()
    # Clear the congress cache so the union path actually runs.
    conn = get_connection()
    conn.execute("DELETE FROM cache WHERE key LIKE 'congress:%'")
    conn.commit()
    conn.close()
    yield
    conn = get_connection()
    conn.execute("DELETE FROM house_clerk_trades")
    conn.execute("DELETE FROM senate_efd_trades")
    conn.execute("DELETE FROM cache WHERE key LIKE 'congress:%'")
    conn.commit()
    conn.close()


def test_symbol_unions_house_and_senate(seeded_both):
    trades = CongressDataProvider().get_trades_by_symbol("NVDA", days=90)
    chambers = {t.chamber for t in trades}
    assert chambers == {"House", "Senate"}
    assert len(trades) == 2
    # Party stays Unknown for both pending the roster join.
    assert all(t.party == "Unknown" for t in trades)
    senate = next(t for t in trades if t.chamber == "Senate")
    assert senate.state == "VA"
    assert senate.transaction_type == "sell"


def test_top_traded_merges_counts(seeded_both):
    top = CongressDataProvider().get_top_traded_stocks(days=90)
    by_sym = {r["symbol"]: r["trade_count"] for r in top}
    assert by_sym["NVDA"] == 2  # 1 House + 1 Senate
