"""Tests for the extended freshness service that surfaces source registry."""
from __future__ import annotations

from api.services.freshness_service import get_sources_status
from src.data.source_freshness_registry import (
    EXPECTED_SOURCES,
    register_all_wave1_plus_sources,
)


def test_get_sources_status_returns_all_registered():
    register_all_wave1_plus_sources()
    status = get_sources_status()
    assert "sources" in status
    sources = {row["source"] for row in status["sources"]}
    for src in EXPECTED_SOURCES:
        assert src in sources


def test_get_sources_status_includes_counts_by_status():
    register_all_wave1_plus_sources()
    status = get_sources_status()
    assert "counts" in status
    # All sources are freshly registered with no fetch yet → 'never_fetched'
    assert status["counts"].get("never_fetched", 0) >= len(EXPECTED_SOURCES)
