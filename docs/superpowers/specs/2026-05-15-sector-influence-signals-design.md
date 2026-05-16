# Sector Influence Signals & Information — Design

**Status:** Draft, awaiting user review
**Date:** 2026-05-15
**Author:** brainstormed with Claude

---

## 1. Goal

Add 15 new external data sources to the Trading app to deepen per-stock analysis with sector-influencing context (innovation, regulatory, physical-economy, demand). Sources are split into two tracks:

- **7 scored signals** — clean, predictive, backtestable. Influence Bubble Score, Recommendation, Alerts, and Risk/Bull narratives.
- **8 information sources** — display-only context. Surface in cards and narratives but **never** feed scored systems. Looser data-quality constraints, no point-in-time backtesting.
- **4 sources dropped** — see §10.

The design respects all CLAUDE.md rules: dependency direction, data integrity (no fake/synthetic data, no lookahead bias), `Decimal` for financial values, type hints, cache-first.

---

## 2. The score-vs-inform distinction (core principle)

A **signal** is something the system *scores*. To qualify it must be:
- Predictive (literature or backtests show edge)
- Clean (well-defined event date, no silent revisions, no state-DB inconsistency)
- Point-in-time honest (publication/filing lag well-understood and modeled)
- Attributable with high confidence (CIK/UEI/known identifier — not fuzzy-matched)

An **information source** is something the system *displays*. It must be:
- Accurate (or clearly marked low-confidence)
- Dated (every fact carries an `as_of`)
- Attributable to a ticker (≥80% fuzzy match acceptable)

Information sources do NOT influence Bubble Score, Recommendation, or any backtest. They appear in cards and narratives only. A wrong fact shown to a user is visible and correctable; a wrong scored input silently poisons every downstream output.

---

## 3. The 15 sources

### 3.1 Scored signals (7)

| Source | Native ID | Publishes | Available-at lag | What it tells you |
|---|---|---|---|---|
| FDA decisions (openFDA + FDA calendar) | Sponsor name + drug | As decisions occur | 0 days | Binary catalysts (PDUFA, AdCom, CRL) for pharma/biotech |
| Gov contracts (USAspending + SAM.gov) | UEI | Daily | 3 days | Awarded contract dollars; backlog/revenue visibility for defense/IT/infra |
| ITC §337 (EDIS) | Court party names | Daily | 0 days | Patent/trade investigations that can ban imports (5–30% stock moves) |
| SEC 8-K exec turnover | CIK | As filed (≤4 biz days of event) | 0 days | CFO/exec departures, especially near earnings |
| Container shipping rates (Drewry WCI, Freightos FBX) | n/a (sector) | Weekly | 0 days | Sector-level cost/margin signal for shippers + retailers |
| EIA inventories | n/a (commodity) | Weekly (Wed 10:30 ET) | 3–5 days | Crude/NatGas/distillate moves (sector-level, energy) |
| Building permits (Census BPS) | n/a (sector) | Monthly | ~18 days | Homebuilder / lumber / appliance leading indicator (sector-level) |

### 3.2 Information sources (8)

| Source | Native ID | Publishes | What it tells you |
|---|---|---|---|
| USPTO patents (PatentsView) | Disambiguated assignee | Weekly bulk | R&D direction, top technology areas, patent quality |
| USPTO trademarks (TSDR) | Owner | Daily | Product hints, brand pipeline |
| Cass Freight Index | n/a | Monthly | Cyclical trucking demand context |
| AAR rail carloads | n/a | Weekly | Industrial/ag/coal/chemical demand context |
| Port congestion (Port of LA, MarEx) | n/a | Weekly | Supply-chain stress context |
| LDA lobbying spend | Registrant/client | Quarterly + 45d lag | Regulatory exposure intensity context |
| USTR / Federal Register tariff actions | Free text + HTS codes | Daily | Trade-policy exposure context |
| USDA NASS + NOAA weather | n/a (commodity/geo) | Monthly / daily | Agriculture and weather-sensitive sector context |

### 3.3 Dropped (not in this spec)

