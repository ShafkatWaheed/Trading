"""Catalog of the 15 sector-influence sources (Wave 1+ spec §3).

Calling `register_all_wave1_plus_sources()` makes them visible on the
`source_freshness` table — even before their data fetchers exist. The
admin /freshness page then shows them with last_fetched_at=NULL so we
can see staleness uniformly as fetchers are added wave by wave.
"""
from __future__ import annotations

from src.data.source_freshness import register_source


# (source, cadence, ttl_seconds, rate_limit_budget_per_day)
_SOURCES: tuple[tuple[str, str, int, int | None], ...] = (
    # ── Scored signals (7) ────────────────────────────────────────
    ("openfda",            "daily",     86400,   240 * 60 * 24),   # 240/min unauth
    ("usaspending",        "daily",     86400,   1000),
    ("sam_gov_entity",     "monthly",   30 * 86400, 1000),
    ("itc_edis",           "twice_daily", 12 * 3600, None),
    ("sec_8k",             "hourly",    3600,    None),            # piggybacks on existing SEC EDGAR pipeline
    ("drewry_wci",         "weekly",    7 * 86400, None),          # scrape
    ("freightos_fbx",      "daily",     86400,   None),
    ("eia_inventories",    "weekly",    7 * 86400, 5000 * 24),
    ("census_bps",         "monthly",   30 * 86400, None),
    # ── Information sources (8) ───────────────────────────────────
    ("uspto_patentsview",  "weekly",    7 * 86400, None),
    ("uspto_tsdr",         "daily",     86400,   None),
    ("cass_freight",       "monthly",   30 * 86400, None),         # scrape
    ("aar_rail",           "weekly",    7 * 86400, None),          # scrape
    ("port_of_la",         "weekly",    7 * 86400, None),          # scrape
    ("lda_lobbying",       "weekly",    7 * 86400, None),
    ("ustr_federal_register", "daily",  86400,   1000),
    ("usda_nass",          "monthly",   30 * 86400, None),
    ("noaa_weather",       "daily",     86400,   None),
)


EXPECTED_SOURCES: tuple[str, ...] = tuple(s[0] for s in _SOURCES)


def register_all_wave1_plus_sources() -> int:
    """Register all sector-influence endpoints with the freshness registry. Idempotent.

    Returns the count registered (== len(_SOURCES) on success).

    Note: spec §3 lists 15 "sources" but we track 18 endpoints because
    several spec sources are aggregates (e.g. container rates =
    Drewry + Freightos; the Goods Flow card draws on Drewry, Freightos,
    Cass, AAR, and Port of LA; USDA NASS + NOAA weather is one spec
    row = 2 endpoints).
    """
    count = 0
    for source, cadence, ttl, budget in _SOURCES:
        register_source(
            source=source, cadence=cadence,
            ttl_seconds=ttl, rate_limit_budget=budget,
        )
        count += 1
    return count
