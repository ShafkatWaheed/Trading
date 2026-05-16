"""Tests for exec-changes → StockInformation mapper (Wave 2, Phase G.2)."""
from __future__ import annotations

from src.analysis.sector_signals.exec_turnover import (
    exec_changes_to_information,
)


_CFO_DEPARTURE_8K = """
Item 5.02 Departure of Directors or Certain Officers; Election of
Directors; Appointment of Certain Officers.

On May 1, 2026, Jane Smith, Chief Financial Officer of the Company,
notified the Company of her decision to resign from her position
effective immediately.
"""


def test_exec_turnover_with_cfo_departure_yields_high_severity():
    filings = [
        {
            "accession_number": "0001000000-26-000010",
            "form": "8-K",
            "filing_date": "2026-05-02",
            "primary_document_url": "https://www.sec.gov/Archives/edgar/data/1/000100000026000010/doc.htm",
            "raw_text": _CFO_DEPARTURE_8K,
        },
    ]
    info = exec_changes_to_information(
        ticker="ACME", filings_8k=filings, as_of="2026-05-15T00:00:00Z"
    )

    assert info.ticker == "ACME"
    assert info.topic == "exec_changes"
    assert info.sources_used == ["sec_8k"]
    assert info.severity == "high"
    assert info.confidence == "high"
    # Headline mentions counts
    assert "1 departures" in info.headline
    assert "0 appointments" in info.headline
    assert "180 days" in info.headline
    # At least one fact populated for the CFO departure
    assert len(info.facts) >= 1
    assert info.facts[0].source == "sec_8k"


def test_exec_turnover_empty_returns_low_signal():
    info = exec_changes_to_information(
        ticker="ACME", filings_8k=[], as_of="2026-05-15T00:00:00Z"
    )
    assert info.severity == "low"
    assert info.confidence == "low"
    assert info.facts == []
    assert info.sources_used == ["sec_8k"]
    assert info.topic == "exec_changes"