| Source | Reason |
|---|---|
| FCC ID grants | Narrow (~2–3 relevant tickers/year), fragile data quality |
| Google Trends | Google silently revises history → data-integrity risk for any scoring use; noisy |
| DOL WARN (state DBs) | State-by-state publication inconsistency makes uniform lag modeling unreliable; revisit as v2 with manual curation |
| App downloads (SimilarWeb / Sensor Tower) | Paid-only data; user has no plan |
| AIS vessel tracking | Free realtime stream is useful but historical data is paid; defer until backtestable history is available |

---

## 4. Architecture

### 4.1 Layering (per CLAUDE.md)

```
src/data/<source>.py             Fetch + cache. ONLY layer hitting external APIs.
    ↓
src/analysis/sector_signals/     Pure scoring & info-extraction. No I/O.
    ├── _shared.py               Dataclasses (StockInformation, SignalReading)
    ├── <signal>.py              For each scored signal — emits SignalReading + StockInformation
    └── <info>.py                For each info source — emits StockInformation only
    ↓
api/services/                    Orchestration. New + extended services.
    ↓
api/routes/                      Endpoints. Mostly extensions to existing routes.
```

CLAUDE.md forbidden imports are respected: analysis never imports from data; data never imports from analysis; models never import from src; sentiment/screener untouched.

### 4.2 Two output dataclasses (single source of truth)

```python
# src/analysis/sector_signals/_shared.py

@dataclass(frozen=True)
class Fact:
    text: str
    as_of: str              # ISO 8601 UTC
    source: str             # 'uspto' | 'openfda' | 'usaspending' | ...
    source_url: str | None
    confidence: float       # 0.0–1.0; 1.0 = authoritative ID match

@dataclass(frozen=True)
class StockInformation:
    ticker: str
    topic: str              # 'innovation' | 'fda_pipeline' | 'gov_backlog' | 'labor_risk' | 'logistics' | ...
    headline: str           # one-line summary
    facts: list[Fact]
    narrative: str | None   # Claude-generated paragraph; None if not yet generated
    implications: list[str] # ['heavy R&D in AI', 'PDUFA July 17 binary']
    related_catalysts: list[str]  # links to known_future_events
    confidence: Literal['high', 'med', 'low']
    as_of: str              # latest fact in this set
    sources_used: list[str]

@dataclass(frozen=True)
class SignalReading:
    """Emitted ONLY by scored signals (the 7 in §3.1)."""
    ticker: str | None      # None for sector-level signals
    sector: str | None      # GICS sector for sector-level signals
    signal_name: str        # 'fda_decision' | 'gov_contract_award' | ...
    value: Decimal          # raw value (e.g. $4.2B contract, 1.5σ container rate move)
    z_score: Decimal | None # vs trailing 1y baseline
    direction: Literal['bullish', 'bearish', 'neutral']
    confidence: Literal['high', 'med', 'low']
    as_of: str              # when the underlying event is valid
    available_at: str       # when a backtest can FIRST see this (point-in-time)
    point_in_time_lag_days: int
    source: str
```

Scored signals emit **both** (one StockInformation for display, one SignalReading for math). Information sources emit **only** StockInformation.

### 4.3 New code by module

**New `src/data/` modules (12):**
- `patents_uspto.py` (patents + trademarks share an USPTO base helper)
- `itc_edis.py`
- `fda_openfda.py`
- `usaspending.py` (gov contracts; SAM.gov entity backfill folded in)
- `freight_rates.py` (Drewry WCI + Freightos FBX + Cass + AAR + Port of LA — one module, multiple endpoints)
- `census_bps.py` (building permits)
- `eia_inventories.py` (verify not duplicating existing `src/data/macro.py` first — see §11)
- `lobbying_lda.py`
- `ustr_federal_register.py`
- `usda_nass.py`
- `noaa_weather.py`
- `entity_aliases.py` (NEW — alias table loader/resolver, see §5)

