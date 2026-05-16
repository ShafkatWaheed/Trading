"""Tests for manual entity-override YAML loader (Wave 1)."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.data.entity_aliases import resolve_ticker, seed_from_overrides
from src.utils.db import get_connection, init_db


@pytest.fixture(autouse=True)
def _clean():
    init_db()
    conn = get_connection()
    conn.execute("DELETE FROM entity_aliases WHERE alias_source = 'override'")
    conn.commit()
    conn.close()
    yield


def test_seed_from_overrides_loads_yaml(tmp_path: Path):
    yaml_text = """
overrides:
  - ticker: BRK.B
    aliases:
      - "Berkshire Hathaway Inc Class B"
      - "berkshire b"
  - ticker: GOOGL
    cik: "0001652044"
    aliases:
      - "Alphabet Inc Class A"
  - ticker: AAPL
    subsidiaries:
      - "Beats Electronics LLC"
      - "Apple Operations International"
"""
    p = tmp_path / "overrides.yaml"
    p.write_text(yaml_text)

    inserted = seed_from_overrides(yaml_path=p)
    assert inserted == 5  # 2 BRK + 1 GOOGL alias + 2 AAPL subs

    # alias lookup works (exact)
    r = resolve_ticker("Berkshire Hathaway Inc Class B")
    assert r is not None and r.ticker == "BRK.B"

    # subsidiary rollup
    r = resolve_ticker("Beats Electronics LLC")
    assert r is not None and r.ticker == "AAPL"
    assert r.alias_type == "subsidiary"


def test_seed_from_overrides_missing_file_returns_zero(tmp_path: Path):
    missing = tmp_path / "does_not_exist.yaml"
    assert seed_from_overrides(yaml_path=missing) == 0


def test_seed_from_overrides_default_path_works():
    """Default path should load the real entity_overrides.yaml and seed >0 rows."""
    n = seed_from_overrides()
    assert n > 0, "expected at least one entry seeded from default entity_overrides.yaml"
