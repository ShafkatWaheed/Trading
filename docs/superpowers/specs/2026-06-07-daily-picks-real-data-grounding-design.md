# Daily Picks — Real-Data Grounding Design Spec

**Date:** 2026-06-07
**Status:** Approved (pending spec review)

## Problem

The Daily Picks page is empty. Root cause (diagnosed, evidence captured): each of the 8 agents is asked to *"Pick exactly 5 stocks to BUY today"* with only a tiny macro snapshot and **no real stock data**. The `claude` CLI, reading CLAUDE.md's "NEVER fabricate market data" rule, **correctly refuses** and returns prose, not JSON. `ask_claude_json` then returns `None` → `_run_one_agent` yields `picks=[]` with `error=None` → all 8 agents empty → consensus/contrarians/option_plans all empty. The empty payload is then cached ~12h, so it persists.

The module's own docstring already says it *should* use "the brief pipeline narrowed to that agent's lens" — but the implementation never does. This spec closes that gap with a **separate, daily-picks-only** grounding pipeline.

## Goal

Make each agent **discover real candidates through its own lens** (per-agent discovery), then run **one Claude synthesis pass** that ranks them, computes consensus/contrarians, and writes grounded rationale. Agents never fabricate (they screen real data); Claude only ranks/explains real candidates, so it won't refuse. The existing payload shape is preserved so the frontend and the already-shipped `option_plans` enrichment keep working.

## Hard Constraints

- **Daily-picks only. The brief pipeline (`brief_service.py`) is NOT imported, called, or modified.** Candidate data comes from `discover_service` + `DataGateway`, which are separate from brief.
- **Real data only (CLAUDE.md).** Every candidate derives from real prices/fundamentals/flows or is omitted. The synthesis LLM call ranks/explains real candidates — it is never asked to invent tickers. No synthetic fallback.
- **No regression to the option_plans feature** (already on `main`): the payload keeps `agents` / `consensus` / `contrarians`, so `enrich_symbols` still attaches plans to the now-non-empty picks.

## Non-Goals (YAGNI)

- The 2 analyst-data lenses (**Estimate-Revisions**, **Analyst-Consensus**) are a **fast follow** — they need Finnhub (`src/data/finnhub.py`) wired through the gateway first. Out of scope here.
- Agents are **deterministic real-data screens**, not LLM calls (the "intelligence" is concentrated in the single synthesis pass). No per-agent LLM.
- No changes to brief, the Discover page, or the screener internals (read-only reuse only).

## Architecture

```
get_daily_picks()                              [daily_picks_service.py — MODIFY]
  ├─ market context (existing _market_ctx, read-only)
  ├─ candidate signals: discover_service.get_opportunities(...)  (real, wide, cached)
  ├─ per-agent discovery (parallel, deterministic)   [daily_picks_agents.py — NEW]
  │     each lens screens real data → top-N picks + evidence + conviction
  ├─ synthesis (ONE ask_claude_json call)            [daily_picks_synthesis.py — NEW]
  │     input: all agents' picks + evidence + market ctx
  │     output: ranked consensus + contrarians + per-pick rationale
  │     └─ fallback: compute_consensus_and_contrarian (existing, deterministic)
  └─ payload (agents/consensus/contrarians + rationale) → option_plans enrichment (existing)
```

Layering: per-agent discovery and synthesis fetch data / call the LLM, so they live in the **service layer** (`api/services/`), consistent with `discover_service`/`daily_picks_service`. Pure scoring helpers live in `src/analysis/` (pure, unit-tested).

## Components

### 1. `src/analysis/daily_picks_scoring.py` (NEW, pure)
Small pure helpers, no I/O:
- `conviction_from_score(score: float) -> str` — map a 0–100 opportunity score (or normalized signal strength) to `"high"|"med"|"low"` via fixed thresholds.
- `rank_candidates(cands: list[dict], key: str, top_n: int) -> list[dict]` — stable sort + truncate.
Pure functions → easy deterministic tests.

### 2. `api/services/daily_picks_agents.py` (NEW, service layer)
A lens registry. Each lens is a deterministic function:

```python
def discover(agent_key, *, opportunities, gateway) -> list[dict]:
    # returns up to _PICKS_PER_AGENT dicts:
    #   {"symbol", "evidence": {...real signals...}, "conviction": "high|med|low"}
```

`opportunities` is the shared real-data signal set from `discover_service.get_opportunities` (each card has `symbol`, `score`, `strategy`, real metrics). Each agent **independently selects its own candidates** by its lens; lenses needing data not in the opportunity cards query the gateway directly:

| Agent (key) | Lens discovery (real data) |
|---|---|
| Momentum Trader (`momentum`) | opportunity cards with strategy ∈ {Momentum, Breakout, Golden Cross, Volume Spike, Gap Fill}, ranked by score |
| Value Investor (`value`) | candidates filtered by real fundamentals (low P/E & PEG, positive margin) via `gateway.get_fundamentals` over the opportunity universe |
| Contrarian (`contrarian`) | strategy ∈ {Oversold Bounce, Mean Reversion, Support Bounce} |
| Macro Strategist (`macro`) | strategy ∈ {Sector Leader} aligned with the macro regime from `_market_ctx` |
| Disruption Hunter (`disruption`) | opportunity symbols intersected with disruption-theme beneficiary tickers (`gateway` themes) |
| Insider Shadow (`insider`) | strategy = Insider Accumulation, confirmed via `gateway.get_insider_summary` (cluster buys) |
| Options Whisperer (`options`) | `gateway.get_options_summary` over candidates → bullish put/call + unusual activity |
| Flow Tracker (`flow`) | strategy = Congress Buying and/or `gateway.get_institutional_summary` net 13F accumulation |

