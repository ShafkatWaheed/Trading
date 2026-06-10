"""PIT compact assembler: filing-date filters must exclude anything dated > D."""
from api.services import analyst_pit_service as pit
from src.utils.db import get_connection, init_db


def _seed():
    init_db()
    conn = get_connection()
    try:
        conn.execute("DELETE FROM congress_trades WHERE source='test'")
        conn.execute("DELETE FROM institution_holdings WHERE cik LIKE 'TESTCIK%'")
        # congress buy filed 2026-01-10 (before D) and one filed 2026-03-20 (after D)
        for i, (fdate, tdate) in enumerate([("2026-01-10", "2026-01-05"),
                                            ("2026-03-20", "2026-03-15")]):
            conn.execute(
                "INSERT INTO congress_trades (filing_uuid, txn_index, chamber, politician_name, "
                "party, ticker, transaction_type, transaction_date, filing_date, source, fetched_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,'test',datetime('now'))",
                (f"tc{i}", i, "House", "Rep X", "R", "SYN_PIT", "buy", tdate, fdate),
            )
        # 13F as_of before D and after D
        for i, asof in enumerate(["2025-12-31", "2026-03-31"]):
            conn.execute(
                "INSERT INTO institution_holdings (cik, symbol, value_usd, shares, as_of, source) "
                "VALUES (?,?,?,?,?,'hand')",
                (f"TESTCIK{i}", "SYN_PIT", 1000.0, 10.0, asof),
            )
        conn.commit()
    finally:
        conn.close()


def _cleanup():
    conn = get_connection()
    try:
        conn.execute("DELETE FROM congress_trades WHERE source='test'")
        conn.execute("DELETE FROM institution_holdings WHERE cik LIKE 'TESTCIK%'")
        conn.commit()
    finally:
        conn.close()


def test_congress_flag_excludes_filings_after_d():
    _seed()
    # As of 2026-02-01: only the 2026-01-10 filing is known.
    flags = pit.congress_flags_as_of(["SYN_PIT"], "2026-02-01")
    _cleanup()
    assert flags.get("SYN_PIT", 0) == 1   # one disclosed buy known by D


def test_13f_flag_excludes_periods_after_d():
    _seed()
    n = pit.institution_breadth_as_of(["SYN_PIT"], "2026-02-01").get("SYN_PIT", 0)
    _cleanup()
    assert n == 1   # only the 2025-12-31 13F period is known by 2026-02-01
