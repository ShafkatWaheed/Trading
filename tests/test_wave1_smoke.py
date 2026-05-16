"""End-to-end smoke test of Wave 1 foundation.

Walks every public surface added in Wave 1:
  - Schema tables exist
  - Manual override seeder works
  - Resolver returns the right ticker
  - Source registry knows about all 18 endpoints
  - assert_no_lookahead enforces point-in-time
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from src.analysis.edge_validator import LookaheadViolation, assert_no_lookahead
from src.analysis.sector_signals._shared import (
    Fact,
    SignalReading,
    StockInformation,
)
from src.data.entity_aliases import (
    insert_alias,
    resolve_ticker,
    seed_from_overrides,
)
from src.data.source_freshness import get_all_sources
from src.data.source_freshness_registry import (
    EXPECTED_SOURCES,
    register_all_wave1_plus_sources,
)
from src.utils.db import get_connection, init_db


def test_wave1_smoke_end_to_end():
    init_db()

    # 1) Manual overrides seed: BRK.B dual-class
    seed_from_overrides()
    r = resolve_ticker("Berkshire Hathaway Class B")
    assert r is not None and r.ticker == "BRK.B"

    # 2) Subsidiary rollup: Beats Electronics LLC → AAPL
    r = resolve_ticker("Beats Electronics LLC")
    assert r is not None and r.ticker == "AAPL"

    # 3) Fuzzy match (information threshold)
    insert_alias(
        ticker="LMT", cik=None, uei=None,
        alias_type="legal", alias_name="lockheed martin",
        alias_source="smoke_test", confidence=1.0,
        created_at="2026-05-15T00:00:00Z",
    )
    r = resolve_ticker("Lockheed-Martin Co", use_fuzzy=True, min_confidence=0.8)
    assert r is not None and r.ticker == "LMT"

    # 4) Source registry has all 18 endpoints
    register_all_wave1_plus_sources()
    registered = {s.source for s in get_all_sources()}
    for src in EXPECTED_SOURCES:
        assert src in registered

    # 5) StockInformation construction (information-only output)
    si = StockInformation(
        ticker="AAPL", topic="innovation",
        headline="Filed 1,247 patents in last 12mo",
        facts=[Fact(
            text="1247 patents", as_of="2026-05-15T00:00:00Z",
            source="uspto", source_url=None, confidence=1.0,
        )],
        narrative=None, implications=[], related_catalysts=[],
        confidence="high", as_of="2026-05-15T00:00:00Z",
        sources_used=["uspto"], severity="low",
    )
    assert si.ticker == "AAPL"

    # 6) SignalReading construction with Decimal
    sr = SignalReading(
        ticker="LMT", sector=None, signal_name="gov_contract_award",
        value=Decimal("4200000000"), z_score=None,
        direction="bullish", confidence="high",
        as_of="2026-05-10T00:00:00Z",
        available_at="2026-05-13T00:00:00Z",
        point_in_time_lag_days=3, source="usaspending",
    )

    # 7) Lookahead gate: a reading available 2026-05-13 is OK for 2026-05-15 decision
    assert_no_lookahead([sr], decision_timestamp="2026-05-15T00:00:00Z")

    # 8) Lookahead gate: a reading available 2026-05-20 is NOT OK for 2026-05-15 decision
    sr_future = SignalReading(
        ticker="X", sector=None, signal_name="x",
        value=Decimal("1"), z_score=None,
        direction="neutral", confidence="low",
        as_of="2026-05-20T00:00:00Z",
        available_at="2026-05-20T00:00:00Z",
        point_in_time_lag_days=0, source="test",
    )
    with pytest.raises(LookaheadViolation):
        assert_no_lookahead([sr_future], decision_timestamp="2026-05-15T00:00:00Z")


def test_wave1_smoke_cleanup():
    """Clean up the smoke_test row inserted by the smoke test above."""
    conn = get_connection()
    conn.execute("DELETE FROM entity_aliases WHERE alias_source = 'smoke_test'")
    conn.commit()
    conn.close()
