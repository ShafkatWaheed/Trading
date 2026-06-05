"""Tests for Senate eFD PTR ingest pipeline.

Network access is dependency-injected (httpx never called). The DataTables
search JSON and the electronic-PTR HTML are fed as canned fixtures.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.data import senate_efd
from src.utils.db import get_connection, init_db


def test_init_db_creates_senate_tables():
    init_db()
    conn = get_connection()
    names = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name IN ('senate_efd_trades', 'senate_efd_index')"
        )
    }
    conn.close()
    assert names == {"senate_efd_trades", "senate_efd_index"}


def test_norm_txn_maps_senate_labels():
    assert senate_efd._norm_txn("Purchase") == "buy"
    assert senate_efd._norm_txn("Sale (Full)") == "sell"
    assert senate_efd._norm_txn("Sale (Partial)") == "sell"
    assert senate_efd._norm_txn("Exchange") == "exchange"
    assert senate_efd._norm_txn("weird") == "unknown"


def test_norm_date_and_amounts():
    assert senate_efd._norm_date("03/16/2026") == "2026-03-16"
    assert senate_efd._norm_date("garbage") == "garbage"
    assert senate_efd._parse_amount_range("$1,001 - $15,000") == (1001, 15000)
    assert senate_efd._parse_amount_range("no dollars here") == (0, 0)


def test_parse_amount_range_handles_endash():
    assert senate_efd._parse_amount_range("$1,001 – $15,000") == (1001, 15000)