**New `src/analysis/sector_signals/` modules (12):**
- `_shared.py` (dataclasses)
- `fda.py`, `govcon.py`, `itc.py`, `exec_turnover.py`, `logistics.py`, `energy_inventory.py`, `housing.py` — these 7 emit both StockInformation + SignalReading
- `innovation.py` (patents + trademarks), `lobbying.py`, `trade_policy.py`, `agriculture.py`, `weather.py` — these 5 emit StockInformation only

**Extended files:**
- `src/data/sec_edgar.py` — add 8-K Item 5.02 extraction (if not present)
- `src/data/macro.py` — verify/extend EIA coverage (see §11)
- `src/analysis/backtester.py` — wire in SignalReading point-in-time validation
- `src/analysis/edge_validator.py` — assert no signal in backtest has `available_at > decision_timestamp`

**New `api/services/` (5):**
- `innovation_service.py` → Deep Dive Innovation card
- `fda_catalysts_service.py` → Deep Dive FDA card (conditional on sector)
- `backlog_service.py` → Deep Dive Backlog card (conditional on sector)
- `goods_flow_service.py` → Market Pulse Goods Flow card
- `real_economy_service.py` → Market Pulse Real Economy card

**Extended services:**
- `bubble_score_service.py` — add SignalReading inputs from the 7 scored signals
- `risk_narrative_service.py` — accept new StockInformation inputs (top-3 by severity rule, see §7)
- `bull_narrative_service.py` — accept Innovation + Backlog StockInformation
- `alerts_service.py` — add 4 new alert types (FDA decisions, ITC §337, exec turnover, container-rate spikes)
- `catalyst_calendar_service.py` — add FDA PDUFA, EIA release schedule, USDA WASDE schedule from `known_future_events` table
- `freshness_service.py` — register all new sources

**New routes/endpoints:**
- `GET /stocks/{ticker}/innovation` — Innovation card
- `GET /stocks/{ticker}/fda-catalysts` — FDA card (404 if not pharma/biotech)
- `GET /stocks/{ticker}/backlog` — gov contract backlog (404 if not defense/IT/govtech)
- `GET /market/goods-flow` — Goods Flow card
- `GET /market/real-economy` — Real Economy card

---

## 5. Entity identity & ticker mapping

### 5.1 The alias table

New table `entity_aliases` in `trading.db`:

```sql
CREATE TABLE entity_aliases (
  ticker          TEXT NOT NULL,
  cik             TEXT,
  uei             TEXT,
  alias_type      TEXT NOT NULL CHECK (alias_type IN ('legal', 'common', 'subsidiary', 'uspto_canonical', 'sam_business_name', 'brand', 'override')),
  alias_name      TEXT NOT NULL,        -- normalized lowercased
  alias_source    TEXT NOT NULL,        -- 'sec' | 'sam' | 'uspto' | 'manual' | 'override'
  confidence      REAL NOT NULL,        -- 0.0–1.0; 1.0 for authoritative ID match
  created_at      TEXT NOT NULL,
  PRIMARY KEY (ticker, alias_type, alias_name)
);
CREATE INDEX idx_entity_aliases_name ON entity_aliases(alias_name);
CREATE INDEX idx_entity_aliases_cik ON entity_aliases(cik);
CREATE INDEX idx_entity_aliases_uei ON entity_aliases(uei);
```

Seeded from:
1. SEC EDGAR (CIK → legal name + former names — already in pipeline)
2. SAM.gov entity API (one-time + monthly refresh) → UEI + business name + DBA names
3. PatentsView `disambiguated_assignee_organization` table → USPTO canonical names with CIK cross-reference where present
4. Manual `src/data/entity_overrides.yaml` for known edge cases

### 5.2 Resolver API

```python
# src/data/entity_aliases.py

def resolve_ticker(
    name: str,
    *,
    min_confidence: float = 0.9,
    use_fuzzy: bool = True,
) -> ResolvedEntity | None:
    """
    Returns ResolvedEntity(ticker, matched_alias, confidence) or None.
    `confidence` < 0.9 returns None unless use_fuzzy=True AND it's an information source.
    Authoritative ID matches (CIK, UEI) bypass fuzzy and return confidence=1.0.
    """
```

