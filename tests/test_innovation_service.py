"""Tests for innovation_service (Wave 2)."""
from __future__ import annotations

import pytest


def test_innovation_service_for_unknown_ticker_returns_empty(monkeypatch):
    from api.services.innovation_service import get_innovation_for_ticker

    # No entity aliases set up → no canonical assignee → empty
    out = get_innovation_for_ticker("ZZZ_NOPE")
    assert out["ticker"] == "ZZZ_NOPE"
    assert out["headline"]                # always present
    assert out["facts"] == []


def test_innovation_service_for_known_ticker_returns_info(monkeypatch):
    from datetime import datetime, timezone
    from api.services import innovation_service
    from src.data.entity_aliases import insert_alias
    from src.utils.db import init_db

    init_db()
    insert_alias(
        ticker="AAPL", cik=None, uei=None,
        alias_type="uspto_canonical", alias_name="apple",
        alias_source="innov_test", confidence=1.0,
        created_at=datetime.now(tz=timezone.utc).isoformat(),
    )

    fake_patents = [
        {"patent_id": "1", "title": "T1", "date": "2026-01-01", "cpc_class": "G06N", "assignee": "Apple Inc."},
        {"patent_id": "2", "title": "T2", "date": "2026-02-01", "cpc_class": "G06N", "assignee": "Apple Inc."},
    ]
    monkeypatch.setattr(
        innovation_service, "fetch_patents_for_assignee",
        lambda assignee, since_date, max_results=100: fake_patents,
    )

    out = innovation_service.get_innovation_for_ticker("AAPL")
    assert out["ticker"] == "AAPL"
    assert "2 patents" in out["headline"]
    assert len(out["facts"]) >= 2
