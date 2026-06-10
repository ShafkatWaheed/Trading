# AI Analyst — Self-Improving Daily Top-Gainer Predictor

**Date:** 2026-06-09
**Status:** Approved design (pending spec review)

## Vision

An AI stock analyst that, every trading day, predicts **10 stocks** from the
Tier A+B universe (~1,022) most likely to finish in that day's **top ~15% of
gainers** (open→close return). The analyst **reads the entire board** — every
deep-dive sidecar, market-pulse / sector flow, earnings calls, per-stock news +
live web search, options flow, congress, insider, 13F, macro, fundamentals — and
reasons to its picks. (Options flow, pre-market gap, and reddit buzz are
**live-only** — used in live trading but excluded from the backtest, since they
have no point-in-time history; see below.) It is graded daily, and its accuracy **compounds** through
a playbook (`analyst_playbook.md`) that it rewrites weekly from its own results.

It is **cold-started** by a strict point-in-time walk-forward over the **past 90
trading days**, then continues **live** on the same playbook — so the skill it
accumulates carries forward and keeps improving as real days accrue.

## Locked decisions (from brainstorming)

1. **Bootstrap honesty:** strict point-in-time — each past day uses only data
   knowable on/before that day. No lookahead (CLAUDE.md hard rule).
2. **Target:** same-day top gainer, **rank-based** — a pick is a HIT if the
   stock lands in the actual top ~15% of the universe by open→close % that day.
3. **Selection:** **two-stage Claude (no deterministic screen)** — Stage 1
   triages the universe to a ~35 shortlist; Stage 2 deep-reads full packets and
   picks the final 10. Model: **Opus** (per project preference for prediction AI).
4. **Universe:** **Tier A+B (~1,022)**.
5. **Learning cadence:** rewrite the playbook **weekly** (every ~5 trading days)
   during the bootstrap; predictions compound week over week.
6. **Coverage:** the analyst reads **everything**. Live = the full signal board.
   Bootstrap = everything reconstructable as-of-date (which is almost all of it).

## Goals

- A Claude analyst that sees the full signal board and predicts 10 daily.
- A strict-PIT 90-day walk-forward bootstrap that grades itself and writes the
  initial playbook — no lookahead, no fabrication.
- A live daily loop that continues on the same playbook and keeps learning.
- A daily **signal archive** so every future day has a complete, honest snapshot
  — future backtests read real stored history instead of reconstructing it.

## Non-Goals (YAGNI)

