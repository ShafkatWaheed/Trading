"""Tests for exec_changes_service (Wave 2, Phase G.3)."""
from __future__ import annotations


def test_exec_changes_service_for_unknown_ticker_returns_empty():
    from api.services.exec_changes_service import get_exec_changes_for_ticker

    # No legal alias / CIK on file → empty result (low severity)
    out = get_exec_changes_for_ticker("ZZZ_NOPE")
    assert out["ticker"] == "ZZZ_NOPE"
    assert out["topic"] == "exec_changes"
    assert out["headline"]  # always present
    assert out["facts"] == []
    assert out["sources_used"] == ["sec_8k"]
    assert out["severity"] == "low"
    assert out["confidence"] == "low"


def test_exec_changes_service_for_known_cik_returns_info(monkeypatch):
    from datetime import datetime, timezone

    from api.services import exec_changes_service
    from src.data.entity_aliases import insert_alias
    from src.utils.db import init_db

    init_db()
    insert_alias(
        ticker="ACME",
        cik="0001234567",
        uei=None,
        alias_type="legal",
        alias_name="acme corp",
        alias_source="exec_changes_test",
        confidence=1.0,
        created_at=datetime.now(tz=timezone.utc).isoformat(),
    )

    fake_filings = [
        {
            "accession_number": "0001234567-26-000001",
            "form": "8-K",
            "filing_date": "2026-05-02",
            "primary_document_url": "https://www.sec.gov/Archives/edgar/data/1234567/000123456726000001/doc.htm",
            "raw_text": (
                "Item 5.02 Departure of Directors or Certain Officers; "
                "Election of Directors; Appointment of Certain Officers.\n\n"
                "On May 1, 2026, Jane Smith, Chief Financial Officer of the "
                "Company, notified the Company of her decision to resign "
                "from her position effective immediately."
            ),
        },
    ]
    monkeypatch.setattr(
        exec_changes_service, "fetch_recent_8ks",
        lambda cik, days=180: fake_filings,
    )

    out = exec_changes_service.get_exec_changes_for_ticker("ACME")
    assert out["ticker"] == "ACME"
    assert out["topic"] == "exec_changes"
    assert out["sources_used"] == ["sec_8k"]
    # CFO departure → high severity
    assert out["severity"] == "high"
    assert "1 departures" in out["headline"]
    assert len(out["facts"]) >= 1