### 5.3 Fuzzy matching rules

- Normalize: lowercase, strip `Inc|Corp|LLC|Ltd|Co|Holdings|Group`, strip punctuation, collapse whitespace
- Match with `rapidfuzz.fuzz.token_set_ratio`
- **Scored signals require ≥0.9 confidence.** Below 0.9, the signal is logged to `unmatched_candidates` and NOT scored.
- **Information sources accept ≥0.8 confidence.** Below 0.8, item is logged but not surfaced.
- Every fact and reading carries the match confidence in its `confidence` field for transparency.

### 5.4 Parent-subsidiary rollup

- 10-K Exhibit 21 (list of subsidiaries) parsed via existing `src/data/sec_10k_extractor.py` (extend if needed) seeds `alias_type='subsidiary'` rows pointing at parent ticker
- A patent assigned to "Beats Electronics LLC" rolls up to AAPL
- Cross-listed and dual-class structures (BRK.A/BRK.B, GOOG/GOOGL) get manual overrides

---

## 6. Caching, freshness, and rate limits

### 6.1 Per-source TTLs

| Source | Native cadence | Cache TTL | Background refresh | Rate-limit notes |
|---|---|---|---|---|
| USPTO patents | Weekly bulk | 7d | Weekly Sun | Bulk download, no limit |
| USPTO trademarks | Daily | 24h | Daily | Reasonable |
| ITC EDIS | Daily | 6h | Twice daily | Reasonable |
| FDA openFDA | Daily | 24h | Daily | 240 req/min unauth |
| USAspending / SAM.gov | Weekly contracts, monthly entity | 24h / 7d | Daily | 1000 req/day |
| Drewry WCI | Weekly (Thu) | 7d | Friday | Scrape |
| Freightos FBX | Daily | 24h | Daily | Free public |
| Cass Freight | Monthly | 7d | Day after release | Scrape |
| AAR rail | Weekly (Wed) | 7d | Thursday | Scrape |
| Port congestion | Weekly | 24h | Daily | Scrape |
| Census BPS | Monthly (~18th) | 7d | Day after release | Free API |
| EIA inventories | Weekly (Wed 10:30 ET) | 24h | Wed 11:00 ET | 5000 req/hour |
| USDA NASS | Monthly | 7d | Day after release | None |
| NOAA weather | Daily | 6h | 4× daily | Free |
| LDA lobbying | Quarterly | 7d | Weekly | Reasonable |
| USTR / Federal Register | Daily | 24h | Daily | 1000 req/hour |
| SEC 8-K | As filed | 1h (recent) / 24h (historical) | Hourly | Existing pipeline |

### 6.2 Cache implementation

- One SQLite table per source under `trading.db` following existing pattern in `stock_db.py`
- Standard columns: `key`, `payload_json`, `fetched_at`, `expires_at`, `source`, `http_status`
- **Empty-payload pitfall (per memory):** if a fetch returns 0 records, store with `expires_at = fetched_at + 1h` (short TTL) instead of full TTL. Applied globally to all 15 sources.
- All writes go through `src/data/<source>.py`; analysis layer never reads/writes cache directly
- All new endpoints support `?refresh=1` force-refresh, returning `RefreshableResponse` envelope (existing pattern)

### 6.3 Rate-limit safety

- `src/data/gateway.py` extended with per-source token buckets
- Exceeding 80% of budget logs to existing `/data-sources/rate-limits` admin route
- Failed calls logged to `api_failures` table (existing); retried with exponential backoff (max 3, per CLAUDE.md)

### 6.4 Scheduler integration

- `src/scheduler.py` gets one background job per source on its native cadence (no per-request fetching for slow signals)
- `freshness_service.py` registers all 15 sources so `/freshness` admin page tracks staleness uniformly

---

## 7. Risk-narrative prioritization rule

