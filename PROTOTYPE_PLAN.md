# Knowledge-Graph Prototype — 5-Week Plan

A keyword-driven news → stocks engine over a 4,800-stock tiered universe with peer/competitor and supply-chain interconnectivity.

## Locked design decisions

1. **Universe size:** 4,800 stocks across S&P 500, Russell 1000/2000, TSX 60, TSX broad, TSXV liquid, NASDAQ Capital liquid.
2. **Tiering:** A (~150 hand) / B (~800) / C (~1,800) / D (~1,800), deterministic from market cap + index membership.
3. **News engine:** keyword-driven, not theme-classified. Headlines tokenize → keywords → industry impacts → stocks. ~150-200 hand-seeded keywords across ~15 domains (AI, oil, war, tariffs, rates, FDA, court rulings, antitrust, M&A, GLP-1, crypto, climate, mining).
4. **Hierarchy:** theme/keyword → sector → industry (yfinance taxonomy, ~150 industries) → stocks. Stock-level signal score does within-industry ranking.
5. **Supply-chain edges:** ~30 hand "spine" + LLM-mined from 10-K Item 1A/Item 7 for ~350 Tier A stocks. Item 1A only (truncated input).
6. **Peer/competitor edges:** Tier A hand-curated (~1,050 with `overlap_dimensions`) + Tier B/C/D Claude per-industry batched (~21,750). No embedding service needed.
7. **Court ruling / regulatory events:** keyword-driven via `keyword_impact` rows + `target_stock` for direct name-targeted events (FDA approves X, FTC blocks Y).
8. **LLM:** Claude via existing CLI subprocess pattern (`claude -p prompt --model haiku`). Authenticated via subscription, **no API key, no per-token billing**.
9. **Resumable jobs:** all bulk LLM operations (peer ranking, 10-K extraction) chunked into a `jobs` table that can pause/resume across subscription budget windows.

## Architecture

```
NEWS HEADLINE → tokenize + NER → keyword_impact lookup → aggregate by industry
                                                      → fan out to stocks (multi-tag, tier-aware)
                                                      → expand 1-2 hops via stock_peers + stock_relations
                                                      → composite rank: tier × industry_boost × opp_score × hop_decay × confidence
                                                      → return grouped result with "why" trace
```

## Data model — seven new tables

```sql
industries          -- ~150 yfinance industry codes + sector mapping
stocks_universe     -- 4,800 stocks with tier (extends existing STOCK_DB pattern)
stock_industry      -- M2M; supports multi-tag for conglomerates with weights
stock_peers         -- Tier A hand + Tier B/C/D Claude batched
stock_relations     -- supply chain (supplier/customer/peer/substitute/complement)
keyword_impact      -- ~200 hand-seeded keyword → industry rows with polarity + weight
keyword_groups      -- ~30 (deferred — for backtest aggregation only)
```

All tables go in the existing SQLite at `trading.db`. Migrations in `src/utils/db.py` `init_db()`.

## Five-week phase plan

### Week 1 — Universe + tiering + industry tags
- Day 1: schema migrations + Tier A hand-seed (~150 stocks)
- Day 2: deterministic tier classifier + ETF/index universe loader
- Day 3: yfinance industry pull for all 4,800 (overnight network job)
- Day 4: multi-tag ~30 conglomerates by hand
- Day 5: `GET /universe` API endpoint + tests

**End-of-week-1 acceptance:** all 4,800 stocks in DB with sector + industry + tier.

### Week 2 — Keyword engine
- Day 6: hand-seed ~150 `keyword_impact` rows across 15 domains
- Day 7: tokenizer + n-gram + NER + negation
- Day 8: aggregation engine (diminishing-returns by industry)
- Day 9: fan-out to stocks; `POST /news-impact` endpoint
- Day 10: validation against ~30 historical headlines, tune weights

**End-of-week-2 acceptance:** `POST /news-impact` returns sensible ranked stocks for prototype keyword set.

### Week 3 — Peer/competitor edges
- Day 11: Tier A hand-curate ~1,050 peer edges with `overlap_dimensions`
- Day 12: Claude-Sonnet validation pass on Tier A
- Day 13: Claude-Haiku batched per-industry peer ranking for Tier B/C/D (~150 industry batches, resumable)
- Day 14: ~50 cross-industry hand-curated peer edges for Tier A
- Day 15: `GET /graph/stock/{sym}/peers` endpoint with confidence badges

**End-of-week-3 acceptance:** "Peers of MSFT" works for any of the 4,800 stocks; confidence honestly displayed.

### Week 4 — Supply chain + regulatory + graph traversal
- Day 16: hand-seed ~30 critical supply-chain spine edges
- Day 17: Claude-Haiku 10-K Item 1A extraction for ~150 Tier A stocks (resumable; ~7-8 hours subprocess time)
- Day 18: regulatory keywords (~30 rows) for court rulings / FDA / antitrust / M&A
- Day 19: graph traversal engine (1-2 hops via supply-chain + peers); composite ranking
- Day 20: `GET /graph/stock/{sym}/neighborhood` + auto-expansion in `POST /news-impact`

**End-of-week-4 acceptance:** end-to-end news → stocks → graph fans out via peers and suppliers; court/FDA/M&A events return sensible results.

