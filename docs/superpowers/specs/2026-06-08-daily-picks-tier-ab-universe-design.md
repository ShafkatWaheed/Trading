# Daily Picks — Tier A+B Scoring Universe Design Spec

**Date:** 2026-06-08
**Status:** Approved (pending spec review)

## Problem

Daily-picks can only surface stocks that have a fresh row in `precomputed_scores`.
That table is populated by `refresh_scores`, which scores `_all_target_symbols()`
= watchlist (`AAPL`) + a hardcoded 69-symbol `STOCK_DB`. So daily-picks screens
**69 of the ~4,356 stocks** in `stocks_universe` — names like **MRVL (Tier B)**
are never scored and can never be picked. (Brief is unaffected — it screens the
full graph universe via `context_search_service`/`graph_relevance`, with no
dependence on the 69.)

## Goal

Score **Tier A+B of `stocks_universe` (~1,022 liquid large/mid-cap names)** nightly
so daily-picks draws its candidates from that wider, tradeable universe — without
touching the other refresh jobs, the watchlist/STOCK_DB list, or brief.

## Why Tier A+B (not all 4,356, not the 69)

- The 69 is a high-frequency **pre-warm hot set** shared by 6 jobs (prices q15m,
  news hourly, options q30m, etc.). Those cannot scale to thousands — Polygon
  (5/min), AV (1/15s), and news quotas make it infeasible. Scoring is the
  exception: one cheap `get_historical` call/symbol, daily.
- Tier A+B is the liquid/tradeable slice (includes MRVL). Tier C/D are
  micro-caps/illiquid — poor option-chain liquidity (the feature's purpose) and
  ~30+ min extra nightly with higher throttling risk for little value.
- One-off names outside A+B remain reachable via the **watchlist** (scored
  on-demand by `get_opportunities`), so nothing is lost.

## Hard Constraints

- **Do NOT change `_all_target_symbols()`** — it feeds 5 other jobs
  (`refresh_prices`, `refresh_fundamentals`, `refresh_insider`, `refresh_news`,
  `refresh_options`). Only the scoring scope changes.
- **Do NOT touch brief** (`brief_service` / `context_search_service`).
- Real data only; per-symbol failures degrade gracefully (no fabrication).

## Architecture

```
API startup scheduler (api/main.py, 5:30 ET daily)
   └── refresh_scores(symbols=_tier_ab_symbols())     [scope change]
          └── _fan_out(_one, ~1,022 syms, max_workers=4)   [existing pattern]
                 get_historical(252d) -> technical.analyze -> compute_opportunity
                 -> save_precomputed_score
   => precomputed_scores now holds ~1,022 fresh rows
   => get_opportunities returns the best-60 across 1,022
   => daily-picks agents screen that richer pool (MRVL eligible if it scores well)
```

## Components

### 1. `_tier_ab_symbols()` (NEW, `src/scheduler.py`)
```python
def _tier_ab_symbols() -> list[str]:
    """Tier A+B symbols from stocks_universe (the liquid/tradeable slice).
    Falls back to _all_target_symbols() if the table is empty/unavailable so a
    scoring run never operates on nothing."""
```
- `SELECT symbol FROM stocks_universe WHERE tier IN ('A','B') ORDER BY symbol`.
- If the query returns empty (fresh/unseeded DB) or errors → return
  `_all_target_symbols()` (safety fallback).

### 2. `refresh_scores(symbols: list[str] | None = None)` (MODIFY, `src/scheduler.py`)
- Add the optional `symbols` param. Default `None` → `_all_target_symbols()`
  (**backward-compatible**: the legacy standalone `start_scheduler` path keeps
  its current behavior).
- Body unchanged otherwise: `_fan_out(_one, symbols, max_workers=4, label="scores")`.

### 3. API scheduler (MODIFY, `api/main.py`)
- The existing 5:30 ET `_refresh_opportunity_scores` job (added earlier) changes
  its call from `refresh_scores()` to
  `refresh_scores(symbols=_tier_ab_symbols())`, importing `_tier_ab_symbols`
  alongside `refresh_scores`. Still wrapped in try/except so a scheduler error
  never breaks startup.

### 4. Unchanged
`_all_target_symbols`, the 5 non-scoring refresh jobs, `get_opportunities`
(`limit=60` stays — best-60-of-1,022 is already a large upgrade, and a bigger
limit would worsen the cold-first-call `option_plans` latency noted separately),
`STOCK_DB`, brief.

## Data Flow / Error Handling

- `_fan_out` already isolates per-symbol exceptions; a throttled/empty
  `get_historical` for a symbol is skipped (no score row written for it), not
  fatal. ~1,022 cold yfinance fetches at 4 workers ≈ 6–7 min, background thread,
  non-blocking.
- **Throttling risk (flagged):** Yahoo may throttle at this volume; failed
  symbols simply aren't scored that night and are retried next run. Concurrency
  kept at 4.
- Empty-universe fallback (Component 1) guarantees a run never scores nothing.

## Testing (temp DB, injected gateway, no network)

1. **`tests/test_tier_ab_symbols.py`** — seed a synthetic `stocks_universe`
   (rows tagged tier A/B/C/D with `source='test'`, synthetic symbols `SYN_*`);
   assert `_tier_ab_symbols()` returns only A+B, excludes C/D; with an empty
   table it falls back to `_all_target_symbols()`.
2. **`tests/test_refresh_scores_scope.py`** — call
   `refresh_scores(symbols=["SYN_A","SYN_B"])` with the historical fetch
   monkeypatched (fake OHLCV DataFrame, no network); assert `precomputed_scores`
   has rows for exactly those symbols and `_all_target_symbols` was not used.
   (Per CLAUDE.md test-isolation: synthetic symbols only, temp DB.)

## Out of Scope / Follow-ups

- Other refresh jobs (rate-limit-bound — stay on the 69).
- Tier C/D (possible future **weekly** lower-frequency scoring pass).
- The cold first-call latency (synthesis + `option_plans` Polygon chains) —
  separate follow-up (pre-warm in the nightly job).
- `get_opportunities` limit tuning.
