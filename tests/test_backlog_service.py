"""Tests for backlog_service (Wave 2, Phase E.3)."""
from __future__ import annotations


def test_backlog_service_for_unknown_ticker_returns_empty(monkeypatch):
    from api.services import backlog_service

    # No name/UEI → both fetchers should return [] → empty card.
    monkeypatch.setattr(
        backlog_service, "fetch_contracts_for_recipient",
        lambda name, **k: [],
    )
    monkeypatch.setattr(
        backlog_service, "fetch_contracts_for_uei",
        lambda uei, **k: [],
    )

    out = backlog_service.get_backlog_for_ticker("ZZZ_NOPE")
    assert out["ticker"] == "ZZZ_NOPE"
    assert out["headline"]                # always present
    assert out["facts"] == []
    assert out["sources_used"] == ["usaspending"]


def test_backlog_service_for_known_ticker_returns_info(monkeypatch):
    from datetime import datetime, timezone

    from api.services import backlog_service
    from src.data.entity_aliases import insert_alias
    from src.utils.db import get_connection, init_db

    init_db()
    insert_alias(
        ticker="LMT", cik=None, uei="ABCD1234EFGH",
        alias_type="sam_business_name", alias_name="lockheed martin",
        alias_source="backlog_test", confidence=1.0,
        created_at=datetime.now(tz=timezone.utc).isoformat(),
    )

    fake_contracts = [
        {
            "award_id": "W56HZV-23-C-0001",
            "recipient_name": "LOCKHEED MARTIN CORPORATION",
            "award_amount": 4_200_000_000,
            "award_type": "BPA Call",
            "action_date": "2026-01-15",
            "awarding_agency": "Department of Defense",
        },
        {
            "award_id": "FA8650-24-C-0042",
            "recipient_name": "LOCKHEED MARTIN CORPORATION",
            "award_amount": 850_000_000,
            "award_type": "Definitive Contract",
            "action_date": "2026-03-02",
            "awarding_agency": "Department of the Air Force",
        },
    ]
    # Service now queries name first, UEI second — patch both. We deliver
    # the contracts via the UEI path here and return [] from the name path
    # so dedupe logic still runs and totals match the prior assertion.
    monkeypatch.setattr(
        backlog_service, "fetch_contracts_for_recipient",
        lambda name, **k: [],
    )
    monkeypatch.setattr(
        backlog_service, "fetch_contracts_for_uei",
        lambda uei, **k: fake_contracts,
    )

    try:
        out = backlog_service.get_backlog_for_ticker("LMT")
        assert out["ticker"] == "LMT"
        assert "2" in out["headline"]
        # Top agency + top contract facts present
        assert len(out["facts"]) >= 2
        assert any("Department of Defense" in f["text"] for f in out["facts"])
        assert out["sources_used"] == ["usaspending"]
    finally:
        conn = get_connection()
        conn.execute("DELETE FROM entity_aliases WHERE alias_source='backlog_test'")
        conn.commit()
        conn.close()


def test_backlog_service_uses_name_when_no_uei_seeded(monkeypatch):
    """Service must surface contracts via NAME path even with no UEI alias."""
    from datetime import datetime, timezone

    from api.services import backlog_service
    from src.data.entity_aliases import insert_alias
    from src.utils.db import get_connection, init_db

    init_db()
    now = datetime.now(tz=timezone.utc).isoformat()
    insert_alias(
        ticker="LMT_TEST", cik=None, uei=None,  # NO UEI
        alias_type="legal", alias_name="Lockheed Martin Corporation",
        alias_source="backlog_test", confidence=1.0, created_at=now,
    )

    fake_contracts = [{
        "award_id": "TEST-1", "recipient_name": "LOCKHEED MARTIN CORPORATION",
        "award_amount": 1_000_000, "award_type": "A",
        "action_date": "2026-05-01", "awarding_agency": "Department of Defense",
    }]
    monkeypatch.setattr(
        backlog_service, "fetch_contracts_for_recipient",
        lambda name, **k: fake_contracts,
    )
    # UEI fetch returns empty since no UEI seeded
    monkeypatch.setattr(
        backlog_service, "fetch_contracts_for_uei",
        lambda uei, **k: [],
    )

    try:
        out = backlog_service.get_backlog_for_ticker("LMT_TEST")
        assert out["facts"], "should return contracts via name path"
    finally:
        conn = get_connection()
        conn.execute("DELETE FROM entity_aliases WHERE alias_source='backlog_test'")
        conn.commit()
        conn.close()
