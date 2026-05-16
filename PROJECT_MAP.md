# Trading — Project Map

A bird's-eye view of the codebase so Claude (or any new contributor) can navigate quickly.
Read this **after** CLAUDE.md (which has the strict architecture/coding rules).

---

## Three runtimes

| | Where | How to run | Logs |
|---|---|---|---|
| **Backend** (FastAPI) | `api/` | `uvicorn api.main:app --port 8000 --reload` | `/tmp/uvicorn.log` |
| **Frontend** (Next.js 14) | `frontend/` | `cd frontend && npm run dev` (port 3000) | `/tmp/next.log` |
| **Scheduler / agent** (Python) | `src/scheduler.py`, `src/agent.py` | Started by Streamlit dashboard *(legacy, deprecated)* | — |

The Streamlit `dashboard.py` is **gone**. The Next.js frontend is the primary UI.

---

## Frontend — the five user-facing pages

```
/                       Market Pulse           — macro context, today's takeaway, sectors, news
/discover               Discover               — rank/filter/screen ranked opportunities
/deep-dive/<TICKER>     Deep Dive              — per-stock analysis (verdict + bull/bear + flows + plan)
/deep-dive/compare      Compare Stocks         — side-by-side comparison of N stocks
/prove-it               Prove It               — signal backtester + AI analyst
/agent                  AI Agent               — autonomous trading dashboard
/alerts                 Alerts                 — flagged events
+ /universe /news-impact /edge-freshness /data-sources  — admin / advanced
```

### Page anatomy — each page is composed from:
- `app/<page>/page.tsx`                       — page-level state + layout
- `components/<area>/*.tsx`                   — one component per card
- `lib/hooks/use-<page>.ts`                   — react-query hook
- `lib/api/endpoints.ts` (`xApi.method()`)    — typed HTTP client
- `lib/api/types.ts`                          — shared TS types

### Visual hierarchy (all pages)
- **Hero** — `card` + colored `border-l-4` — verdicts, TLDR, recommendations
- **Analysis** — `.card-subtle` — peer, analyst, news, calendar
- **Reference** — `.card-muted` — earnings tables, paste tools

Defined in `frontend/app/globals.css`.

### Section headers
`<SectionHeader index={1} label="Snapshot" subtitle="…" id="snapshot" />` for numbered, anchored sections. Used on Deep Dive, Market, and Discover.

---

## Backend — `api/` layout

```
api/
├── main.py                # FastAPI app + CORS
├── schemas.py             # ALL Pydantic types (single big file)
├── constants.py           # PERIOD_DAYS etc.
├── routes/
│   ├── stocks.py          # /stocks/* — deep-dive, search, bubble-score, narratives, ...
│   ├── market.py          # /market/* — pulse, dashboard, takeaway, news, calendar
│   ├── discover.py        # /discover — ranked opportunities
│   ├── backtest.py        # /backtest/* — signal accuracy, portfolio sim, AI analyst
│   ├── compare.py         # /compare
│   ├── agent.py           # /agent/*
│   ├── watchlist.py       # /watchlist
│   ├── alerts.py          # /alerts
│   ├── earnings.py        # /earnings/explain
│   ├── simulation.py      # /simulation/* — walk-forward replay
│   ├── universe.py        # /universe — stock universe
│   ├── news_impact.py     # /news-impact
│   ├── graph.py           # /graph — relationship graph
│   ├── freshness.py       # /freshness — data freshness queue
│   └── data_sources.py    # /data-sources/rate-limits
└── services/              # ⬇ The orchestrator layer — see below
```

### Service catalog (where each major piece of logic lives)

