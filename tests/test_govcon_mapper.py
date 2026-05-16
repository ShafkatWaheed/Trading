"""Tests for the gov-contracts (Backlog) mapper (Wave 2, Phase E.2)."""
from __future__ import annotations

from src.analysis.sector_signals.govcon import contracts_to_information


def test_contracts_to_information_aggregates_by_awarding_agency():
    contracts = [
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
        {
            "award_id": "N00019-25-C-0099",
            "recipient_name": "LOCKHEED MARTIN CORPORATION",
            "award_amount": 1_500_000_000,
            "award_type": "Definitive Contract",
            "action_date": "2026-02-10",
            "awarding_agency": "Department of Defense",
        },
    ]
    info = contracts_to_information(
        ticker="LMT", contracts=contracts, as_of="2026-05-15T00:00:00Z"
    )
    assert info.ticker == "LMT"
    assert info.topic == "gov_backlog"
    # Count + total appear in headline
    assert "3 contracts" in info.headline
    assert "6.6B" in info.headline  # 4.2B + 0.85B + 1.5B = 6.55B → "6.6B" via Decimal .1f banker's rounding
    # Top agency aggregation present in facts (DoD dominates with 4.2+1.5 = 5.7B)
    assert any("Department of Defense" in f.text for f in info.facts)
    assert info.sources_used == ["usaspending"]
    assert info.confidence == "high"


def test_contracts_to_information_empty_returns_low_signal():
    info = contracts_to_information(
        ticker="LMT", contracts=[], as_of="2026-05-15T00:00:00Z"
    )
    assert info.severity == "low"
    assert info.confidence == "low"
    assert info.facts == []