### Week 5 — UI + polish + tests
- Day 21: React `/news-impact` page (textarea, analyze button, grouped results)
- Day 22: React `/stock/[sym]/neighborhood` page (supply-chain + peer panels)
- Day 23: nav tab + design-system polish + tier color coding
- Day 24: unit tests (tokenizer, aggregator, traverse, ranking) + audit clean + point-in-time guards on edge reads
- Day 25: empty states, error handling, perf check (<500ms queries; SQLite indices)

**End-of-week-5 acceptance:** demoable end-to-end at 4,800-stock scale; UI clean; tests pass; audit green.

## Demo script (week 5 deliverable)

| Scenario | Input | Expected output |
|---|---|---|
| AI capex | "OpenAI commits $50B GPU build-out with Oracle" | NVDA, AVGO, AMD, MU, ORCL direct + supply-chain expansion to TSM/ASML + 2nd-deriv VRT/GEV/CCJ + peer fan-out |
| War/oil | "Iran fires missiles at Saudi oil refinery" | LMT/NOC/RTX defense, XOM/CVX/OXY oil, VLO/MPC refiners, DAL/UAL shorts |
| Court | "FTC blocks Capital One Discover merger" | COF/DFS direct + JPM/BAC/AXP industry-peer benefit |
| FDA | "FDA rejects LLY Alzheimer's drug" | LLY direct large negative + BIIB/BMY/GILD competitor positive |
| Peer query | Click MSFT → peers | Tier A: GOOG/AMZN/ORCL/CRM/IBM with overlap dims; Tier B/C/D LLM-batched |
| Supply chain | Click NVDA → neighborhood | Up: TSM/ASML/CDNS/SNPS; Down: MSFT/GOOG/META/TSLA; Peers: AVGO/AMD/MRVL/INTC |

## What's deferred (post-prototype)

- Embedding-based fallback for novel keywords (Voyage AI / sentence-transformers)
- Backtest validation of edge weights via historical instances
- Auto-news-ingestion (Tavily/Exa pipeline → engine)
- Real-time alerts when keywords fire above threshold
- Agent integration (the agent will not yet consume this graph)
- Force-directed graph viz (prototype uses grouped lists)
- Time-decay on stale edges (`as_of` is recorded; decay rules not applied)
- Multi-dimensional peer similarity for Tier B/C/D
- Cross-industry peer discovery for Tier B/C/D
- Caching layer (queries hit SQL fresh; sub-500ms target without it at prototype scale)

## Risk register

| Risk | Probability | Mitigation |
|---|---|---|
| yfinance rate limits during 4,800-stock industry pull | medium | run as overnight job with retries + caching |
| Tier C/D peer edges noisy (Claude-only, no review) | high | `confidence='low'` badge in UI; never auto-trade |
| Industry mis-tagging (INTC under "AI booms") | high | stock-level signal score sorts winners within industry; ~10-30 polarity overrides for known cases |
| Subscription budget caps long Claude batch runs | medium | resumable jobs table; Haiku for bulk |
| Conglomerate exposure missed | medium | hand multi-tag top 30 names; defer rest |
| Stale supply-chain edges | medium | each edge has `as_of` + `evidence` surfaced in UI |
| Composite ranking weights heuristic | high | hard-coded sensible defaults; learned weights post-prototype |

## File layout for new code

```
src/
├── data/
│   ├── stock_db.py            (existing — kept for backward compat)
│   ├── tier_a_seed.py         (NEW — hand-curated 150 names)
│   ├── industry_loader.py     (NEW — yfinance industry pull)
│   ├── tier_classifier.py     (NEW — deterministic A/B/C/D rules)
│   └── universe_loader.py     (NEW — ETF holdings + TSX/NASDAQ filters)
├── news/                       (NEW MODULE)
│   ├── __init__.py
│   ├── tokenize.py            (n-grams, NER, negation)
│   ├── aggregate.py           (diminishing-returns, polarity merge)
│   └── expand.py              (1-2 hop supply chain + peer expansion)
├── graph/                      (NEW MODULE)
│   ├── __init__.py
│   ├── traverse.py            (neighborhood queries)
│   └── rank.py                (composite scoring)
├── utils/
│   ├── claude_cli.py          (NEW — refactored from ai_analyst_service)
│   ├── db.py                  (UPDATE — new tables in init_db)
│   └── ...
api/
├── routes/
│   ├── universe.py            (NEW)
│   └── graph.py               (NEW)
└── services/
    └── news_impact_service.py (NEW)
frontend/app/
├── news-impact/page.tsx       (NEW)
└── stock/[symbol]/
    └── neighborhood/page.tsx  (NEW)
seeds/                          (NEW directory for non-Python seed data)
├── keyword_impact.csv         (~200 rows)
├── stock_relations.csv        (~30 spine edges)
└── tier_a_peers.csv           (~1,050 hand peers)
tests/
├── test_universe_schema.py    (NEW)
├── test_tier_classifier.py    (NEW)
├── test_news_tokenize.py      (NEW)
├── test_news_aggregate.py     (NEW)
└── test_graph_traverse.py     (NEW)
```

## What this session will accomplish (autonomous mode)

Realistic scope for one overnight session:
1. PROTOTYPE_PLAN.md (this file) — done
2. Week 1 Day 1 fully: schema + Tier A seed + loader + tests
3. Week 1 Day 2 partially: tier classifier rules (deterministic, offline-runnable)
4. Defer to next session: live network pulls (yfinance, ETF holdings) — code written but execution requires network

End-of-session deliverable: schema + ~150 Tier A stocks loaded + tier classifier ready, all audit/tests green.
