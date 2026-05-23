"""Tests for the consolidated patent_events mapper (Wave 2, Phase 2)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.analysis.sector_signals.patent_events import patent_events_to_information


def _today_plus_days(d: int) -> str:
    return (datetime.now(tz=timezone.utc).date() + timedelta(days=d)).strftime("%b %d, %Y")


def test_empty_inputs_returns_low_signal():
    info = patent_events_to_information(
        ticker="AAPL", as_of="2026-05-16T00:00:00Z",
        orange_book_patents=[], itc_investigations=[],
        license_deals=[], litigation_events=[],
    )
    assert info.severity == "low"
    assert info.confidence == "low"
    assert info.facts == []
    assert info.topic == "patent_events"


def test_near_term_patent_cliff_is_high_severity():
    patents = [{
        "application_number": "207103",
        "patent_number": "8685975",
        "patent_expire_date": _today_plus_days(180),  # 6 months out
        "drug_substance_flag": True,
        "drug_product_flag": False,
        "use_code": "U-1234",
        "sponsor_name": "PFIZER INC",
        "trade_name": "IBRANCE",
    }]
    info = patent_events_to_information(
        ticker="PFE", as_of="2026-05-16T00:00:00Z",
        orange_book_patents=patents, itc_investigations=[],
        license_deals=[], litigation_events=[],
    )
    assert info.severity == "high"
    assert "fda_orange_book" in info.sources_used
    assert any("IBRANCE" in f.text or "207103" in f.text for f in info.facts)


def test_active_337_respondent_is_high_severity():
    itc = [{
        "investigation_number": "337-TA-1234",
        "title": "Certain Devices",
        "party_name": "Apple",
        "party_role": "respondent",
        "status": "Active",
        "filing_date": "",
    }]
    info = patent_events_to_information(
        ticker="AAPL", as_of="2026-05-16T00:00:00Z",
        orange_book_patents=[], itc_investigations=itc,
        license_deals=[], litigation_events=[],
    )
    assert info.severity == "high"
    assert "itc_edis" in info.sources_used


def test_license_deal_alone_is_medium_severity():
    # Use a duck-typed object with the same attrs as LicenseDeal
    class _LD:
        def __init__(self, dt, cp, s):
            self.deal_type, self.counterparty, self.summary = dt, cp, s
    deals = [_LD("license", "Novartis", "Cross-license patent agreement")]
    info = patent_events_to_information(
        ticker="PFE", as_of="2026-05-16T00:00:00Z",
        orange_book_patents=[], itc_investigations=[],
        license_deals=deals, litigation_events=[],
    )
    assert info.severity == "med"
    assert "sec_8k" in info.sources_used


def test_verdict_against_company_is_high_severity():
    class _LE:
        def __init__(self, k, d, s):
            self.event_kind, self.direction, self.summary = k, d, s
    events = [_LE("verdict", "against_company", "Damages of $200M")]
    info = patent_events_to_information(
        ticker="X", as_of="2026-05-16T00:00:00Z",
        orange_book_patents=[], itc_investigations=[],
        license_deals=[], litigation_events=events,
    )
    assert info.severity == "high"


def test_multiple_sources_aggregate_correctly():
    patents = [{"application_number":"X","patent_number":"1","patent_expire_date":_today_plus_days(400),
                "drug_substance_flag":True,"drug_product_flag":False,"use_code":"","sponsor_name":"X","trade_name":"DrugA"}]
    class _LD:
        deal_type, counterparty, summary = "license", "PartyA", "Cross-license"
    info = patent_events_to_information(
        ticker="PFE", as_of="2026-05-16T00:00:00Z",
        orange_book_patents=patents, itc_investigations=[],
        license_deals=[_LD()], litigation_events=[],
    )
    # cliff in 13 months (>12) = med, license deal = med → headline mentions both
    assert info.severity == "med"
    assert len(info.facts) >= 2
    assert "fda_orange_book" in info.sources_used
    assert "sec_8k" in info.sources_used
