# Daily Picks Tier A+B Scoring Universe — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Score Tier A+B of `stocks_universe` (~1,022 liquid names, incl. MRVL) nightly so daily-picks draws candidates from that wider universe instead of the hardcoded 69 — without touching the other 5 refresh jobs or brief.

**Architecture:** Add `_tier_ab_symbols()` (queries `stocks_universe WHERE tier IN ('A','B')`, falls back to `_all_target_symbols()` if empty); parameterize `refresh_scores(symbols=None)` (default unchanged); point the API's 5:30 ET scoring job at the Tier A+B list. Everything else (`_all_target_symbols`, the 5 high-frequency refresh jobs, `get_opportunities`, `STOCK_DB`, brief) is untouched.

**Tech Stack:** Python, SQLite (`stocks_universe`, `precomputed_scores`), the existing `_fan_out` thread pool + `get_historical`/`technical.analyze`/`compute_opportunity`. pytest with temp DB + monkeypatched gateway (no network). Use `python3`.

**Reference spec:** `docs/superpowers/specs/2026-06-08-daily-picks-tier-ab-universe-design.md`

**Conventions:** tests use the autouse temp-DB fixture, synthetic symbols `SYN_*` + `source='test'`, no network/LLM (per CLAUDE.md test isolation).

**Hard constraint:** Do NOT modify `_all_target_symbols()`, the other refresh jobs, or brief.

---

## File Structure
- **Modify:** `src/scheduler.py` — add `_tier_ab_symbols()`; add `symbols=None` param to `refresh_scores`.
- **Modify:** `api/main.py` — the 5:30 ET scoring job calls `refresh_scores(symbols=_tier_ab_symbols())`.
- **Create tests:** `tests/test_tier_ab_symbols.py`, `tests/test_refresh_scores_scope.py`.

---

## Task 1: Tier-A+B universe source + parameterized scoring

**Files:**
- Modify: `src/scheduler.py`
- Test: `tests/test_tier_ab_symbols.py`, `tests/test_refresh_scores_scope.py`

**Context (current code, `src/scheduler.py`):**
```python
def _all_target_symbols() -> list[str]:
    """Watchlist symbols + STOCK_DB symbols (deduplicated)."""
    from src.data.stock_db import STOCK_DB
    init_db()
    syms = {item["symbol"] for item in get_watchlist()}
    syms.update(STOCK_DB.keys())
    return sorted(syms)
```
`refresh_scores()` ends with `_fan_out(_one, _all_target_symbols(), max_workers=4, label="scores")`. `_one(sym)` builds `DataGateway()`, calls `gw.get_historical(sym, period_days=252)`, then `technical.analyze` → `compute_opportunity` → `save_precomputed_score`. `stocks_universe` has columns incl. `symbol, tier ('A'|'B'|'C'|'D'), source`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tier_ab_symbols.py`:
```python
"""_tier_ab_symbols pulls Tier A+B from stocks_universe, falls back when empty."""
from __future__ import annotations

from src import scheduler
from src.utils.db import get_connection, init_db


def _seed_universe(rows):
    init_db()
    c = get_connection()
    c.execute("DELETE FROM stocks_universe WHERE source='test'")
    for sym, tier in rows:
        c.execute(
            "INSERT OR REPLACE INTO stocks_universe (symbol, tier, source) VALUES (?, ?, 'test')",
            (sym, tier),
        )
    c.commit(); c.close()


def test_tier_ab_returns_only_a_and_b():
    _seed_universe([("SYN_A1", "A"), ("SYN_B1", "B"), ("SYN_C1", "C"), ("SYN_D1", "D")])
    out = scheduler._tier_ab_symbols()
    assert "SYN_A1" in out and "SYN_B1" in out
    assert "SYN_C1" not in out and "SYN_D1" not in out


def test_tier_ab_falls_back_when_universe_empty():
    init_db()
    c = get_connection(); c.execute("DELETE FROM stocks_universe"); c.commit(); c.close()
    out = scheduler._tier_ab_symbols()
    # falls back to the watchlist + STOCK_DB list
    assert out == scheduler._all_target_symbols()
    assert len(out) > 0
```

Create `tests/test_refresh_scores_scope.py`:
```python
"""refresh_scores(symbols=...) scores exactly the given symbols (no network)."""
from __future__ import annotations

