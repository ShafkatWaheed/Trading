"""Tests for fda_catalysts_service (Wave 2, Phase D.3)."""
from __future__ import annotations


def test_fda_catalysts_service_for_unknown_ticker_returns_empty(monkeypatch):
    from api.services.fda_catalysts_service import get_fda_catalysts_for_ticker

    # No entity aliases set up → no sponsor names → empty
    out = get_fda_catalysts_for_ticker("ZZZ_NOPE")
    assert out["ticker"] == "ZZZ_NOPE"
    assert out["headline"]                # always present
    assert out["facts"] == []


def test_fda_catalysts_service_for_known_ticker_returns_info(monkeypatch):
    from datetime import datetime, timezone

    from api.services import fda_catalysts_service
    from src.data.entity_aliases import insert_alias
    from src.utils.db import init_db

    init_db()
    insert_alias(
        ticker="PFE", cik=None, uei=None,
        alias_type="legal", alias_name="pfizer",
        alias_source="fda_test", confidence=1.0,
        created_at=datetime.now(tz=timezone.utc).isoformat(),
    )

    fake_apps = [
        {"application_number": "NDA022345", "sponsor_name": "PFIZER INC",
         "submission_type": "ORIG", "submission_status": "AP", "action_date": "20260115"},
        {"application_number": "NDA022346", "sponsor_name": "PFIZER INC",
         "submission_type": "ORIG", "submission_status": "AP", "action_date": "20260120"},
    ]
    monkeypatch.setattr(
        fda_catalysts_service, "fetch_fda_applications_for_sponsor",
        lambda sponsor_name, limit=100: fake_apps,
    )

    out = fda_catalysts_service.get_fda_catalysts_for_ticker("PFE")
    assert out["ticker"] == "PFE"
    assert "2" in out["headline"]
    assert len(out["facts"]) >= 2
    assert out["sources_used"] == ["openfda"]
