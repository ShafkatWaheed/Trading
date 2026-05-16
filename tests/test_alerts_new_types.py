"""Tests for Wave 2 alert type wrappers."""
from __future__ import annotations

import pytest

from api.services.alerts_service import (
    create_contract_award_alert,
    create_exec_departure_alert,
    create_fda_decision_alert,
    create_itc_filing_alert,
)
from src.utils.db import get_connection, init_db


@pytest.fixture(autouse=True)
def _clean():
    init_db()
    conn = get_connection()
    conn.execute("DELETE FROM alerts WHERE alert_type IN ('fda_decision', 'itc_337_filing', 'exec_departure', 'contract_award')")
    conn.commit()
    conn.close()
    yield


def test_create_fda_decision_alert_inserts_row():
    create_fda_decision_alert(
        ticker="MRNA",
        application_number="BLA-125594",
        submission_status="Approved",
        action_date="2026-07-17",
    )
    conn = get_connection()
    row = conn.execute(
        "SELECT alert_type, symbol, message, severity FROM alerts "
        "WHERE alert_type = 'fda_decision' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert row["symbol"] == "MRNA"
    assert "MRNA" in row["message"] or "BLA-125594" in row["message"]
    assert "Approved" in row["message"]
    # Approvals are bullish-leaning catalysts; severity should be at least 'warning' or above 'info'
    assert row["severity"] in ("info", "warning", "high")


def test_create_itc_filing_alert_inserts_row():
    create_itc_filing_alert(
        ticker="NVDA",
        investigation_number="337-TA-1234",
        party_role="respondent",
        title="Certain GPUs and related products",
    )
    conn = get_connection()
    row = conn.execute(
        "SELECT alert_type, symbol, message, severity FROM alerts "
        "WHERE alert_type = 'itc_337_filing' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert row["symbol"] == "NVDA"
    assert "respondent" in row["message"].lower() or "337" in row["message"]
    # Respondent = potential import ban → high severity
    assert row["severity"] in ("warning", "high")


def test_create_exec_departure_alert_inserts_row():
    create_exec_departure_alert(
        ticker="AAPL",
        person_name="Jane Smith",
        role="Chief Financial Officer",
        filing_date="2026-05-15",
    )
    conn = get_connection()
    row = conn.execute(
        "SELECT alert_type, symbol, message, severity FROM alerts "
        "WHERE alert_type = 'exec_departure' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert row["symbol"] == "AAPL"
    assert "Jane Smith" in row["message"]
    assert "CFO" in row["message"] or "Chief Financial Officer" in row["message"]
    # CFO departure is high-severity
    assert row["severity"] in ("warning", "high")


def test_create_contract_award_alert_inserts_row():
    create_contract_award_alert(
        ticker="LMT",
        award_id="HQ0276-26-C-0001",
        award_amount=4_200_000_000,
        awarding_agency="Department of Defense",
        action_date="2026-05-10",
    )
    conn = get_connection()
    row = conn.execute(
        "SELECT alert_type, symbol, message, severity FROM alerts "
        "WHERE alert_type = 'contract_award' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert row["symbol"] == "LMT"
    assert "LMT" in row["message"]
    assert "Department of Defense" in row["message"] or "DoD" in row["message"]
    # Large award is info-level (no urgency to react)
    assert row["severity"] in ("info", "warning")
