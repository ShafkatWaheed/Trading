"""End-to-end smoke test of Wave 2 (Catalysts).

Walks every Wave 2 public surface:
  - Phase A: SAM.gov + PatentsView seeders, 8-K Item 5.02 parser
  - Phase B: entity_match_decisions table + resolve_ticker_with_audit
  - Phase C-G: 6 services (Innovation, FDA, Backlog, Litigation, Exec Changes, Entity Match Debug)
  - Phase I: 4 alert types
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.utils.db import get_connection, init_db


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def test_wave2_smoke_phase_a_seeders():
    from src.data.entity_aliases import (
        seed_from_sam_mapping,
        seed_from_patentsview_assignees,
    )
    init_db()
    conn = get_connection()
    conn.execute("DELETE FROM entity_aliases WHERE alias_source = 'smoke_w2'")
    conn.commit()
    conn.close()

    n_sam = seed_from_sam_mapping(
        {"LMT": ("PR7YEP4DZW43", "LOCKHEED MARTIN CORPORATION")},
        alias_source="smoke_w2",
    )
    n_uspto = seed_from_patentsview_assignees(
        {"AAPL": ["Apple Inc.", "Apple Computer, Inc."]},
        alias_source="smoke_w2",
    )
    assert n_sam == 1
    assert n_uspto == 2


def test_wave2_smoke_phase_a_8k_parser():
    from src.utils.sec_8k_parser import parse_8k_item_502
    txt = """Item 5.02 Departure of Directors or Certain Officers

On April 1, 2026, Jane Smith notified the Board of Directors of XYZ Corp that she will resign
from her position as Chief Financial Officer. Ms. Smith's resignation is effective immediately."""
    changes = parse_8k_item_502(txt)
    assert any(c.event_type == "departure" for c in changes)


def test_wave2_smoke_phase_b_audit():
    from src.data.entity_aliases import (
        insert_alias,
        resolve_ticker_with_audit,
    )
    init_db()
    conn = get_connection()
    conn.execute("DELETE FROM entity_aliases WHERE alias_source = 'smoke_w2'")
    conn.execute("DELETE FROM entity_match_decisions WHERE source = 'smoke_w2'")
    conn.commit()
    conn.close()

    insert_alias(
        ticker="AAPL", cik=None, uei=None,
        alias_type="legal", alias_name="apple",
        alias_source="smoke_w2", confidence=1.0, created_at=_now(),
    )
    out = resolve_ticker_with_audit("Apple Inc.", source="smoke_w2", use_fuzzy=False)
    assert out.ticker == "AAPL"
    assert out.method == "exact_alias"

    # Verify the decision was logged
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM entity_match_decisions WHERE source = 'smoke_w2' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert row is not None
    assert row["ticker"] == "AAPL"


def test_wave2_smoke_phase_c_through_g_services(monkeypatch):
    """All six card services should be callable and return well-formed payloads."""
    from api.services.innovation_service import get_innovation_for_ticker
    from api.services.fda_catalysts_service import get_fda_catalysts_for_ticker
    from api.services.backlog_service import get_backlog_for_ticker
    from api.services.litigation_service import get_litigation_for_ticker
    from api.services.exec_changes_service import get_exec_changes_for_ticker
    from api.services.entity_matches_service import get_matches_for_ticker

    # For unknown ticker: all services should return non-empty dicts with the
    # right shape (empty facts, but valid envelope).
    for fn in (
        get_innovation_for_ticker,
        get_fda_catalysts_for_ticker,
        get_backlog_for_ticker,
        get_litigation_for_ticker,
        get_exec_changes_for_ticker,
    ):
        out = fn("ZZZ_NONEXISTENT")
        assert out["ticker"] == "ZZZ_NONEXISTENT"
        assert "headline" in out
        assert isinstance(out.get("facts", None), list)

    # Entity Match Debug has a slightly different shape
    out = get_matches_for_ticker("ZZZ_NONEXISTENT")
    assert out["ticker"] == "ZZZ_NONEXISTENT"
    assert out["matches"] == []


def test_wave2_smoke_phase_i_alert_types():
    from api.services.alerts_service import (
        create_contract_award_alert,
        create_exec_departure_alert,
        create_fda_decision_alert,
        create_itc_filing_alert,
    )
    init_db()
    # Use distinctive symbols so cleanup is scoped
    conn = get_connection()
    conn.execute("DELETE FROM alerts WHERE symbol LIKE 'SMOKE_W2%'")
    conn.commit()
    conn.close()

    create_fda_decision_alert(
        ticker="SMOKE_W2_FDA",
        application_number="BLA-X",
        submission_status="Approved",
        action_date="2026-05-15",
    )
    create_itc_filing_alert(
        ticker="SMOKE_W2_ITC",
        investigation_number="337-TA-9999",
        party_role="respondent",
        title="Test",
    )
    create_exec_departure_alert(
        ticker="SMOKE_W2_EXEC",
        person_name="Test Person",
        role="Chief Financial Officer",
        filing_date="2026-05-15",
    )
    create_contract_award_alert(
        ticker="SMOKE_W2_CON",
        award_id="X-1",
        award_amount=2_000_000_000,
        awarding_agency="DoD",
        action_date="2026-05-15",
    )

    conn = get_connection()
    rows = conn.execute(
        "SELECT alert_type, COUNT(*) AS c FROM alerts WHERE symbol LIKE 'SMOKE_W2%' GROUP BY alert_type"
    ).fetchall()
    conn.close()
    types = {r["alert_type"]: r["c"] for r in rows}
    assert types.get("fda_decision") == 1
    assert types.get("itc_337_filing") == 1
    assert types.get("exec_departure") == 1
    assert types.get("contract_award") == 1

    # Cleanup
    conn = get_connection()
    conn.execute("DELETE FROM alerts WHERE symbol LIKE 'SMOKE_W2%'")
    conn.commit()
    conn.close()


def test_wave2_smoke_six_endpoints_registered():
    """All 6 Wave 2 endpoints must be registered on the FastAPI app."""
    from api.main import app
    paths = {route.path for route in app.routes}
    assert "/stocks/{ticker}/innovation" in paths
    assert "/stocks/{ticker}/fda-catalysts" in paths
    assert "/stocks/{ticker}/backlog" in paths
    assert "/stocks/{ticker}/litigation" in paths
    assert "/stocks/{ticker}/exec-changes" in paths
    assert "/stocks/{ticker}/entity-matches" in paths
