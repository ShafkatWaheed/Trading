"""Tests for ITC §337 → StockInformation mapper (Wave 2, Phase F.2)."""
from __future__ import annotations

from src.analysis.sector_signals.itc import itc_investigations_to_information


def test_itc_mapper_with_respondent_yields_high_severity():
    rows = [
        # Investigation 1 — Apple is complainant
        {
            "investigation_number": "337-TA-1234",
            "title": "Certain Mobile Devices and Components Thereof",
            "party_name": "Apple Inc.",
            "party_role": "complainant",
            "status": "Active",
            "filing_date": "2026-02-01",
        },
        # Investigation 2 — Apple is respondent (active → high severity)
        {
            "investigation_number": "337-TA-1235",
            "title": "Certain Wireless Audio Equipment",
            "party_name": "Apple Inc.",
            "party_role": "respondent",
            "status": "Active",
            "filing_date": "2026-03-15",
        },
    ]
    info = itc_investigations_to_information(
        ticker="AAPL", investigations=rows, as_of="2026-05-15T00:00:00Z"
    )
    assert info.ticker == "AAPL"
    assert info.topic == "litigation"
    assert info.severity == "high"
    assert info.sources_used == ["itc_edis"]
    # Headline mentions both counts
    assert "1 as respondent" in info.headline
    assert "1 as complainant" in info.headline
    assert "§337" in info.headline
    # Facts populated (up to 5)
    assert len(info.facts) == 2
    assert all(f.source == "itc_edis" for f in info.facts)


def test_itc_mapper_empty_returns_low_signal():
    info = itc_investigations_to_information(
        ticker="AAPL", investigations=[], as_of="2026-05-15T00:00:00Z"
    )
    assert info.severity == "low"
    assert info.confidence == "low"
    assert info.facts == []
    assert info.sources_used == ["itc_edis"]