Risk narrative now receives up to 8 StockInformation enrichment inputs per ticker (lobbying, tariff, exec turnover, ITC, weather, USDA, port congestion, …). Without ordering it becomes noisy.

**Rule:** rank candidate enrichments by severity score; surface top-3 in the narrative; log the others.

Severity scoring:
- ITC §337 filing, FDA CRL, executive departure within 30 days of earnings, strike: **high**
- Lobbying intensity outlier, tariff action affecting >10% revenue, EIA inventory shock: **medium**
- Routine context (patent count, AAR cyclical position): **low**

Severity computed in each analysis module; surfaced via a `severity` field on StockInformation. `risk_narrative_service.py` sorts and trims.

---

## 8. Point-in-time integrity

CLAUDE.md "NEVER Look at Future Data" is hard-line. The 7 scored signals each carry `as_of` AND `available_at`. Backtests filter on `available_at`.

### 8.1 Lag table (scored signals only)

| Signal | Event date | Available-at lag | Notes |
|---|---|---|---|
| FDA decisions | Decision date | 0 days | Same-day public. PDUFA dates known in advance live in `known_future_events`. |
| Gov contracts | Award date | 3 days | USAspending typically publishes within 1–3 days; use 3 as conservative. |
| ITC §337 | Filing date | 0 days | EDIS docket real-time. |
| Exec turnover | 8-K filing date | 0 days | Must file within 4 biz days of event; use filing date as available-at. |
| Container rates | Index date | 0 days | Same-day publication. |
| EIA inventories | Survey week-end | 5 days | Wed 10:30 ET publication of prior-week data. |
| Building permits | Survey month-end | 18 days | Around 18th of following month. |

### 8.2 Information sources — explicit non-application

Information-source emissions carry `as_of` only (no `available_at`). They never enter backtests. Tests assert that `SignalReading` is never produced by information modules.

### 8.3 Forward-looking catalysts

New table `known_future_events`:

```sql
CREATE TABLE known_future_events (
  event_id        TEXT PRIMARY KEY,
  ticker          TEXT,           -- nullable (macro events apply to sectors)
  event_type      TEXT NOT NULL,  -- 'pdufa' | 'fda_adcom' | 'eia_release' | 'usda_wasde' | 'ustr_hearing' | 'cpi_release' | 'fomc' | ...
  event_date      TEXT NOT NULL,  -- ISO 8601
  source          TEXT NOT NULL,
  source_url      TEXT,
  details_json    TEXT,
  added_at        TEXT NOT NULL
);
CREATE INDEX idx_known_future_events_date ON known_future_events(event_date);
CREATE INDEX idx_known_future_events_ticker ON known_future_events(ticker);
```

Used by `catalyst_calendar_service.py` for the existing calendar UI. Signal scoring can use `days_until_event` as a feature without lookahead (the date itself is known today).

### 8.4 Backtest validator extension

`src/analysis/edge_validator.py` adds:

```python
def assert_no_lookahead(readings: list[SignalReading], decision_timestamp: str) -> None:
    """
    Raises LookaheadViolation if any reading has available_at > decision_timestamp.
    """
```

`src/analysis/backtester.py` calls this on every decision step. Fail-loud, not warn-soft.

---

## 9. Surfacing summary

### 9.1 New cards (5)

| Card | Page | Conditional? |
|---|---|---|
| Innovation (patents + trademarks) | Deep Dive | If ticker has any USPTO filings in last 5y |
| FDA Catalysts | Deep Dive | If ticker's industry (per existing `src/data/industry_loader.py`) maps to pharma, biotech, or medical devices |
| Backlog (gov contracts) | Deep Dive | If ticker has UEI matched to ≥$10M lifetime awards |
| Goods Flow (container rates + Cass + AAR + ports) | Market Pulse | Always |
| Real Economy (EIA + building permits + USDA + weather) | Market Pulse | Always |

### 9.2 Narrative enrichments (no new card)

Risk narrative gains inputs: ITC, exec turnover, lobbying, tariff/USTR, USDA, NOAA weather, port congestion (the top-3 rule applies).
Bull narrative gains inputs: Innovation, Backlog (when relevant).

