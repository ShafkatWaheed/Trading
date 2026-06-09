# Daily Picks — Re-point Insider/Flow/Macro Agents to Real Data

**Date:** 2026-06-09
**Status:** Approved (pending spec review)

## Problem

The Insider, Flow, and Macro daily-picks agents select candidates by discover
**strategy tags** (`Insider Accumulation`, `Congress Buying`, `Sector Leader`,
`Dividend Play`) that the technical-only nightly scoring **never produces** — so
those three agents always return 0 picks. (The Options agent was just fixed via
the yfinance summary fallback.)

## Goal

Re-point the three agents to derive candidates from **real data sources** that
exist and are populated, intersecting each signal with the scored opportunity
pool (so picks keep their technical entry/stop/target levels + score for ranking).
Verified data availability: `congress_trades` (999 rows, 375 buys/180d),
`institution_holdings` (9,267 rows, 729 symbols), `stock_industry` (2,940),
`get_sector_tape()` (6 inflow sectors).

## Non-Goals (YAGNI)

- No change to momentum/contrarian/disruption/value/options agents.
- No new `form4_trades` bulk loader (insider uses the cached per-symbol gateway
  path — path (i); a bulk table is a future upgrade).
- No change to the scoring pipeline (`compute_opportunity` / `refresh_scores`).
- True 13F period-over-period "accumulation" deltas are out of scope; the flow
  agent uses institutional **breadth** as the 13F signal (see below).

## Architecture

In `api/services/daily_picks_agents.py`, route `insider`/`flow`/`macro` to new
data-backed selectors instead of `_strategy_select`. Each returns up to
`_PICKS_PER_AGENT` (5) picks drawn from the passed `opportunities` list (so each
pick carries the card's real technical levels), ranked by `score`, with
`conviction = conviction_from_score(card score)` and lens-specific `evidence`.
All per-symbol failures degrade to skip (never fabricate). No brief import.

### Flow agent — `_flow_select(opportunities)` (bulk DB, cheapest)
Two cheap aggregate queries (indexed), unioned, intersected with the pool:
- **Congressional buying:**
  `SELECT ticker FROM congress_trades WHERE transaction_type='buy' AND transaction_date >= date('now','-180 day') GROUP BY ticker HAVING COUNT(*) >= 2`
- **Institutional breadth (13F):**
  `SELECT symbol FROM institution_holdings GROUP BY symbol HAVING COUNT(DISTINCT cik) >= 5`
- Candidates = opportunities whose symbol ∈ (congress_buys ∪ inst_breadth).
  Evidence: `{congress_buys: n|None, institutions: k|None}`. Top-5 by score.
- (Wrapped in try/except → `[]` on DB error.)

### Macro agent — `_macro_select(opportunities, gateway)`
- `smart_money_service.get_sector_tape()` (cached 6h) → set of sectors with
  `direction == "inflow"`.
- Candidates = opportunities whose card `sector` is an inflow sector, **plus**
  dividend plays: among the top `_SHORTLIST` (15) by score, those with
  `gateway.get_fundamentals(sym).dividend_yield >= 3.0` (cached). Dedup, top-5.
  Evidence: `{sector, sector_inflow: bool, dividend_yield: float|None}`.
- **Sector-name match:** the card `sector` (from fundamentals) and the
  sector-tape sector names are both yfinance-style (e.g. "Technology",
  "Healthcare"); compare case-insensitively. If a future mismatch appears, the
  agent simply finds fewer matches (degrades, no crash).

### Insider agent — `_insider_select(opportunities, gateway)` (path (i))
- For the top `_INSIDER_SHORTLIST` (15) opportunities by score:
  `gateway.get_insider_summary(sym, days=90)` (cached 24h). Keep if
  `cluster_buy` **or** `signal in {"buy","strong buy"}` **or** `total_buys >= 3`.
  Evidence: `{signal, cluster_buy, total_buys, net_shares}`. Top-5 by score.
- Bounded to ≤15 SEC calls/run (cached 24h); per-symbol error → skip.

## Data Flow / Error Handling

- Each selector is independently try/excepted (consistent with `discover_for_agent`'s
  per-agent isolation) — a failing data source yields `[]` for that agent only.
- All candidates come from real DB rows / SEC / fundamentals; no fabrication.
- Cost per regen: Flow = 2 indexed DB queries (~ms); Macro = 1 cached sector-tape
  + ≤15 cached fundamentals; Insider = ≤15 SEC calls (cached 24h). Bounded.

## Components / Files

- **Modify:** `api/services/daily_picks_agents.py` — add `_flow_select`,
  `_macro_select`, `_insider_select`; route `flow`/`macro`/`insider` to them in
  `discover_for_agent`; remove the `insider`, `flow`, and `macro` keys from
  `_STRATEGY_LENSES` (they now have dedicated selectors); `momentum`,
  `contrarian`, and `disruption` stay in `_STRATEGY_LENSES` unchanged.
  Add module constants `_INSIDER_SHORTLIST = 15`, `_CONGRESS_BUY_MIN = 2`,
  `_INST_HOLDER_MIN = 5`, `_DIV_YIELD_MIN = 3.0`.
- **Reads:** `congress_trades`, `institution_holdings` (via `get_connection`);
  `smart_money_service.get_sector_tape`; `gateway.get_insider_summary` /
  `get_fundamentals`.

## Testing (temp DB, synthetic data, injected gateway, no network)

1. **Flow** (`tests/test_daily_picks_flow_agent.py`): seed synthetic
   `congress_trades` (SYN_A: 2 recent buys) + `institution_holdings`
   (SYN_B: 5 distinct CIKs); opportunity pool with SYN_A/SYN_B/SYN_C → assert
   flow selects {SYN_A, SYN_B}, not SYN_C; DB error → `[]`.
2. **Macro**: monkeypatch `smart_money_service.get_sector_tape` → inflow={"Tech"};
   fake gateway `get_fundamentals` → SYN_D dividend_yield=4.0; pool with a
   Tech-sector card + SYN_D → assert macro selects the Tech card + SYN_D (dividend).
3. **Insider**: fake gateway `get_insider_summary` returns cluster_buy=True for
   SYN_E, neutral for others → assert insider selects SYN_E; a gateway exception
   for one symbol → that symbol skipped, others still evaluated.

(Per CLAUDE.md test isolation: synthetic `SYN_*` symbols, `source='test'`, temp DB.)

## Out of Scope / Follow-ups

- Bulk `form4_trades` table (insider path (ii)) — future O(1) upgrade.
- True 13F accumulation deltas (vs breadth).
- Feeding flow signals into the scoring pipeline (option C).
