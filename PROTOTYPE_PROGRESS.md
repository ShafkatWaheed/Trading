# Prototype Progress Report — Week 1 Complete

Session date: 2026-05-09 (overnight autonomous build).

## What's done

**Week 1 of the 5-week plan in [PROTOTYPE_PLAN.md](PROTOTYPE_PLAN.md) is complete and tested.** All 107 prototype-related tests pass; data-integrity audit stays green; no other test regressions.

### New code

| File | Purpose |
|---|---|
| [PROTOTYPE_PLAN.md](PROTOTYPE_PLAN.md) | The 5-week plan — locked design decisions, demo script, file layout, risks |
| [src/utils/db.py](src/utils/db.py) | 7 new tables added to `init_db()`: `industries`, `stocks_universe`, `stock_industry`, `stock_peers`, `stock_relations`, `keyword_impact`, `keyword_groups` |
| [src/data/tier_a_seed.py](src/data/tier_a_seed.py) | **150 hand-curated Tier A stocks** spanning all 11 GICS sectors (Mag 7, semis, finance, pharma, energy, defense, utilities, etc.) |
| [src/data/universe_loader.py](src/data/universe_loader.py) | `load_tier_a()` — idempotent backfill of Tier A → `stocks_universe` + `stock_industry`. `get_universe(tier=...)` query helper. |
| [src/data/tier_classifier.py](src/data/tier_classifier.py) | Deterministic A/B/C/D rule. Pure function; offline-runnable. Tunable thresholds. |
| [src/data/index_loader.py](src/data/index_loader.py) | ETF holdings parser (iShares/Invesco CSV format). Network fetch with disk cache. `apply_universe_memberships()` upserts the universe with tier classification. Tier-A demotion guard ensures hand-seeded names stay tier A. |
| [src/data/industries_seed.py](src/data/industries_seed.py) | **142 yfinance industry codes** mapped to 11 GICS sectors. `load_industries()` upsert. |
| [src/data/industry_loader.py](src/data/industry_loader.py) | yfinance industry/sector puller. Resumable (skip already-tagged), rate-limited, CLI-runnable as `python -m src.data.industry_loader`. |
| [src/data/conglomerate_overrides.py](src/data/conglomerate_overrides.py) | **19 hand-curated multi-tag overrides** for AMZN (3 industries), GOOGL/GOOG, MSFT, AAPL, META, BRK-B (5 industries), TSLA, F, GM, DIS, CVS (3), PEP, WMT, JNJ, GE, ORCL, IBM, T. Replaces single yfinance tag with weighted mix. |
| [api/services/universe_service.py](api/services/universe_service.py) | Query layer for the universe with tier × industry × sector composability + pagination |
| [api/routes/universe.py](api/routes/universe.py) | `GET /universe?tier=A&industry=Semiconductors&limit=50` endpoint |
| [api/schemas.py](api/schemas.py) | Pydantic schemas: `UniverseStock`, `IndustryTag`, `TierCounts`, `UniverseResponse` |
| [api/main.py](api/main.py) | Router registered |

### New tests (74 added; all 107 prototype tests pass)

| File | Coverage |
|---|---|
| [tests/test_universe_schema.py](tests/test_universe_schema.py) | Schema migrations idempotent, tier check constraint, keyword_impact CHECK, Tier A seed integrity (≥8 sectors, Mag 7 present, thematic anchors present), loader idempotency |
| [tests/test_tier_classifier.py](tests/test_tier_classifier.py) | A/B/C/D edge cases, threshold overrides, batch helper, hand-seeded override |
| [tests/test_index_loader.py](tests/test_index_loader.py) | iShares CSV parser (skips metadata, filters cash/futures), upsert semantics, idempotency, **tier-A demotion guard** |
| [tests/test_industries_seed.py](tests/test_industries_seed.py) | All 11 sectors covered, ~140 industries, no dupes, critical industries (Uranium, Electrical Equipment, etc.) present |
| [tests/test_industry_loader.py](tests/test_industry_loader.py) | yfinance mocking via `sys.modules` injection (same pattern as backtester tests), force-vs-skip behaviour, market-cap backfill, new-industry auto-creation |
| [tests/test_universe_api.py](tests/test_universe_api.py) | Conglomerate weight integrity (every entry sums to 1.0), `/universe` endpoint smoke + filter tests |
| [tests/fixtures/sample_holdings.csv](tests/fixtures/sample_holdings.csv) | Real-format iShares-style fixture for the parser |

## How to use what's been built

### Database setup
The new tables auto-create on next `init_db()` call. Existing data is untouched.

```bash
source .venv/bin/activate
python -c "from src.utils.db import init_db; init_db()"
```

### Load the Tier A spine (offline, instant)
```bash
python -c "
from src.data.universe_loader import load_tier_a
from src.data.industries_seed import load_industries
load_industries()
print(load_tier_a())
"
```

### Pull index memberships from the live web (network-gated, opt-in)
```bash
python -c "
from src.data.index_loader import fetch_all_indices, apply_universe_memberships
mem = fetch_all_indices()                    # downloads to data/index_cache/
print({k: len(v) for k, v in mem.items()})
print(apply_universe_memberships(mem))
"
```
Cache files land in `data/index_cache/`. Re-runs reuse cached CSVs unless `force=True`.

### Pull yfinance industry tags for everything in the universe
```bash
python -m src.data.industry_loader            # all stocks_universe rows
python -m src.data.industry_loader --symbols AAPL,MSFT --force
```

### Apply conglomerate multi-tag overrides
```bash
python -c "
from src.data.conglomerate_overrides import apply_conglomerate_overrides
print(apply_conglomerate_overrides())
"
```

