"""Catalog of the 17 endpoints covering the 15 sector-influence sources (Wave 1+ spec §3).

Calling `register_all_wave1_plus_sources()` makes them visible on the
`source_freshness` table — even before their data fetchers exist. The
admin /freshness page then shows them with last_fetched_at=NULL so we
can see staleness uniformly as fetchers are added wave by wave.

Note on the 15-vs-17 distinction: spec §3 lists 15 logical "sources"
but several are aggregates of multiple endpoints with distinct native
publication cadences (e.g. container rates = Drewry + Freightos; the
Goods Flow card draws from Drewry, Freightos, Cass, AAR, and Port of
LA; the USDA NASS + NOAA weather spec row is 2 endpoints). We track
all 17 endpoints independently for freshness. (Was 18 before the
Innovation card was dropped — see post-Wave-2 design change note in
the spec.)

Per spec §6.1, the `cadence` column records the *native* publishing
cadence of the upstream source (used in UI/staleness labels) while
`ttl_seconds` is the cache TTL that drives when our fetchers re-poll.
The two are intentionally distinct: a weekly publication may still be
re-polled daily so we pick up the release within hours.
"""
from __future__ import annotations

from src.data.source_freshness import register_source


# (source, cadence, ttl_seconds, rate_limit_budget_per_day)
_SOURCES: tuple[tuple[str, str, int, int | None], ...] = (
    # ── Scored-signal endpoints (9) ──────────────────────────────
    ("openfda",            "daily",        24 * 3600,  240 * 60 * 24),   # 240/min unauth
    ("usaspending",        "weekly",       24 * 3600,  1000),
    ("sam_gov_entity",     "monthly",       7 * 86400, 1000),
    ("itc_edis",           "daily",         6 * 3600,  None),            # refresh 2×/day
    ("sec_8k",             "hourly",        1 * 3600,  None),            # piggybacks on existing SEC EDGAR pipeline
    ("drewry_wci",         "weekly",        7 * 86400, None),            # scrape, Thu publication
    ("freightos_fbx",      "daily",        24 * 3600,  None),
    ("eia_inventories",    "weekly",       24 * 3600,  5000 * 24),       # Wed 10:30 ET release
    ("census_bps",         "monthly",       7 * 86400, None),            # ~18th of next month
    # ── Information-source endpoints (8) ─────────────────────────
    ("uspto_tsdr",         "daily",        24 * 3600,  None),
    ("cass_freight",       "monthly",       7 * 86400, None),            # scrape, mid-month publication
    ("aar_rail",           "weekly",        7 * 86400, None),            # Wed publication
    ("port_of_la",         "weekly",       24 * 3600,  None),            # scrape
    ("lda_lobbying",       "quarterly",     7 * 86400, None),
    ("ustr_federal_register", "daily",     24 * 3600,  1000),
    ("usda_nass",          "monthly",       7 * 86400, None),
    ("noaa_weather",       "daily",         6 * 3600,  None),
)


EXPECTED_SOURCES: tuple[str, ...] = tuple(s[0] for s in _SOURCES)


def register_all_wave1_plus_sources() -> int:
    """Register all sector-influence endpoints with the freshness registry. Idempotent.

    Returns the count registered (== len(_SOURCES) on success).

    Note: spec §3 lists 15 "sources" but we track 17 endpoints because
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
