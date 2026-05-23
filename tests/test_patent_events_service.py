"""Tests for patent_events_service (orchestrator for the consolidated card)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest


def test_patent_events_unknown_ticker_returns_low_signal():
    from api.services.patent_events_service import get_patent_events_for_ticker

    out = get_patent_events_for_ticker("ZZZ_NONEXISTENT")
    assert out["ticker"] == "ZZZ_NONEXISTENT"
    assert out["topic"] == "patent_events"
    assert out["severity"] == "low"
    assert out["facts"] == []


def test_patent_events_aggregates_all_four_streams(monkeypatch):
    """When all four fetchers return data, service merges them correctly."""
    from datetime import datetime, timedelta, timezone
    from src.data.entity_aliases import insert_alias
    from src.utils.db import init_db
    from api.services import patent_events_service

    init_db()
    now = datetime.now(tz=timezone.utc).isoformat()
    insert_alias(
        ticker="PFE", cik="0000078003", uei=None,
        alias_type="legal", alias_name="Pfizer Inc",
        alias_source="pe_test", confidence=1.0, created_at=now,
    )

    # Stub all four fetchers
    cliff_date = (datetime.now(tz=timezone.utc) + timedelta(days=180)).strftime("%Y-%m-%d")
    monkeypatch.setattr(patent_events_service, "fetch_patents_for_sponsor",
        lambda name, **k: [{
            "application_number": "207103", "patent_number": "8685975",
            "patent_expire_date": cliff_date,
            "drug_substance_flag": True, "drug_product_flag": False,
            "use_code": "U-1", "sponsor_name": "PFIZER INC", "trade_name": "IBRANCE",
        }],
    )
    monkeypatch.setattr(patent_events_service, "fetch_337_investigations_for_party",
        lambda name: [{
            "investigation_number": "337-TA-1234", "title": "Certain Biologic Reactors",
            "party_name": "Pfizer", "party_role": "respondent",
            "status": "Active", "filing_date": "",
        }],
    )
    monkeypatch.setattr(patent_events_service, "fetch_recent_8ks",
        lambda cik, days=180: [{"accession_number":"x", "form":"8-K",
            "filing_date":"2026-04-15", "primary_document_url":"",
            "raw_text": """Item 1.01 Entry into a Material Definitive Agreement.
On April 1, 2026, the Company entered into a patent license agreement with
Counterparty Holdings Inc. paying a 4% royalty."""}],
    )
    # parse_8k_item_801 will return empty for this raw_text (no Item 8.01)

    out = patent_events_service.get_patent_events_for_ticker("PFE")
    assert out["ticker"] == "PFE"
    assert out["topic"] == "patent_events"
    # 1 cliff + 1 §337 + 1 license = at minimum 3 facts
    assert len(out["facts"]) >= 3
    # Severity should be high (cliff <12mo OR respondent §337)
    assert out["severity"] == "high"
    sources = set(out["sources_used"])
    assert {"fda_orange_book", "itc_edis", "sec_8k"}.issubset(sources)

    # Cleanup
    from src.utils.db import get_connection
    conn = get_connection()
    conn.execute("DELETE FROM entity_aliases WHERE alias_source = 'pe_test'")
    conn.commit()
    conn.close()


def test_patent_events_no_cik_skips_8k_streams(monkeypatch):
    """Tickers without a CIK should not call fetch_recent_8ks."""
    from datetime import datetime, timezone
    from src.data.entity_aliases import insert_alias
    from src.utils.db import init_db
    from api.services import patent_events_service

    init_db()
    now = datetime.now(tz=timezone.utc).isoformat()
    insert_alias(
        ticker="NO_CIK_TEST", cik=None, uei=None,
        alias_type="legal", alias_name="No CIK Test Inc",
        alias_source="pe_test", confidence=1.0, created_at=now,
    )

    fetch_calls = {"n": 0}
    def _fail_8k_fetch(cik, days=180):
        fetch_calls["n"] += 1
        return []

    monkeypatch.setattr(patent_events_service, "fetch_patents_for_sponsor", lambda *a, **k: [])
    monkeypatch.setattr(patent_events_service, "fetch_337_investigations_for_party", lambda *a, **k: [])
    monkeypatch.setattr(patent_events_service, "fetch_recent_8ks", _fail_8k_fetch)

    out = patent_events_service.get_patent_events_for_ticker("NO_CIK_TEST")
    assert out["severity"] == "low"
    assert fetch_calls["n"] == 0  # 8-K fetch was skipped because no CIK

    from src.utils.db import get_connection
    conn = get_connection()
    conn.execute("DELETE FROM entity_aliases WHERE alias_source = 'pe_test'")
    conn.commit()
    conn.close()