import pandas as pd

from src import scheduler
from src.utils.db import get_connection, init_db


def _fake_hist():
    # 60 ascending bars — enough for technical.analyze + compute_opportunity.
    rows = []
    for i in range(60):
        base = 80 + i * 0.4
        rows.append({"date": f"2026-0{1+i//28}-{1+i%28:02d}",
                     "open": base, "high": base + 1.5, "low": base - 1.5,
                     "close": base, "volume": 1_000_000})
    return pd.DataFrame(rows)


class _FakeGateway:
    def get_historical(self, symbol, period_days=252):
        return _fake_hist()


def test_refresh_scores_scopes_to_given_symbols(monkeypatch):
    init_db()
    c = get_connection()
    c.execute("DELETE FROM precomputed_scores WHERE symbol LIKE 'SYN_%'")
    c.commit(); c.close()

    # Inject a no-network gateway for the scoring fetch.
    import src.data.gateway as gw_mod
    monkeypatch.setattr(gw_mod, "DataGateway", _FakeGateway)
    # Guard: if the default path were used, this would blow up loudly.
    monkeypatch.setattr(scheduler, "_all_target_symbols",
                        lambda: (_ for _ in ()).throw(AssertionError("default scope used")))

    scheduler.refresh_scores(symbols=["SYN_A", "SYN_B"])

    c = get_connection()
    got = {r["symbol"] for r in c.execute(
        "SELECT symbol FROM precomputed_scores WHERE symbol LIKE 'SYN_%'")}
    c.close()
    assert got == {"SYN_A", "SYN_B"}
```

- [ ] **Step 2: Run — expect FAIL**

Run: `python3 -m pytest tests/test_tier_ab_symbols.py tests/test_refresh_scores_scope.py -v`
Expected: FAIL — `_tier_ab_symbols` missing; `refresh_scores()` takes no `symbols` arg.

- [ ] **Step 3: Implement**

In `src/scheduler.py`, add `_tier_ab_symbols` right after `_all_target_symbols`:
```python
def _tier_ab_symbols() -> list[str]:
    """Tier A+B symbols from stocks_universe (the liquid/tradeable slice).

    Falls back to _all_target_symbols() if the table is empty/unavailable, so a
    scoring run never operates on nothing.
    """
    init_db()
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT symbol FROM stocks_universe WHERE tier IN ('A','B') ORDER BY symbol"
        ).fetchall()
        conn.close()
        syms = [r["symbol"] for r in rows]
    except Exception:
        syms = []
    return syms or _all_target_symbols()
```

Then change the `refresh_scores` signature and its final line. Replace:
```python
def refresh_scores() -> None:
    """Pre-compute opportunity scores → write to precomputed_scores table. Daily 5 PM ET."""
```
with:
```python
def refresh_scores(symbols: list[str] | None = None) -> None:
    """Pre-compute opportunity scores → write to precomputed_scores table.

    `symbols` defaults to _all_target_symbols() (watchlist + STOCK_DB) for the
    legacy standalone scheduler; the API scheduler passes _tier_ab_symbols().
    """
```
and replace the final line:
```python
    _fan_out(_one, _all_target_symbols(), max_workers=4, label="scores")
```
with:
```python
    scope = symbols if symbols is not None else _all_target_symbols()
    _fan_out(_one, scope, max_workers=4, label="scores")
```
(Confirm `get_connection` is imported at module top in `src/scheduler.py`; it is used elsewhere in the file. If not imported, add `from src.utils.db import get_connection` near the existing db imports.)

- [ ] **Step 4: Run — expect PASS**

Run: `python3 -m pytest tests/test_tier_ab_symbols.py tests/test_refresh_scores_scope.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/scheduler.py tests/test_tier_ab_symbols.py tests/test_refresh_scores_scope.py
git commit -m "feat(scheduler): _tier_ab_symbols + scope param on refresh_scores

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Point the API scoring job at Tier A+B

**Files:**
- Modify: `api/main.py`

**Context:** the current 5:30 ET block (api/main.py ~lines 73–87) is:
```python
    try:
        from api.services._scheduler import schedule_daily_at
        from src.scheduler import refresh_scores as _refresh_scores

        def _refresh_opportunity_scores():
            try:
                _refresh_scores()
            except Exception:
                pass

        schedule_daily_at(5, 30, _refresh_opportunity_scores, name="opportunity_scores_refresh")
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("opportunity scores scheduler failed: %r", e)
```

