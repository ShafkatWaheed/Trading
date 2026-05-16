"""Tests for innovation (patents+trademarks) mapper (Wave 2)."""
from __future__ import annotations

from src.analysis.sector_signals.innovation import patents_to_information


def test_patents_to_information_aggregates_by_cpc_class():
    patents = [
        {"patent_id": "11234567", "title": "ML on-device", "date": "2026-01-15",
         "cpc_class": "G06N", "assignee": "Apple Inc."},
        {"patent_id": "11234568", "title": "Display optics", "date": "2026-02-20",
         "cpc_class": "H04W", "assignee": "Apple Inc."},
        {"patent_id": "11234569", "title": "More ML", "date": "2026-03-10",
         "cpc_class": "G06N", "assignee": "Apple Inc."},
    ]
    info = patents_to_information(ticker="AAPL", patents=patents, as_of="2026-05-15T00:00:00Z")
    assert info.ticker == "AAPL"
    assert info.topic == "innovation"
    assert "3 patents" in info.headline or "3 grants" in info.headline.lower()
    # Top CPC class with 2 of 3 should appear in implications or facts
    assert any("G06N" in f.text for f in info.facts)
    assert info.sources_used == ["uspto_patentsview"]


def test_patents_to_information_empty_returns_low_signal():
    info = patents_to_information(ticker="AAPL", patents=[], as_of="2026-05-15T00:00:00Z")
    assert info.severity == "low"
    assert info.confidence == "low"
    assert info.facts == []