- No order execution / brokerage. (Research only — CLAUDE.md.)
- **No options flow / pre-market / reddit in the backtest.** These three have no
  honest point-in-time history, so using them for a past date would contaminate
  the backtest. They are **live-only**: used in live trading, excluded from the
  90-day bootstrap entirely (no faking with today's values).
- No change to the existing deterministic `5d_momentum_v1` strategy — it remains
  as the fallback ranker.
- Not replacing the Brief / Daily Picks pipelines; this is the Predictions page.

## Signal Inventory — read EVERYTHING

Two granularities per as-of date D:
- **Compact row** (all ~1,022, for Stage-1 triage): symbol, name, sector,
  momentum %, pulse/sector-flow tag, congress/insider/13F flags, earnings-soon
  flag, news-sentiment tag, valuation tag.
- **Full packet** (the ~35 shortlist, for Stage-2 deep-read): every signal below
  in full, plus web search (live) / date-filtered search (bootstrap).

| Signal source | Live | Bootstrap (as-of D) | Point-in-time method |
|---|---|---|---|
| Momentum / technicals | ✅ | ✅ | price bars sliced ≤ D (`_compute_indicators`) |
| Market pulse / sector flow / rotation | ✅ | ✅ | sector-ETF + flow, prices ≤ D |
| Macro (VIX, 10Y/5Y, S&P, regime) | ✅ | ✅ | yfinance series sliced ≤ D |
| Earnings calls (dates + transcript gist) | ✅ | ✅ | earnings with call date ≤ D; transcript text dated |
| Per-stock news + sentiment | ✅ | ✅ | search filtered to published ≤ D |
| Congress trades | ✅ | ✅ | `congress_trades` filing date ≤ D |
| Insider (SEC Form 4) | ✅ | ✅ | SEC filing date ≤ D |
| 13F institutional | ✅ | ✅ | `institution_holdings` filing date ≤ D |
| Fundamentals / valuation / trailing P/E | ✅ | ◑ | quarterly EPS + price ≤ D (recomputed) |
| Bubble score | ✅ | ◑ | recomputed from PIT price + fundamentals |
| Analyst consensus / recommendation | ✅ | ◑ | dated where revision history exists |
| Peer valuation | ✅ | ◑ | recomputed from PIT peer prices/fundamentals |
| Catalyst calendar | ✅ | ✅ | events dated; future-of-D catalysts known if announced ≤ D |
| Live web search | ✅ | ✗→date-filtered | live = today's web; bootstrap = published-date filter only |
| Options flow | ✅ | ✗ | **live-only** — used live; excluded from backtest (no PIT history → contamination) |
| Pre-market gap, reddit/social buzz | ✅ | ✗ | **live-only** — same reasoning as options flow |

`◑` = reconstructed best-effort from point-in-time primitives; if a value can't
be honestly reconstructed for a given symbol/date it is **omitted (None)**, never
fabricated, never back-filled with today's value.

## Architecture & Components

```
                 ┌──────────────────────────────────────────┐
                 │  analyst_playbook.md  (fed into BOTH       │
                 │  Claude stages every day; rewritten weekly)│
                 └──────────────────────────────────────────┘
   as-of D                    │                         ▲ weekly rewrite
      │                       ▼                         │
┌─────────────┐   ┌────────────────────┐   ┌────────────────────┐
│ PIT signal  │──▶│ Stage 1: triage    │──▶│ Stage 2: deep-read │──▶ 10 picks
│ assembler   │   │ (Opus, ~1,022 rows)│   │ (Opus, ~35 packets │     + rationale
│ (compact +  │   │   → ~35 shortlist  │   │  + search) → 10    │
│  full)      │   └────────────────────┘   └────────────────────┘
└─────────────┘                                       │
      ▲                                                ▼
┌─────────────┐                              ┌────────────────────┐
│ daily signal│◀── archive full board ───────│ persist (mode tag) │
│ archive     │    every LIVE day            │ + grade open→close │
└─────────────┘                              └────────────────────┘
```

### A. Point-in-time signal assembler — `api/services/analyst_pit_service.py` (new)
- `assemble_compact(universe, as_of)` → `list[dict]` (one compact row per symbol).
- `assemble_full(symbols, as_of, *, allow_live_search)` → full packets for the shortlist.
- Each source has a `*_as_of(symbol|symbols, D)` reader documenting its PIT
  guarantee; reads guarded by `src/utils/point_in_time.py` `assert_no_lookahead`.
- `allow_live_search=False` in bootstrap (date-filtered news only); `True` live.
- Reuses `ai_analyst_service`'s macro/indicator PIT approach where possible.

### B. Two-stage Claude predictor — `api/services/analyst_predictor.py` (new)
- `triage(compact_rows, playbook)` → `~35` symbols + one-line reasons (Opus).
- `deep_pick(full_packets, playbook, *, allow_live_search)` → 10 ranked picks,
  each with `reasoning` + `confidence` (Opus).
- `predict_for_date(as_of, *, mode)` orchestrates A→Stage1→Stage2.
- Deterministic momentum-rank **fallback** if Claude fails (never fabricate).
- All Claude calls via `src/utils/claude_cli.ask_claude_json` (subprocess, $0).

### C. Grading — extend `api/services/predictions_service.py`
- `record_actuals_for_date(D, universe=A+B)`: open→close % for all ~1,022, rank,
  hit if `universe_rank <= ceil(0.15 * universe_size)`.
- `get_accuracy_window()` already computes rolling hit rate — widen to A+B.

### D. Playbook engine — reuse the skills writer
- New file `data/predictions/analyst_playbook.md` (kept separate from the
  existing momentum `skills.md` so neither clobbers the other).
- Fed into **both** Claude stages each day.
- `rewrite_playbook(window)` (adapted from `update_prediction_skills`): Opus
  digests the window's picks + outcomes + hit-rate-by-feature → rewrites the file
  atomically. Same file spans bootstrap → live (continuity).

### E. Bootstrap orchestrator — `scripts/bootstrap_ai_analyst.py` (committed, resumable)
Walk-forward, oldest→newest over the last 90 trading days:
```
prefetch bars for A+B over [today-100d, today]           # one bulk load
for D in trading_days(last=90):
    if already_predicted(D): continue                     # idempotent/resumable
    packets  = assemble(universe, as_of=D, allow_live_search=False)
    picks    = two_stage_predict(packets, playbook, mode='bootstrap')
    persist(picks, mode='bootstrap', date=D)
    grade(D)                                               # open→close ranks
    if end_of_trading_week(D):
        playbook = rewrite_playbook(window=this_week)
report rolling hit-rate curve over the 90 days
```
Runs as a long background job with progress logging; resumable on restart.

### F. Live loop — scheduler hooks (`api/main.py`)
- **6:30 ET:** `predict_for_date(today, mode='live')` — full board + live search.
- **16:15 ET:** `record_actuals_for_date(today)` + archive the day's full signals.
- **Weekly (Fri close):** `rewrite_playbook(window=trailing_week)`.

On go-live, `ai_analyst_v1` **replaces** `5d_momentum_v1` as the active strategy
(the 6:30 ET job calls the analyst, not the deterministic ranker). Momentum-rank
survives only as the in-predictor fallback when a Claude call fails.

## Data model

Reuse: `daily_predictions`, `daily_prediction_actuals`, `prediction_strategies`
(+ one `ai_analyst_v1` row).

- `daily_predictions`: add `mode TEXT` (`'bootstrap'|'live'`) and store per-pick
  `reasoning` + `confidence` in existing columns / `components_json`.
- **New `signal_archive`** table — the daily full-board snapshot:
  ```sql
  CREATE TABLE IF NOT EXISTS signal_archive (
    as_of_date  TEXT NOT NULL,      -- YYYY-MM-DD (the day the snapshot is FOR)
    symbol      TEXT NOT NULL,
    signals_json TEXT NOT NULL,     -- full per-symbol signal packet
    captured_at TEXT NOT NULL,      -- when written (audit)
    PRIMARY KEY (as_of_date, symbol)
  );
  CREATE INDEX IF NOT EXISTS idx_sigarch_date ON signal_archive(as_of_date);
  ```
  Written every live day, storing the full live board (including the three
  live-only signals). Future backtests read honest stored history from here
  instead of reconstructing. The **90-day cold-start bootstrap does not use the
  live-only signals** (no archived history exists for those past dates).

## Point-in-time / data-integrity guarantees (CLAUDE.md)

- Bootstrap: only PIT-reconstructable signals; `allow_live_search=False`; news
  via published-date ≤ D filter. **Options flow, pre-market gap, and reddit buzz
  are excluded from the backtest** (no PIT history → contamination risk) and are
  used **live-only**. Any no-history signal is **omitted** for a past date,
  never faked with today's value.
- Live: the full board, including the three live-only signals above.
- Every assembler reader documents its PIT guarantee in its docstring; reads
  wrapped by `assert_no_lookahead`.
- No fabrication anywhere: missing signal → `None`, Claude is instructed it may
  use only the provided packet (+ dated search) and must not invent data.
- `Decimal` for any price/financial values; parameterized SQL.

## Accuracy & reporting

- Rolling hit-rate (predicted-in-top-15% / total) over the bootstrap 90 days and
  live. Surfaced on the Predictions page alongside each day's picks + rationale.
- Per-feature attribution in the weekly rewrite (which signals preceded hits).

## Cost / latency

- Bootstrap: ~90 days × 2 Opus calls + ~15 rewrites ≈ **~195 Opus calls**,
  walk-forward (sequential due to playbook dependency) → hours of wall-clock.
  **$0** on the Claude subscription (CLI subprocess). Run as a resumable
  background job with progress.
- Live: 2 Opus calls + grading + archive per day; one weekly rewrite.

## Testing (temp DB, synthetic `SYN_*`, no network, injected gateway)

- **PIT assembler:** seed synthetic dated rows (congress filed before/after D,
  Form 4, 13F, earnings dates); assert as-of-D reader excludes anything dated > D
  (lookahead guard). Price slicing stops at D.
- **Two-stage predictor:** injected fake-Claude returning deterministic JSON;
  assert Stage-1 shortlist feeds Stage-2; fallback to momentum on Claude failure;
  exactly 10 picks with reasoning+confidence.
- **Grading:** synthetic open→close returns over a synthetic A+B; assert top-15%
  rank threshold + rolling hit-rate math.
- **Playbook rewrite:** injected fake-Claude; atomic write; version-tag guard;
  same file across bootstrap→live.
- **Signal archive:** write + read-back a full snapshot; PK dedup per (date,symbol).
- **Bootstrap orchestrator:** 3-day mini-walk-forward against a temp DB; assert
  idempotent resume (re-run skips done dates), weekly rewrite fires on week-end.

## Open items / follow-ups

- Exact compact-row schema (which columns Claude sees for 1,022) — tune in the plan.
- Web-search provider for dated news in bootstrap (Exa `end_published_date` vs
  Tavily date filters) — pick in the plan.

## Resolved

- **Go-live = replace.** `ai_analyst_v1` becomes the active strategy outright,
  replacing `5d_momentum_v1` (which remains only as the in-predictor fallback).