### 9.3 Alerts (new types)

- FDA decision / PDUFA imminent
- ITC §337 filing or determination
- Executive (especially CFO) departure within 30 days of earnings
- Container-rate spike (>2σ in 4-week window)

### 9.4 Bubble Score inputs (scored signals only)

Added to `src/analysis/sector_signals/bubble_inputs.py` with explicit weight table:
- FDA imminent catalyst: weight ±W_fda (boost/penalty depending on prior probability)
- Gov contract YoY backlog growth: weight ±W_govcon
- ITC §337 active: weight −W_itc
- Exec turnover near earnings: weight −W_exec
- Container-rate stress (for sector-tagged tickers): weight ±W_container
- EIA inventory shock (energy sector): weight ±W_eia
- Building permits trend (homebuilder/lumber/appliance sectors): weight ±W_permits

Default weights documented in the module. All scored signals must have a default weight before merge; weight = 0 means "track but don't influence" (testing mode). **Initial weight values are picked during Wave 2 implementation, calibrated against existing Bubble Score components so no single new signal dominates.**

---

## 10. Out of scope / explicitly dropped

See §3.3 for the complete list (FCC ID, Google Trends, DOL WARN, App downloads, AIS). All five will be revisited in a future "Sector Influence Phase 2" spec if Phase 1 proves out.

---

## 11. Verifications resolved during Wave 1

| Item | Outcome | Where addressed |
|---|---|---|
| EIA coverage in `src/data/macro.py` | NOT present | Build new `src/data/eia_inventories.py` in Wave 3 |
| 8-K Item 5.02 extraction in `src/data/sec_edgar.py` | NOT present | Add in Wave 2 (exec turnover signal) |
| 10-K Exhibit 21 parsing | Added in Wave 1 | `src/data/sec_10k_extractor.py::parse_exhibit_21_subsidiaries` |
| `RefreshableResponse` shape | Open | Verify as first task of Wave 2 plan |
| Pre-existing `src/utils/rate_limit.py` | Present (sliding-window `RateLimiter` per-provider) | Wave 1 Task F4 (per-source token bucket) DEFERRED — existing module covers the use case; Wave 2 fetchers can call `RateLimiter.acquire()` directly. Wave 2 may add the new sources to `_API_SPECS` for visibility in the rate-limit admin route. |

---

## 12. Implementation phasing

### Wave 1 — Foundation (no user-visible change)
- `entity_aliases` table + SAM.gov UEI backfill + PatentsView assignee canonicalization + manual override file
- `StockInformation` + `SignalReading` dataclasses in `_shared.py`
- `src/data/gateway.py` per-source token buckets
- `freshness_service.py` extended to register all 15 sources
- `edge_validator.py` lookahead assertion
- `known_future_events` table
- 10-K Exhibit 21 subsidiary rollup verified/extended
- Unit tests for fuzzy matching threshold + alias rollup

### Wave 2 — High-edge catalysts (6 new cards + alerts) — PURELY ADDITIVE

**Design principle (revised 2026-05-15):** Wave 2 is purely additive. Existing
Deep Dive cards (verdict, bubble score, bull/risk narratives, smart money,
peer valuation, catalyst calendar, news feed) and existing scoring services
are NEVER modified. Wave 2 only appends new card sections on Deep Dive.
- USPTO patents + trademarks → **Innovation card** (Deep Dive, conditional)
- openFDA + FDA calendar → **FDA Catalysts card** (Deep Dive, conditional)
- USAspending + SAM.gov → **Backlog card** (Deep Dive, conditional)
- ITC EDIS → **Litigation card** (Deep Dive, conditional on active investigations) — flipped from "Risk narrative enrichment" to honor additive principle
- SEC 8-K Item 5.02 → **Executive Changes card** (Deep Dive, always visible if any) — flipped from "Risk narrative enrichment"
- `entity_match_decisions` table + `/stocks/{t}/entity-matches` → **Entity Match Debug card** (Deep Dive, always visible). Shows for each Wave 2+ source: what name was matched, method (exact CIK/UEI vs fuzzy), confidence, alternatives considered, why this match was chosen. Designed to make the entity-resolution layer auditable.
- Alerts page gets new types: FDA decision/PDUFA imminent, ITC §337 filing/determination, exec departure, container-rate spike. Alerts are an existing list-append surface, NOT a modification.
- **Bubble Score integration DEFERRED to a later wave.** Adding new factors changes existing scoring behavior, which violates the additive principle. The new SignalReadings are emitted and stored but do not yet affect any displayed score.