Each agent returns up to 5 picks with the **evidence** that justifies them. Every agent call is individually try/excepted — one failing lens contributes empty picks, never crashes the run. Agent keys/names come from the existing `AGENT_PERSONALITIES` (unchanged) so the frontend columns are stable.

### 3. `api/services/daily_picks_synthesis.py` (NEW, service layer)
```python
def synthesize(agent_results, market_ctx) -> dict:
    # returns {"consensus": [...], "contrarians": [...]}
```
- Builds a prompt containing each agent's picks **with their real evidence** + the market context, and asks Claude (via `ask_claude_json`, model `haiku`/`sonnet`) to: dedupe, rank, identify consensus (symbols multiple agents independently surfaced) and per-agent contrarians, and write a 1–2 sentence **rationale per pick citing the real evidence**. Output JSON validated.
- **Deterministic fallback:** if `ask_claude_json` returns `None`/unparseable, call the existing `src.analysis.daily_picks_consensus.compute_consensus_and_contrarian(agent_results)` (already in the codebase) and attach a templated rationale. This guarantees the page is **never empty when candidates exist**, regardless of LLM behavior.

Because the LLM is handed real candidates + evidence and asked only to rank/explain, it does not hit the "refuse to fabricate" path that broke the cold prompt.

### 4. `api/services/daily_picks_service.py` (MODIFY)
- Replace the cold-prompt path (`_build_agent_prompt` + the `ask_claude_json` "pick 5" call inside `_run_one_agent`) with: fetch `discover_service.get_opportunities`, run `daily_picks_agents.discover` for each agent in the existing `ThreadPoolExecutor`, then `daily_picks_synthesis.synthesize`.
- Keep `agent_results` shape (`{agent_key, agent_name, risk_tolerance, picks, error}`) so consensus + the option_plans symbol-collection still work.
- Payload keeps `agents` / `consensus` / `contrarians`; add `rationale` carried on each pick (or a top-level `rationale` map). `option_plans` enrichment (already shipped) runs unchanged.
- **Cache fix:** only `cache_set` when the payload has at least one pick (`consensus` or any agent picks non-empty). An all-empty run is not cached, so a transient failure can't stick for ~12h. Keep the 8h TTL for successful runs.
- Remove `_build_agent_prompt` (dead after this change) — it is the fabrication-inducing prompt and should not linger.

## Data Flow / Error Handling

- `discover_service.get_opportunities` failure → empty opportunity set → agents return empty → synthesis fallback returns empty → payload empty → **not cached** (retries next request). Logged via `log_api_call`.
- Per-agent exception → that agent's `error` set, `picks=[]`; others proceed.
- Synthesis LLM failure → deterministic consensus fallback (non-empty if any agent picked).
- No fabricated symbols/prices anywhere; evidence is real or the candidate is dropped.

## Output Shape (unchanged + rationale)

```jsonc
{
  "generated_at": "...", "as_of_date": "...", "market_context": {...},
  "agents": [{ "agent_key","agent_name","risk_tolerance",
               "picks":[{"symbol","rationale","conviction","evidence":{...}}],
               "error": null }],
  "consensus":  [{ "symbol","agent_count","agents":[...],"rationale":"..." }],
  "contrarians":[{ "agent_key","agent_name","symbol","rationale","conviction" }],
  "option_plans": { "AAPL": {...} },   // attached by existing enrichment
  "from_cache": false
}
```

Frontend already renders `agents`/`consensus`/`contrarians`; `rationale` and `evidence` are additive (optional in TS types) and can be surfaced incrementally.

## Testing (temp DB, injected fakes, no network/LLM)

1. **`tests/test_daily_picks_scoring.py`** — pure: conviction thresholds, ranking/truncation.
2. **`tests/test_daily_picks_agents.py`** — inject a fake gateway + a synthetic `opportunities` list (synthetic symbols `SYN_*` with strategy tags + metrics); assert each lens selects the right candidates with evidence; assert a gateway error in one lens yields empty for that lens only.
3. **`tests/test_daily_picks_synthesis.py`** — inject `ask_claude_json`: (a) returns valid JSON → parsed consensus/contrarians + rationale; (b) returns `None` → deterministic fallback via `compute_consensus_and_contrarian` produces non-empty output from non-empty agent picks.
4. **`tests/test_daily_picks_service.py` (extend)** — monkeypatch discover + agents + synthesis; assert payload non-empty, shape intact, `option_plans` collection still runs, and **empty payload is not cached** (cache row absent after an all-empty run).

## Out of Scope / Follow-ups

- Estimate-Revisions + Analyst-Consensus agents (need Finnhub→gateway wiring).
- Surfacing `evidence`/`rationale` richly in the frontend (additive; can follow).
- Any change to brief, Discover, or screener internals.
