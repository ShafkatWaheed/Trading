"""Unit tests for the Quiver congress ingest (src.data.quiver_congress).

All DB writes hit the session temp DB (see tests/conftest.py). Synthetic
filers/tickers only — never production symbols.
"""
from src.data import quiver_congress as Q


def test_norm_txn():
    assert Q._norm_txn("Purchase") == "buy"
    assert Q._norm_txn("Sale (Partial)") == "sell"
    assert Q._norm_txn("Sale (Full)") == "sell"
    assert Q._norm_txn("Exchange") == "exchange"
    assert Q._norm_txn("") == "unknown"
    assert Q._norm_txn("Receive") == "unknown"


def test_norm_chamber():
    assert Q._norm_chamber("Senate") == "Senate"
    assert Q._norm_chamber("senate") == "Senate"
    assert Q._norm_chamber("Representatives") == "House"
    assert Q._norm_chamber("") == "House"


def test_norm_party():
    assert Q._norm_party("D") == "Democrat"
    assert Q._norm_party("R") == "Republican"
    assert Q._norm_party("I") == "Independent"
    assert Q._norm_party("") == "Unknown"
    assert Q._norm_party("X") == "Unknown"


def test_parse_amount_range():
    assert Q._parse_amount_range("$100,001 - $250,000") == (100001, 250000)
    assert Q._parse_amount_range("$1,001 – $15,000") == (1001, 15000)  # en-dash
    assert Q._parse_amount_range("") == (0, 0)


def test_filing_uuid_stable_and_chamber_scoped():
    a = Q._filing_uuid("Senate", "W000802", "2026-06-02", "Sheldon Whitehouse")
    b = Q._filing_uuid("Senate", "W000802", "2026-06-02", "Sheldon Whitehouse")
    c = Q._filing_uuid("House", "W000802", "2026-06-02", "Sheldon Whitehouse")
    assert a == b           # deterministic
    assert a != c           # chamber-scoped


def _rec(**kw):
    base = {
        "Representative": "Test Senator", "BioGuideID": "T000001",
        "ReportDate": "2026-06-02", "TransactionDate": "2026-05-08",
        "Ticker": "SYN1", "Transaction": "Purchase",
        "Range": "$1,001 - $15,000", "House": "Senate",
        "Party": "D", "TickerType": "Stock", "Description": None,
    }
    base.update(kw)
    return base


def test_normalize_drops_bad_tickers_and_keeps_both_chambers():
    records = [
        _rec(Ticker="SYN1", House="Senate"),
        _rec(Ticker="SYN2", House="Representatives", Representative="Test Rep"),
        _rec(Ticker="--"),    # bad ticker -> dropped
        _rec(Ticker=""),      # empty -> dropped
    ]
    grouped = Q.normalize(records)
    all_trades = [t for v in grouped.values() for t in v]
    assert {t["ticker"] for t in all_trades} == {"SYN1", "SYN2"}
    assert {t["chamber"] for t in all_trades} == {"Senate", "House"}


def test_refresh_writes_both_chambers_and_is_idempotent():
    records = [
        _rec(Ticker="SYN1", House="Senate", Representative="Test Senator",
             Party="D", Transaction="Purchase", Range="$1,001 - $15,000"),
        _rec(Ticker="SYN1", House="Representatives", Representative="Test Rep",
             Party="R", Transaction="Sale (Full)", Range="$15,001 - $50,000"),
    ]
    counts = Q.refresh(fetch_fn=lambda: records)
    assert counts["trades"] == 2
    assert counts["house"] == 1 and counts["senate"] == 1
    assert counts["politicians"] == 2

    rows = Q.get_trades_by_symbol("SYN1", days=3650)
    assert len(rows) == 2
    by_chamber = {r["chamber"]: r for r in rows}
    assert by_chamber["Senate"]["party"] == "Democrat"
    assert by_chamber["Senate"]["transaction_type"] == "buy"
    assert by_chamber["House"]["party"] == "Republican"
    assert by_chamber["House"]["transaction_type"] == "sell"

    # Re-running must not duplicate (idempotent rewrite per filing)
    Q.refresh(fetch_fn=lambda: records)
    assert len(Q.get_trades_by_symbol("SYN1", days=3650)) == 2


def test_get_top_traded_stocks():
    records = [
        _rec(Ticker="SYN1", House="Senate", Representative="A"),
        _rec(Ticker="SYN1", House="Representatives", Representative="B"),
        _rec(Ticker="SYN2", House="Senate", Representative="C"),
    ]
    Q.refresh(fetch_fn=lambda: records)
    top = {r["symbol"]: r["trade_count"] for r in Q.get_top_traded_stocks(days=3650)}
    assert top["SYN1"] == 2
    assert top["SYN2"] == 1


def test_refresh_empty_feed_is_safe():
    counts = Q.refresh(fetch_fn=lambda: [])
    assert counts["trades"] == 0 and counts["filings"] == 0
