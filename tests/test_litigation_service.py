"""Tests for litigation_service (Wave 2, Phase F.3)."""
from __future__ import annotations


def test_litigation_service_for_unknown_ticker_returns_empty(monkeypatch):
    from api.services.litigation_service import get_litigation_for_ticker

    # No legal/common/override aliases → no EDIS queries → empty result
    out = get_litigation_for_ticker("ZZZ_NOPE")
    assert out["ticker"] == "ZZZ_NOPE"
    assert out["headline"]                # always present
    assert out["facts"] == []
    assert out["sources_used"] == ["itc_edis"]
    assert out["severity"] == "low"


def test_litigation_service_for_known_ticker_returns_info(monkeypatch):
    from datetime import datetime, timezone

    from api.services import litigation_service
    from src.data.entity_aliases import insert_alias
    from src.utils.db import init_db

    init_db()
    insert_alias(
        ticker="AAPL", cik=None, uei=None,
        alias_type="legal", alias_name="apple",
        alias_source="litigation_test", confidence=1.0,
        created_at=datetime.now(tz=timezone.utc).isoformat(),
    )

    fake_rows = [
        {
            "investigation_number": "337-TA-1234",
            "title": "Certain Mobile Devices and Components Thereof",
            "party_name": "Apple Inc.",
            "party_role": "complainant",
            "status": "Active",
            "filing_date": "2026-02-01",
        },
        {
            "investigation_number": "337-TA-1235",
            "title": "Certain Wireless Audio Equipment",
            "party_name": "Apple Inc.",
            "party_role": "respondent",
            "status": "Active",
            "filing_date": "2026-03-15",
        },
    ]
    monkeypatch.setattr(
        litigation_service, "fetch_337_investigations_for_party",
        lambda name: fake_rows,
    )

    out = litigation_service.get_litigation_for_ticker("AAPL")
    assert out["ticker"] == "AAPL"
    assert out["topic"] == "litigation"
    # Active respondent → high severity
    assert out["severity"] == "high"
    assert "1 as respondent" in out["headline"]
    assert "1 as complainant" in out["headline"]
    assert len(out["facts"]) >= 1
    assert out["sources_used"] == ["itc_edis"]
