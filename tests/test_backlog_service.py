"""Tests for backlog_service (Wave 2, Phase E.3)."""
from __future__ import annotations


def test_backlog_service_for_unknown_ticker_returns_empty(monkeypatch):
    from api.services.backlog_service import get_backlog_for_ticker

    # No sam_business_name aliases → no UEIs → empty result
    out = get_backlog_for_ticker("ZZZ_NOPE")
    assert out["ticker"] == "ZZZ_NOPE"
    assert out["headline"]                # always present
    assert out["facts"] == []
    assert out["sources_used"] == ["usaspending"]


def test_backlog_service_for_known_ticker_returns_info(monkeypatch):
    from datetime import datetime, timezone

    from api.services import backlog_service
    from src.data.entity_aliases import insert_alias
    from src.utils.db import init_db

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
    monkeypatch.setattr(
        backlog_service, "fetch_contracts_for_uei",
        lambda uei, since_date, max_results=100: fake_contracts,
    )

    out = backlog_service.get_backlog_for_ticker("LMT")
    assert out["ticker"] == "LMT"
    assert "2" in out["headline"]
    # Top agency + top contract facts present
    assert len(out["facts"]) >= 2
    assert any("Department of Defense" in f["text"] for f in out["facts"])
    assert out["sources_used"] == ["usaspending"]