### Wave 3 — Physical economy (2 new Market Pulse cards)
- Drewry WCI, Freightos FBX, Cass, AAR, Port of LA → Goods Flow card
- Census BPS, EIA inventories (verify §11.1 first), USDA NASS, NOAA weather → Real Economy card
- Bubble Score integration for container rates, EIA, building permits

### Wave 4 — Narrative enrichments (no new cards)
- LDA lobbying → Risk narrative bullets
- USTR Federal Register → Risk narrative bullets
- Risk-narrative top-3-by-severity prioritization rule live

Each wave ships independently after Wave 1. A user could stop after Wave 2 with ~80% of total value.

---

## 13. Success criteria

- 7 scored signals emit `SignalReading` with valid `available_at`; backtester rejects any reading violating point-in-time.
- 8 information sources emit `StockInformation` only; tests assert `SignalReading` is never produced from these modules.
- Entity alias coverage: ≥95% of S&P 500 tickers have ≥1 non-CIK alias (UEI or USPTO canonical) after Wave 1 seeding.
- Fuzzy false-positive rate: manual spot-check of 50 sampled scored attributions shows ≥98% correct ticker assignment.
- Bubble Score weights documented in one file; changing a weight requires no code changes elsewhere.
- All 15 sources visible on `/data-sources/rate-limits` admin page with current status.
- Cache hit rates ≥80% during normal operation (no per-request external fetches for slow signals).
- Empty-payload short TTL (1h) verified by unit test for each source.

---

## 14. Non-goals

- AIS vessel tracking (deferred Phase 2)
- Composite "Sector Influence Score" — explicitly rejected. Composites hide which signal is firing and degrade alpha; surface signals separately.
- Order execution, broker integration, real money flow — out of project scope per CLAUDE.md.

---

## Wave 1 completion log

Wave 1 (Foundation) shipped on branch `feat/sector-influence-wave-1`. 

**Delivered:** Three new SQLite tables (`entity_aliases`, `source_freshness`, `known_future_events`), shared dataclasses (`Fact`, `StockInformation`, `SignalReading`), entity-alias resolver with exact-match + fuzzy (≥0.9 scored / ≥0.8 information), manual override YAML seeder, SEC EDGAR alias seeder, 10-K Exhibit 21 subsidiary parser, parent→subsidiary alias seeder, point-in-time lookahead validator wired into the backtester, per-source freshness registry (18 endpoints), and admin-facing `get_sources_status()` service.

**Tests:** 60+ new unit/integration tests across `tests/test_entity_aliases_*.py`, `tests/test_sector_signals_shared.py`, `tests/test_source_freshness*.py`, `tests/test_known_future_events_schema.py`, `tests/test_lookahead_assertion.py`, `tests/test_backtester_lookahead_integration.py`, `tests/test_sec_10k_exhibit21.py`, `tests/test_freshness_service_sources.py`, `tests/test_wave1_smoke.py`.

**Deferred to Wave 2:**
- SAM.gov entity-API seeder (needs gov-contracts fetcher to be useful)
- PatentsView assignee canonicalization (needs patents fetcher to be useful)
- Wave 1 plan's Task F4 (per-source token bucket) — existing `src/utils/rate_limit.py` covers the use case
- `/freshness` route extension to surface `get_sources_status()` (service exists; route wiring deferred until Wave 2 admin UI work)
- Replacing existing macro / commodity / news / smart-money / options-flow pipelines — these stay as-is.