- [ ] **Step 1: Edit the import + call**

Change the import line to also bring in `_tier_ab_symbols`, and the call to pass the Tier A+B scope:
```python
        from api.services._scheduler import schedule_daily_at
        from src.scheduler import refresh_scores as _refresh_scores, _tier_ab_symbols

        def _refresh_opportunity_scores():
            try:
                _refresh_scores(symbols=_tier_ab_symbols())
            except Exception:
                pass
```
Leave the `schedule_daily_at(5, 30, ...)` line and the surrounding try/except unchanged.

- [ ] **Step 2: Verify it compiles + imports**

Run: `python3 -m py_compile api/main.py && echo OK`
Expected: `OK`.
Run: `python3 -c "import ast,sys; ast.parse(open('api/main.py').read()); print('parse ok')"`
Expected: `parse ok`.
(Full `import api.main` may fail on an unrelated missing dep like `ta` — that's pre-existing; a SyntaxError or a NameError on `_tier_ab_symbols` is ours to fix.)

- [ ] **Step 3: Confirm the symbols resolve at runtime**

Run:
```bash
python3 -c "from src.scheduler import _tier_ab_symbols; print('tier A+B count:', len(_tier_ab_symbols()))"
```
Expected: a count in the ~1,000 range (Tier A+B from the live `stocks_universe`), confirming the wiring resolves real symbols. (If it prints the ~69 fallback count, `stocks_universe` is unexpectedly empty — investigate before continuing.)

- [ ] **Step 4: Commit**

```bash
git add api/main.py
git commit -m "feat(api): score Tier A+B nightly for daily-picks (was hardcoded 69)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Regression check

**Files:** none (verification only)

- [ ] **Step 1: New tests + the daily-picks suite**

Run:
```bash
python3 -m pytest tests/test_tier_ab_symbols.py tests/test_refresh_scores_scope.py \
  tests/test_daily_picks_scoring.py tests/test_daily_picks_agents.py \
  tests/test_daily_picks_synthesis.py tests/test_daily_picks_service.py \
  tests/test_daily_picks_grounded_service.py tests/test_daily_picks_option_plans.py -q
```
Expected: all PASS.

- [ ] **Step 2: Confirm other refresh jobs untouched**

Run: `git diff --stat HEAD~2 HEAD -- src/scheduler.py`
Expected: only the `_tier_ab_symbols` addition + the `refresh_scores` signature/scope-line change. Confirm `_all_target_symbols` body and the other `refresh_*` functions are unchanged:
`grep -n "def _all_target_symbols\|_all_target_symbols()" src/scheduler.py` — the 5 non-scoring jobs (`refresh_prices`, `refresh_fundamentals`, `refresh_insider`, `refresh_news`, `refresh_options`) must still call `_all_target_symbols()`.

- [ ] **Step 3: Data-integrity grep on new tests**

Run: `grep -nE "trading\.db|DB_PATH|sqlite3\.connect" tests/test_tier_ab_symbols.py tests/test_refresh_scores_scope.py`
Expected: no matches (tests use `get_connection`/`init_db` against the temp DB only).

---

## Self-Review Notes (author)

- **Spec coverage:** `_tier_ab_symbols` w/ empty-fallback (T1), parameterized `refresh_scores` keeping the legacy default (T1), API scheduler scope change (T2), `_all_target_symbols`/other jobs untouched (verified T3.2), tests synthetic+temp-DB (T1). brief never referenced.
- **Type consistency:** `_tier_ab_symbols() -> list[str]` and `refresh_scores(symbols: list[str] | None = None)` are used verbatim in the api/main.py call (`_refresh_scores(symbols=_tier_ab_symbols())`).
- **Isolation:** the `refresh_scores` scope test guards against the default path (monkeypatches `_all_target_symbols` to throw) so a regression there fails loudly; the gateway is monkeypatched so no network. Synthetic `SYN_*` symbols + `source='test'` per CLAUDE.md.
- **Out of scope (unchanged):** `get_opportunities` limit, other refresh jobs, Tier C/D, first-call latency.
```