| Service | Provides | Notes |
|---|---|---|
| `market_service.py` | `/market/pulse` — regime, KPIs, yield curve, sector flows, trading implications | Sector rotation deltas computed here |
| `market_dashboard_service.py` | `/market/dashboard` — live indices + breadth + top movers | Sparklines, market-status pill |
| `market_takeaway_service.py` | `/market/takeaway` — 1-paragraph synthesis | Rule-based, no Claude |
| `market_news_service.py` | `/market/news` — top headlines | Tavily → Exa fallback |
| `calendar_service.py` | `/market/calendar` — FOMC, CPI, NFP, GDP + watchlist earnings | Exposes `next_event` + `next_high_impact` |
| `events_service.py` | `/market/geopolitical` | |
| `disruption_service.py` | `/market/disruption` | Claude synthesizes 6 themes with required H/M/E mix |
| `discover_service.py` | `/discover` — ranked opportunity cards | |
| `deep_dive_service.py` | `/stocks/{t}/deep-dive` — full per-stock report | Calls `analyze_stock()` from `src/` |
| `bubble_score_service.py` | `/stocks/{t}/bubble-score` — composite 0–100 + Vibes Premium | Pure rules, no Claude |
| `bull_narrative_service.py` | `/stocks/{t}/bull-narrative` | Claude-generated, 24h cache |
| `risk_narrative_service.py` | `/stocks/{t}/risk-narrative` | Claude-generated, 24h cache |
| `peer_valuation_service.py` | `/stocks/{t}/peer-valuation` | yfinance for each peer |
| `analyst_consensus_service.py` | `/stocks/{t}/analyst-consensus` | yfinance |
| `recommendation_service.py` | `/stocks/{t}/recommendation` | Synthesizes verdict × bubble × analyst × flow |
| `smart_money_service.py` | `/stocks/{t}/smart-money` | Institutional + insider + congress, three sources |
| `news_feed_service.py` | `/stocks/{t}/news-feed` | Tavily → Exa fallback, rule-based sentiment |
| `catalyst_calendar_service.py` | `/stocks/{t}/catalyst-calendar` | yfinance calendar + macro |
| `benchmarks_service.py` | `/stocks/{t}/benchmarks` | SPY + sector ETF spark for chart overlay |
| `signal_evidence_service.py` | `/stocks/{t}/signal-evidence` | Backtests each active signal on the stock |
| `earnings_explainer_service.py` | `/earnings/explain` | Claude parses pasted earnings text |
| `compare_service.py` | `/compare` | Multi-stock side-by-side |
| `backtest_service.py` | `/backtest/{all,single,multi-stock}` | Signal-level backtests |
| `portfolio_sim_service.py` | `/backtest/portfolio` | Realistic portfolio backtest with capital math |
| `portfolio_sim_agent_service.py` | `/simulation/portfolio-agent` | Walk-forward multi-agent simulation |
| `ai_analyst_service.py` | `/backtest/ai-analyst` + `/backtest/ai-analyst-multi` | AI walk-forward; single + multi-stock; single + multi-agent modes |
| `simulation_service.py` | `/simulation/runs`, `/simulation/cycles`, `/simulation/step` | Recorded simulation replay |
| `agent_service.py` | `/agent/*` | Autonomous trading agent |
| `alerts_service.py` | `/alerts/*` | |
| `watchlist_service.py` | `/watchlist/*` | |
| `freshness_service.py` | `/freshness/*` | Data freshness queue |
| `universe_service.py` | `/universe/*` | Stock universe |
| `news_impact_service.py` | `/news-impact` | News-graph propagation |
| `peer_service.py` | Peer relations | |
| `ownership_service.py` | Institutional holdings (13F) | |
| `neighborhood_service.py` | Stock similarity neighborhood | |

### How services compose with `src/`
- Services in `api/services/` are the **orchestrator** layer — allowed to import from `src/data`, `src/analysis`, etc.
- `src/analysis/` is pure computation (signals, backtester) — **never** imports from `src/data` or `api/`.
- `src/data/` is the **only** layer allowed to call external APIs — see CLAUDE.md.
- `src/utils/db.py` is the cache. Use `cache_get(key)` / `cache_set(key, value, ttl_minutes)`.

---

## Data sources — who fetches what

| Source | Wrapper | Used for | Key in .env |
|---|---|---|---|
| Yahoo Finance | `yfinance` (no auth) | Prices, fundamentals, calendar, options, dividends | — |
| Alpha Vantage | `src/data/market.py` | Macro economic data (rate-limited 5/min free) | `ALPHAVANTAGE_API_KEY` |
| SEC EDGAR | `src/data/sec_edgar.py` | Form 4 (insider) + Form 13F (institutional) | — (free) |
| Capitol Trades MCP | `src/data/congress.py` | Congressional STOCK Act disclosures | — (free) |
| Tavily | `src/data/news.py` | News search (primary, rate-limited) | `TAVILY_API_KEY` |
| Exa | `src/data/news.py` | News search fallback when Tavily limited | `EXA_API_KEY` |
| Polygon.io | (configured) | Quotes, level 2 (paid tiers) | `POLYGON_API_KEY` |
| Claude CLI | `subprocess.run(["claude", "-p", …])` | All AI features — uses your CC subscription quota | — |

---

## Claude usage pattern (THE cost-sensitive thing)

Every service that does AI work uses the **`claude` CLI subprocess**, NOT the Anthropic SDK:

```python
proc = subprocess.run(
    ["claude", "-p", prompt, "--model", "haiku", "--allowedTools", ""],
    capture_output=True, text=True, timeout=45, env=env,
)
```

Why: the user is on a **Claude Code subscription**, not an API plan. The CLI calls use their existing CC quota at **$0 incremental cost**. Switching to `anthropic` SDK would bill an API account they don't have set up. **Never migrate to the SDK without explicit permission.**

Trade-off: each CLI cold-start is ~10–15s. Parallelize up to 7 calls with `ThreadPoolExecutor`; more than that causes contention. Multi-agent AI Analyst takes ~60s/cycle as a result — accepted because it's free.

---

## Caching — three layers

1. **SQLite cache** (`src/utils/db.cache_get/set`)
   - Per-service TTLs: bubble score 6h, risk/bull narrative 24h, smart money 6h, news 30m, etc.
   - Each service that does expensive work writes here.
   - **Lesson**: only cache when payload has real data (see `market_dashboard_service` — empty payloads are NOT cached, otherwise an upstream blip pollutes the cache for the whole TTL).

2. **HTTP cache** (none) — every request hits the backend.

3. **React Query in-memory cache** (frontend)
   - `staleTime` per hook (often 5–30 min)
   - Survives page navigation; dies on hard reload
   - **Lesson**: when a component sees null/empty in cached data, auto-refetch (see `BreadthCard`)

---

## Recurring bug patterns to watch for

These have all bitten us at least once. Quick checks save hours.

### 1. `from X import Y` inside a function shadows module-level imports
```python
from src.utils.db import cache_get        # module-level
def my_func():
    cache_get(...)                         # 1
    from src.utils.db import cache_get     # 2  ⚠ makes the name LOCAL for the whole function
    ...                                    # 1 above is now an UnboundLocalError
```
Already burned us once in `compare_service.py`. When seeing `UnboundLocalError` on an imported name, check for shadowing.

### 2. Duplicate Pydantic class names in `api/schemas.py` silently shadow
We had two `PortfolioSimRequest` classes — the second one (walk-forward variant with `start_date`/`end_date`) shadowed the simple one used by `/backtest/portfolio`, causing 422 errors. The fix was to rename the second pair to `WalkForwardSimRequest`/`Response`.
When adding a class to `schemas.py`, grep for the name first.

### 3. Pydantic `response_model` validates strictly
A backend function building a dict that's missing a required field (e.g., `symbol` on a trade) **crashes at validation time** and returns 500 → frontend sees nothing after 60+ seconds of compute. When seeing 500s after long jobs, diff the response shape against the schema.

### 4. Indicator key mismatch — backtester uses no underscore
`_compute_indicators` returns keys like `sma50`, `sma200` (no underscore). Earlier code in `ai_analyst_service` requested `sma_50`/`sma_200` and silently got `None`. Always check the actual keys.

### 5. `uvicorn --reload` + long `subprocess.run` = stuck shutdown
The reloader's graceful shutdown waits for in-flight `claude` subprocess calls (which are 60–180s) to complete. New requests never get served because the worker isn't accepting. **Fix**: identify worker PID with `ps -ef | grep uvicorn`, `kill <pid>` (SIGTERM then SIGKILL if needed), then `uvicorn ... --reload &` again.

### 6. Next.js dev rewrites have a ~60–90s idle timeout
Long-running endpoints (AI Analyst multi-mode = 4+ minutes) get killed by the dev proxy with `socket hang up` / `ECONNRESET`. **Fix**: in the relevant `endpoints.ts` API method, detect localhost and fetch `http://localhost:8000/...` directly. CORS is allowed in `api/main.py` for `localhost:3000`. See `aiAnalyst` and `aiAnalystMulti` for the pattern.

---

## Cross-page navigation conventions

- Every page has a numbered section flow: `01 Snapshot → 02 Action → 03 …`
- Every ticker mentioned is a `<Link>` to `/deep-dive/<TICKER>` if relevant
- The page-level `Nav` has a global ticker search → `/deep-dive/<SYM>`
- The page-level `Nav` has a live market-status pill (open/closed/pre/after with countdown)
- Discover supports multi-select → `/deep-dive/compare?symbols=A,B,C`

---

## When in doubt

1. **Read `CLAUDE.md`** for strict architectural rules (dependency direction, what NOT to do).
2. **Search `api/services/`** to see how an existing feature is wired — most new endpoints follow the same pattern.
3. **Check for cache invalidation** when adding new computed data — TTL too long can hide bugs for hours.
4. **Test with `curl` before debugging the frontend** — separates client from server issues.
5. **Never `kill` a user process without permission.**
