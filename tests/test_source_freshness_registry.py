"""All 17 sector-influence endpoints must pre-register on import."""
from __future__ import annotations

from src.data.source_freshness import get_all_sources
from src.data.source_freshness_registry import (
    EXPECTED_SOURCES,
    register_all_wave1_plus_sources,
)


def test_all_17_sources_registered_after_call():
    register_all_wave1_plus_sources()
    registered = {s.source for s in get_all_sources()}
    for src in EXPECTED_SOURCES:
        assert src in registered, f"source not registered: {src}"


def test_expected_sources_list_size():
    # Spec §3 lists 15 "sources" but several are aggregates of multiple
    # endpoints with distinct cadences. Container rates = Drewry + Freightos
    # (2 endpoints); the Goods Flow card draws from 5 endpoints; the
    # "USDA NASS + NOAA weather" spec row is 2 sources. We track 17
    # endpoints independently for freshness. (Was 18 before the Innovation
    # card was dropped — see post-Wave-2 design change in the spec.)
    assert len(EXPECTED_SOURCES) == 17


def test_expected_sources_have_unique_names():
    assert len(EXPECTED_SOURCES) == len(set(EXPECTED_SOURCES))


def test_idempotent_registration():
    register_all_wave1_plus_sources()
    n1 = len(get_all_sources())
    register_all_wave1_plus_sources()
    n2 = len(get_all_sources())
    assert n1 == n2
