"""Tests for FDA Catalysts mapper (Wave 2, Phase D.2)."""
from __future__ import annotations

from src.analysis.sector_signals.fda import fda_applications_to_information


def test_fda_applications_to_information_aggregates_by_status():
    applications = [
        {"application_number": "NDA022345", "sponsor_name": "PFIZER INC",
         "submission_type": "ORIG", "submission_status": "AP", "action_date": "20260115"},
        {"application_number": "NDA022346", "sponsor_name": "PFIZER INC",
         "submission_type": "ORIG", "submission_status": "AP", "action_date": "20260120"},
        {"application_number": "BLA125678", "sponsor_name": "PFIZER INC",
         "submission_type": "SUPPL", "submission_status": "TA", "action_date": "20260220"},
    ]
    info = fda_applications_to_information(
        ticker="PFE", applications=applications, as_of="2026-05-15T00:00:00Z"
    )
    assert info.ticker == "PFE"
    assert info.topic == "fda_pipeline"
    # Headline should mention the count
    assert "3" in info.headline
    # Status aggregation should surface in facts
    assert any("AP" in f.text for f in info.facts)
    assert info.sources_used == ["openfda"]


def test_fda_applications_to_information_empty_returns_low_signal():
    info = fda_applications_to_information(
        ticker="PFE", applications=[], as_of="2026-05-15T00:00:00Z"
    )
    assert info.severity == "low"
    assert info.confidence == "low"
    assert info.facts == []