### Hit the API
```bash
uvicorn api.main:app --port 8000 --reload
curl 'http://localhost:8000/universe?tier=A&limit=10'
curl 'http://localhost:8000/universe?industry=Semiconductors'
curl 'http://localhost:8000/universe?sector=Healthcare&limit=200'
```

## Key design decisions made along the way

1. **`stocks_universe` is a NEW table, separate from the existing in-memory `STOCK_DB`.** The old 69-stock `src/data/stock_db.py` stays for backward compat (the agent + scheduler still consume it). The new 4,800-stock DB-backed universe is the prototype's foundation. Migration plan to consolidate is post-prototype.

2. **`source` column tracks provenance per row.** Tier-A-seed rows keep `source='tier_a_seed'` even after `index_loader` upserts run — the upsert preserves the original source and only updates the membership flags + market_cap. Tests check by symbol presence, not source filter.

3. **Tier A demotion is impossible after hand-seeding.** The upsert SQL has a `CASE` clause that pins tier='A' if either the new or existing row is A. A stock seeded into Tier A by hand can never get demoted by a later index-loader run that doesn't include it in S&P 500.

4. **Conglomerate override deletes ALL existing `stock_industry` rows for the symbol** before inserting the multi-tag, regardless of source. This was a bug discovered during testing — keeping `tier_a_seed` rows around caused UNIQUE conflicts on the multi-tag insert.

5. **Industries auto-create on yfinance pull.** If yfinance returns an industry code we haven't catalogued in `industries_seed.py`, the loader auto-inserts a row with the sector taken from yfinance. Test verifies this with a synthetic "Quantum Computing Services" industry.

6. **Tests use `sys.modules['yfinance']` injection** (matching the existing `tests/test_backtester_no_lookahead.py` pattern) to avoid live network calls. Real network paths are exercised only when manually invoked from the CLI.

7. **Audit-clean throughout.** [scripts/audit_data_integrity.py](scripts/audit_data_integrity.py) stays green — no fake-data violations, no lookahead patterns. The point-in-time guard infrastructure is unaffected by these changes.

## What's deferred to next sessions

### Week 2 — Keyword news engine (3-5 days)
- [ ] Hand-seed `keyword_impact` (~150-200 rows) across 15 domains: AI, oil, war, tariffs, rates, FDA, court rulings, antitrust, M&A, GLP-1, crypto, climate, mining
- [ ] `src/news/tokenize.py` — n-gram + NER + negation
- [ ] `src/news/aggregate.py` — diminishing-returns sum by industry
- [ ] `POST /news-impact` endpoint
- [ ] Validation against ~30 historical headlines

### Week 3 — Peer/competitor edges (5 days)
- [ ] Tier A hand-curated ~1,050 peer edges with `overlap_dimensions` (e.g. MSFT-GOOG: "cloud,AI,productivity")
- [ ] Claude per-industry batched peer ranking for Tier B/C/D (~150 industry batches via the existing `claude -p` subprocess pattern from [api/services/ai_analyst_service.py:51](api/services/ai_analyst_service.py#L51))
- [ ] `GET /graph/stock/{sym}/peers` endpoint
- [ ] Resumable jobs table for chunked Claude runs

### Week 4 — Supply chain + regulatory + graph traversal (5 days)
- [ ] ~30 hand-curated supply-chain spine edges (NVDA←TSM←ASML, hyperscalers←NVDA, etc.)
- [ ] Claude-Haiku 10-K Item 1A extraction for ~150 Tier A stocks
- [ ] Court ruling / FDA / antitrust keywords
- [ ] Graph traversal engine (1-2 hop)
- [ ] `GET /graph/stock/{sym}/neighborhood` endpoint

### Week 5 — UI + polish (5 days)
- [ ] React `/news-impact` page (textarea + grouped result list)
- [ ] React `/stock/[sym]/neighborhood` page (supply-chain + peer panels)
- [ ] Nav tab + design-system polish
- [ ] Performance check (<500ms queries)

## What needs the user awake (next session)

Three small decisions to make before week 2 starts:

1. **Run `fetch_all_indices()` once with network access.** This populates `data/index_cache/` from iShares/Invesco. Without this, Tier B/C/D in `stocks_universe` stays empty and the API only sees the 150 Tier A names. Network call, ~5MB total download, 10-30 seconds.

2. **Run `python -m src.data.industry_loader` overnight.** This pulls yfinance industry tags for all 4,800 stocks. Rate-limited to be polite (~3 hours runtime). Output: every row in `stocks_universe` gets a `stock_industry` mapping.

3. **Run `apply_conglomerate_overrides()` after the yfinance load** so the 19 conglomerates get their multi-tag mappings (replacing the single yfinance tag).

These three commands are sequential; only step 1 + step 2 need network. Doing all three takes about 4 hours wall-clock (mostly the yfinance pull).

## Status summary

| Layer | Status |
|---|---|
| Schema (7 tables) | ✅ migrated, idempotent, tested |
| Tier A spine (150 stocks) | ✅ hand-curated, loaded, tested |
| Industries reference (~142 codes) | ✅ seeded |
| Tier classifier (deterministic) | ✅ pure-function + tested |
| ETF/index universe loader | ✅ offline parser tested; network fetch ready |
| yfinance industry loader | ✅ tested with mocked yfinance; needs live run |
| Conglomerate multi-tag overrides | ✅ 19 stocks, weights validated |
| `/universe` API endpoint | ✅ smoke-tested via TestClient |
| Audit / point-in-time / data integrity | ✅ all green |
| Total tests | ✅ 107 passing, 0 failures |

Week 1 deliverable from the plan ("all 4,800 stocks tagged with sector + industry + tier") is **code-complete; pending one network refresh of the live caches** that requires user intervention.
