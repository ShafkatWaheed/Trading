# AI Analyst — Daily Top-Gainer Predictor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Claude (Opus) analyst that each day reads the full point-in-time signal board for the Tier A+B universe, predicts 10 likely top-15% gainers in two stages (triage → deep-pick), grades itself same-day, and compounds a `analyst_playbook.md` it rewrites weekly — cold-started by a strict point-in-time 90-day walk-forward.

**Architecture:** New service modules (`analyst_pit_service`, `analyst_predictor`, `analyst_playbook`) reuse the existing point-in-time helpers in `api/services/ai_analyst_service.py` and the existing prediction persistence (`daily_predictions`, `daily_prediction_actuals`, `prediction_strategies`) in `predictions_service.py`. A committed bootstrap script walk-forwards the past 90 trading days; scheduler hooks run it live and replace `5d_momentum_v1` with `ai_analyst_v1`.

**Tech Stack:** Python, SQLite (`src/utils/db.py`), `claude` CLI subprocess (`ask_claude_json`, model=`opus`), yfinance (price/macro), pytest (temp-DB fixture, synthetic `SYN_*`).

**Spec:** [docs/superpowers/specs/2026-06-09-ai-analyst-predictor-design.md](../specs/2026-06-09-ai-analyst-predictor-design.md)

---

## Conventions (read once)

- **Tests:** temp DB via `tests/conftest.py` `_isolated_test_db` (autouse). Use synthetic `SYN_*` symbols, `source='test'`, and clean them in fixture teardown. Never touch production `trading.db` (CLAUDE.md).
- **No fabrication:** any signal that can't be honestly reconstructed for a past date returns `None` and is omitted — never faked with today's value (CLAUDE.md Data Integrity).
- **Claude calls:** always `from src.utils.claude_cli import ask_claude_json`; `model="opus"` for predictions/playbook (project preference). Inject a fake in tests — never hit the network.
- **Money:** use `Decimal` only where a value is a price/financial quantity persisted as money; scores stay `float`.
- **Run tests:** `python3 -m pytest <path> -q` from repo root.

## File Structure

| File | Responsibility |
|---|---|
| `src/utils/db.py` (MODIFY) | Add `signal_archive` table; idempotent `mode` column on `daily_predictions`. |
| `api/services/analyst_pit_service.py` (NEW) | Point-in-time signal assembler: `assemble_compact`, `assemble_full`. Reuses `ai_analyst_service` PIT helpers + congress/13F filing-date filters. |
| `api/services/analyst_predictor.py` (NEW) | Two-stage Opus predictor: `triage`, `deep_pick`, `predict_for_date`; momentum fallback. |
| `api/services/analyst_playbook.py` (NEW) | `analyst_playbook.md` read/write/ensure + `rewrite_playbook`. |
| `api/services/predictions_service.py` (MODIFY) | A+B universe loader; top-15% threshold in `get_accuracy_window`; ensure `ai_analyst_v1` strategy. |
| `api/services/analyst_archive_service.py` (NEW) | `archive_signals_for_date` — store the full live board daily. |
| `scripts/bootstrap_ai_analyst.py` (NEW) | Resumable 90-day walk-forward orchestrator. |
| `api/main.py` (MODIFY) | Swap 6:30 job → analyst predict; 16:15 → actuals + archive; weekly playbook rewrite; activate `ai_analyst_v1`. |
| `api/routes/predictions.py` (MODIFY) | `GET /predictions/analyst/playbook`, `GET /predictions/bootstrap/status`. |
| `tests/test_*` (NEW) | One test module per service. |

---

## Task 1: `signal_archive` table + `mode` column

**Files:**
- Modify: `src/utils/db.py` (within `init_db()` executescript block, after the `daily_prediction_actuals` block ~line 748)
- Test: `tests/test_analyst_schema.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_analyst_schema.py
"""Schema additions for the AI analyst: signal_archive + daily_predictions.mode."""
from src.utils.db import get_connection, init_db


def _cols(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def test_signal_archive_table_exists():
    init_db()
    conn = get_connection()
    try:
        cols = _cols(conn, "signal_archive")
    finally:
        conn.close()
    assert {"as_of_date", "symbol", "signals_json", "captured_at"} <= cols


def test_daily_predictions_has_mode_column():
    init_db()
    conn = get_connection()
    try:
        assert "mode" in _cols(conn, "daily_predictions")
    finally:
        conn.close()


def test_init_db_is_idempotent_for_mode():
    # Running init_db twice must not error on the ALTER (column already added).
    init_db()
    init_db()
    conn = get_connection()
    try:
        assert "mode" in _cols(conn, "daily_predictions")
    finally:
        conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_analyst_schema.py -q`
Expected: FAIL — `signal_archive` missing / `mode` column absent.

- [ ] **Step 3: Add the table to the executescript block**

In `src/utils/db.py`, immediately after the `daily_prediction_actuals` CREATE/INDEX block, add:

```sql
        CREATE TABLE IF NOT EXISTS signal_archive (
            as_of_date   TEXT NOT NULL,   -- YYYY-MM-DD the snapshot is FOR
            symbol       TEXT NOT NULL,
            signals_json TEXT NOT NULL,   -- full per-symbol signal packet (JSON)
            captured_at  TEXT NOT NULL,   -- when written (audit)
            PRIMARY KEY (as_of_date, symbol)
        );
        CREATE INDEX IF NOT EXISTS idx_sigarch_date ON signal_archive(as_of_date);
```

- [ ] **Step 4: Add an idempotent `mode` migration after `init_db()` runs the script**

`daily_predictions` already exists in production, so `mode` needs an `ALTER`. Add this helper and call it at the end of `init_db()` (after `conn.executescript(...)`, before the function returns / connection closes):

```python
def _add_column_if_missing(conn, table: str, column: str, decl: str) -> None:
    """Idempotent ADD COLUMN — safe to run every init_db()."""
    existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
```

In `init_db()`, after the `executescript`:

```python
    _add_column_if_missing(conn, "daily_predictions", "mode", "TEXT")
    conn.commit()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest tests/test_analyst_schema.py -q`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add src/utils/db.py tests/test_analyst_schema.py
git commit -m "feat(db): signal_archive table + daily_predictions.mode for AI analyst"
```

---

## Task 2: Ensure the `ai_analyst_v1` strategy row

**Files:**
- Modify: `api/services/predictions_service.py` (add `ensure_ai_analyst_strategy()` near `get_active_strategy` ~line 575)
- Test: `tests/test_ai_analyst_strategy.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ai_analyst_strategy.py
from api.services import predictions_service as ps
from src.utils.db import get_connection, init_db


def test_ensure_creates_ai_analyst_strategy():
    init_db()
    v = ps.ensure_ai_analyst_strategy()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT name, config_json FROM prediction_strategies WHERE version=?", (v,)
        ).fetchone()
    finally:
        conn.close()
    assert row["name"] == "ai_analyst_v1"
    import json
    cfg = json.loads(row["config_json"])
    assert cfg["ranking_signal"] == "ai_analyst"
    assert cfg["universe_tier"] == "AB"


def test_ensure_is_idempotent():
    init_db()
    v1 = ps.ensure_ai_analyst_strategy()
    v2 = ps.ensure_ai_analyst_strategy()
    assert v1 == v2  # no duplicate row
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_ai_analyst_strategy.py -q`
Expected: FAIL — `ensure_ai_analyst_strategy` undefined.

- [ ] **Step 3: Implement**

In `api/services/predictions_service.py`:

```python
import json as _json
from datetime import datetime, timezone


def ensure_ai_analyst_strategy() -> int:
    """Create the ai_analyst_v1 strategy row if absent; return its version.

    Idempotent — returns the existing version when already present.
    """
    init_db()
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT version FROM prediction_strategies WHERE name='ai_analyst_v1'"
        ).fetchone()
        if existing:
            return existing["version"]
        cfg = {
            "ranking_signal": "ai_analyst",   # picks come from the Claude analyst
            "universe_tier": "AB",            # Tier A+B
            "top_n": 10,
            "hit_threshold_pct": 15,          # top 15% of the universe = hit
        }
        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            "INSERT INTO prediction_strategies (name, description, config_json, created_at) "
            "VALUES (?,?,?,?)",
            ("ai_analyst_v1",
             "Claude analyst reads the full signal board and picks 10 daily top-gainer candidates.",
             _json.dumps(cfg), now),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_ai_analyst_strategy.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add api/services/predictions_service.py tests/test_ai_analyst_strategy.py
git commit -m "feat(predictions): ensure_ai_analyst_strategy() registers ai_analyst_v1"
```

---

## Task 3: A+B universe loader + top-15% accuracy threshold

**Files:**
- Modify: `api/services/predictions_service.py` — add `_load_universe_ab()`; add `hit_threshold_pct` path to `get_accuracy_window` (line 1168)
- Test: `tests/test_ai_analyst_accuracy.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ai_analyst_accuracy.py
from api.services import predictions_service as ps
from src.utils.db import get_connection, init_db


def _seed_ab():
    init_db()
    conn = get_connection()
    try:
        conn.execute("DELETE FROM stocks_universe WHERE source='test'")
        for i, t in enumerate(["A", "A", "B", "B"]):
            conn.execute(
                "INSERT INTO stocks_universe (symbol, tier, source) VALUES (?,?,'test')",
                (f"SYN_U{i}", t),
            )
        conn.commit()
    finally:
        conn.close()


def test_load_universe_ab_returns_a_and_b_only():
    _seed_ab()
    syms = ps._load_universe_ab()
    conn = get_connection()
    try:
        conn.execute("DELETE FROM stocks_universe WHERE source='test'")
        conn.commit()
    finally:
        conn.close()
    assert {"SYN_U0", "SYN_U1", "SYN_U2", "SYN_U3"} <= set(syms)


def test_threshold_pct_converts_to_rank():
    # 200-symbol universe, top 15% => rank threshold 30.
    assert ps._pct_threshold_to_rank(15, 200) == 30
    assert ps._pct_threshold_to_rank(15, 1000) == 150
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_ai_analyst_accuracy.py -q`
Expected: FAIL — `_load_universe_ab` / `_pct_threshold_to_rank` undefined.

- [ ] **Step 3: Implement**

In `api/services/predictions_service.py`:

```python
import math


def _load_universe_ab() -> list[str]:
    """Tier A+B symbols (the analyst's universe). Ordered for determinism."""
    init_db()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT symbol FROM stocks_universe WHERE tier IN ('A','B') ORDER BY symbol"
        ).fetchall()
        return [r["symbol"] for r in rows]
    finally:
        conn.close()


def _pct_threshold_to_rank(pct: int, universe_size: int) -> int:
    """Top-`pct`% of `universe_size` → an integer rank cutoff (>=1)."""
    return max(1, math.ceil(universe_size * pct / 100))
```

Then extend `get_accuracy_window` (line 1168) to accept an optional percentage. Add a keyword `hit_threshold_pct: int | None = None`; when set, derive the per-day rank cutoff from that day's `universe_size` via `_pct_threshold_to_rank` instead of the fixed `hit_threshold`. Keep the existing `hit_threshold` behavior when `hit_threshold_pct is None` (back-compat). (The per-day `universe_size` is already read from `daily_prediction_actuals` in this function.)

- [ ] **Step 3b: Widen `record_actuals_for_date` to rank against A+B**

`record_actuals_for_date` (line 1096) currently ranks the predicted picks against the **Tier A** universe to assign `universe_rank` / `universe_size`. The analyst predicts from **A+B**, so the ranking universe must match or picks outside Tier A get no honest rank. Change the universe it scores from the Tier-A loader to `_load_universe_ab()` (so `universe_size` ≈ 1,022 and the top-15% threshold in `get_accuracy_window` is computed against the right pool). This is safe: `ai_analyst_v1` replaces `5d_momentum_v1`, so all live rows are analyst rows.

Add a focused test (no network — assert the universe-selection helper, not the price fetch):

```python
def test_record_actuals_uses_ab_universe(monkeypatch):
    # the ranking universe must be A+B, not Tier A
    seen = {}
    monkeypatch.setattr(ps, "_load_universe_ab", lambda: (seen.setdefault("ab", True) or ["SYN_U0"]))
    # stub the price/open-close fetch so no network is hit; just assert _load_universe_ab was used
    monkeypatch.setattr(ps, "_score_universe_changes", lambda syms, date: {s: 0.0 for s in syms})
    ps.record_actuals_for_date("2026-02-02")
    assert seen.get("ab") is True
```

(If `record_actuals_for_date` does not already factor its universe-change scoring behind a helper, extract one named `_score_universe_changes(symbols, date)` during this step so it is mockable without network.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_ai_analyst_accuracy.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add api/services/predictions_service.py tests/test_ai_analyst_accuracy.py
git commit -m "feat(predictions): A+B universe loader + top-N% accuracy threshold"
```

---

## Task 4: PIT signal assembler — compact rows

**Files:**
- Create: `api/services/analyst_pit_service.py`
- Test: `tests/test_analyst_pit_compact.py`

This reuses `ai_analyst_service` PIT helpers for macro/sector/insider/opportunity, and adds **congress / 13F filing-date filters** (point-in-time).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_analyst_pit_compact.py
"""PIT compact assembler: filing-date filters must exclude anything dated > D."""
from api.services import analyst_pit_service as pit
from src.utils.db import get_connection, init_db


def _seed():
    init_db()
    conn = get_connection()
    try:
        conn.execute("DELETE FROM congress_trades WHERE source='test'")
        conn.execute("DELETE FROM institution_holdings WHERE source='hand' AND cik LIKE 'TESTCIK%'")
        # congress buy filed 2026-01-10 (before D) and one filed 2026-03-20 (after D)
        for i, (fdate, tdate) in enumerate([("2026-01-10", "2026-01-05"),
                                            ("2026-03-20", "2026-03-15")]):
            conn.execute(
                "INSERT INTO congress_trades (filing_uuid, txn_index, chamber, politician_name, "
                "party, ticker, transaction_type, transaction_date, filing_date, source, fetched_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,'test',datetime('now'))",
                (f"tc{i}", i, "House", "Rep X", "R", "SYN_PIT", "buy", tdate, fdate),
            )
        # 13F as_of before D and after D
        for i, asof in enumerate(["2025-12-31", "2026-03-31"]):
            conn.execute(
                "INSERT INTO institution_holdings (cik, symbol, value_usd, shares, as_of, source) "
                "VALUES (?,?,?,?,?,'hand')",
                (f"TESTCIK{i}", "SYN_PIT", 1000.0, 10.0, asof),
            )
        conn.commit()
    finally:
        conn.close()


def _cleanup():
    conn = get_connection()
    try:
        conn.execute("DELETE FROM congress_trades WHERE source='test'")
        conn.execute("DELETE FROM institution_holdings WHERE cik LIKE 'TESTCIK%'")
        conn.commit()
    finally:
        conn.close()


def test_congress_flag_excludes_filings_after_d():
    _seed()
    # As of 2026-02-01: only the 2026-01-10 filing is known.
    flags = pit.congress_flags_as_of(["SYN_PIT"], "2026-02-01")
    _cleanup()
    assert flags.get("SYN_PIT", 0) == 1   # one disclosed buy known by D


def test_13f_flag_excludes_periods_after_d():
    _seed()
    n = pit.institution_breadth_as_of(["SYN_PIT"], "2026-02-01").get("SYN_PIT", 0)
    _cleanup()
    assert n == 1   # only the 2025-12-31 13F period is known by 2026-02-01
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_analyst_pit_compact.py -q`
Expected: FAIL — module/functions undefined.

- [ ] **Step 3: Implement the filing-date readers + compact assembler**

Create `api/services/analyst_pit_service.py`:

```python
"""Point-in-time signal assembler for the AI analyst.

Every reader returns only data knowable on/before the as-of date `D`
(YYYY-MM-DD). No lookahead (CLAUDE.md). Two views:
  - assemble_compact(symbols, D) -> list[dict] (one row/symbol, for triage)
  - assemble_full(symbols, D, *, allow_live_search) -> dict (deep-read packets)

Reuses the historical PIT helpers in api/services/ai_analyst_service.py
(macro, sector ETF, insider window, opportunity score).
"""
from __future__ import annotations

from src.utils.db import get_connection, init_db


def congress_flags_as_of(symbols: list[str], as_of: str) -> dict[str, int]:
    """{symbol: count of congressional BUYS disclosed (filing_date <= D)}.

    PIT guarantee: filters on filing_date, the date the trade became public.
    """
    if not symbols:
        return {}
    init_db()
    conn = get_connection()
    try:
        ph = ",".join("?" * len(symbols))
        rows = conn.execute(
            f"""
            SELECT ticker, COUNT(*) n FROM congress_trades
            WHERE transaction_type='buy' AND ticker IN ({ph})
              AND filing_date IS NOT NULL AND filing_date <= ?
            GROUP BY ticker
            """,
            (*symbols, as_of),
        ).fetchall()
        return {r["ticker"]: r["n"] for r in rows}
    finally:
        conn.close()


def institution_breadth_as_of(symbols: list[str], as_of: str) -> dict[str, int]:
    """{symbol: distinct 13F holders whose filing period (as_of) <= D}.

    PIT guarantee: a 13F period-end <= D was filed by then (period end always
    precedes the filing). Conservative — never reveals future positions.
    """
    if not symbols:
        return {}
    init_db()
    conn = get_connection()
    try:
        ph = ",".join("?" * len(symbols))
        rows = conn.execute(
            f"""
            SELECT symbol, COUNT(DISTINCT cik) h FROM institution_holdings
            WHERE symbol IN ({ph}) AND as_of <= ?
            GROUP BY symbol
            """,
            (*symbols, as_of),
        ).fetchall()
        return {r["symbol"]: r["h"] for r in rows}
    finally:
        conn.close()
```

Then add `assemble_compact(symbols, as_of)` that, for each symbol, builds a compact dict:
```python
{"symbol", "name", "sector", "momentum_pct", "sector_flow_pct",
 "congress_buys", "institutions", "macro_regime"}
```
- `momentum_pct`: slice price history to `as_of` and compute trailing 5-day % (reuse `ai_analyst_service._historical_opportunity` / `_compute_indicators` on the sliced df; if no bars ≤ D, omit the symbol).
- `sector_flow_pct`: `ai_analyst_service._sector_perf_at(_fetch_sector_history(sector, start, as_of), as_of)`.
- `macro_regime`: derived from `ai_analyst_service._macro_at(_fetch_macro_history(start, as_of), as_of)`.
- `congress_buys` / `institutions`: from the two readers above.
- `name`/`sector`: from `stocks_universe` + `stock_industry` (reuse `universe_service`-style join).
Fetch price history **once** for the whole universe at the start of an assemble call (bulk), then slice per `as_of` in the bootstrap (the orchestrator passes the prefetched frame — see Task 9). Document the PIT guarantee in the docstring.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_analyst_pit_compact.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add api/services/analyst_pit_service.py tests/test_analyst_pit_compact.py
git commit -m "feat(analyst): PIT compact assembler + congress/13F filing-date filters"
```

---

## Task 5: PIT signal assembler — full packets (deep-read)

**Files:**
- Modify: `api/services/analyst_pit_service.py` — add `assemble_full`
- Test: `tests/test_analyst_pit_full.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_analyst_pit_full.py
from api.services import analyst_pit_service as pit


def test_full_packet_omits_live_only_signals_in_bootstrap():
    # allow_live_search=False (bootstrap) => packet must NOT contain options/premarket/reddit
    pkt = pit.assemble_full(["SYN_PIT"], "2026-02-01", allow_live_search=False)
    one = pkt.get("SYN_PIT", {})
    assert "options_flow" not in one
    assert "premarket" not in one
    assert "reddit" not in one
    # but it DOES carry the reconstructable block keys
    assert set(one.keys()) <= {
        "momentum", "sector_flow", "macro", "congress", "insider",
        "institutions", "news", "earnings", "fundamentals", "short_interest",
    }


def test_full_packet_includes_live_only_when_allowed():
    pkt = pit.assemble_full(["SYN_PIT"], "2026-02-01", allow_live_search=True)
    one = pkt.get("SYN_PIT", {})
    # live mode MAY include options/premarket/reddit keys (values can be None)
    assert "options_flow" in one
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_analyst_pit_full.py -q`
Expected: FAIL — `assemble_full` undefined.

- [ ] **Step 3: Implement `assemble_full`**

```python
def assemble_full(symbols: list[str], as_of: str, *, allow_live_search: bool) -> dict[str, dict]:
    """Full per-symbol packets for the shortlist.

    Bootstrap (allow_live_search=False): only PIT-reconstructable blocks —
    momentum, sector_flow, macro, congress, insider, institutions, news
    (published<=D), earnings (call date<=D), fundamentals, short_interest.

    Live (allow_live_search=True): the above PLUS the live-only signals
    options_flow / premarket / reddit (no PIT history → live only) and live
    web search context.

    Any block that cannot be honestly reconstructed for `as_of` is omitted
    (None), never faked.
    """
    packets: dict[str, dict] = {}
    for sym in symbols:
        p = {
            "momentum": _momentum_block(sym, as_of),
            "sector_flow": _sector_block(sym, as_of),
            "macro": _macro_block(as_of),
            "congress": congress_flags_as_of([sym], as_of).get(sym),
            "insider": _insider_block(sym, as_of),
            "institutions": institution_breadth_as_of([sym], as_of).get(sym),
            "news": _news_block(sym, as_of, allow_live_search=allow_live_search),
            "earnings": _earnings_block(sym, as_of),
            "fundamentals": _fundamentals_block(sym, as_of),
            "short_interest": _short_interest_block(sym, as_of),
        }
        if allow_live_search:
            # live-only signals (no PIT history) — present only on live days
            p["options_flow"] = _live_options(sym)
            p["premarket"] = _live_premarket(sym)
            p["reddit"] = _live_reddit(sym)
        packets[sym] = p
    return packets
```

Implement each `_*_block` helper by delegating to the verified PIT helpers:
- `_momentum_block` → slice + `_historical_opportunity` (returns trailing return, trend, RS).
- `_sector_block` → `_sector_perf_at`.
- `_macro_block` → `_macro_at`.
- `_insider_block` → `_insider_window` on `_fetch_historical_insider_pool` (cluster_buy etc.).
- `_short_interest_block` → `_finra_short_window`.
- `_news_block` → date-filtered search (Exa `end_published_date=as_of` / Tavily date filter) for bootstrap; live web search when `allow_live_search`. Bounded to the shortlist only.
- `_earnings_block` → earnings calendar entries with call date ≤ `as_of` (reuse `gateway.get_earnings_calendar`, filter dates ≤ D).
- `_fundamentals_block` → trailing P/E from quarterly EPS ≤ D (the `ai_analyst_service` trailing-P/E approach).
- `_live_options` / `_live_premarket` / `_live_reddit` → live gateway reads (only called when `allow_live_search`).

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_analyst_pit_full.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add api/services/analyst_pit_service.py tests/test_analyst_pit_full.py
git commit -m "feat(analyst): PIT full-packet assembler (live-only signals gated)"
```

---

## Task 6: Two-stage predictor — triage + deep-pick

**Files:**
- Create: `api/services/analyst_predictor.py`
- Test: `tests/test_analyst_predictor.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_analyst_predictor.py
"""Two-stage predictor with an injected fake Claude (no network)."""
from api.services import analyst_predictor as ap


def _compact(n):
    return [{"symbol": f"SYN_{i:03d}", "name": f"Co {i}", "sector": "Tech",
             "momentum_pct": float(n - i)} for i in range(n)]


class _FakeClaude:
    def __init__(self, triage, picks):
        self._triage, self._picks = triage, picks
        self.calls = []

    def __call__(self, prompt, *, model, timeout, retries=0, allowed_tools=""):
        self.calls.append(("triage" if "shortlist" in prompt else "pick", allowed_tools))
        return self._triage if "shortlist" in prompt else self._picks


def test_triage_returns_shortlist_symbols():
    fake = _FakeClaude({"shortlist": ["SYN_000", "SYN_001"]}, None)
    out = ap.triage(_compact(40), playbook="PB", claude=fake)
    assert out == ["SYN_000", "SYN_001"]


def test_deep_pick_returns_ten_with_reasoning():
    picks = {"picks": [{"symbol": f"SYN_{i:03d}", "reasoning": "r", "confidence": 0.6}
                       for i in range(10)]}
    fake = _FakeClaude(None, picks)
    out = ap.deep_pick({f"SYN_{i:03d}": {"momentum": 1} for i in range(10)},
                       playbook="PB", allow_live_search=False, claude=fake)
    assert len(out) == 10
    assert all("reasoning" in p and "confidence" in p for p in out)
    # bootstrap => no web tools requested
    assert fake.calls[-1][1] == ""


def test_deep_pick_falls_back_to_momentum_on_claude_failure():
    fake = _FakeClaude(None, None)   # returns None => failure
    packets = {f"SYN_{i:03d}": {"momentum": {"trailing_return": float(10 - i)}}
               for i in range(12)}
    out = ap.deep_pick(packets, playbook="PB", allow_live_search=False, claude=fake)
    assert len(out) == 10
    assert out[0]["symbol"] == "SYN_000"   # highest momentum first
    assert out[0]["reasoning"].startswith("fallback")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_analyst_predictor.py -q`
Expected: FAIL — module undefined.

- [ ] **Step 3: Implement**

Create `api/services/analyst_predictor.py` with `triage`, `deep_pick`, and `predict_for_date`. `claude` is an injectable callable defaulting to `ask_claude_json` (so tests pass a fake). `allowed_tools="WebSearch,WebFetch"` only when `allow_live_search`. `deep_pick` validates the response shape (list of 10 `{symbol, reasoning, confidence}` with symbols ⊆ packet keys); on `None`/invalid, falls back to ranking packets by `momentum.trailing_return` and returns the top 10 with `reasoning="fallback: momentum rank (Claude unavailable)"`. Prompts embed the playbook + the compact table / full packets as JSON.

```python
from __future__ import annotations
from src.utils.claude_cli import ask_claude_json

_SHORTLIST_N = 35
_PICKS_N = 10


def triage(compact_rows, *, playbook, claude=ask_claude_json) -> list[str]:
    prompt = _triage_prompt(compact_rows, playbook)   # must contain the word "shortlist"
    raw = claude(prompt, model="opus", timeout=180, retries=1)
    syms = (raw or {}).get("shortlist") if isinstance(raw, dict) else None
    valid = {r["symbol"] for r in compact_rows}
    return [s for s in (syms or []) if s in valid][:_SHORTLIST_N]


def deep_pick(packets, *, playbook, allow_live_search, claude=ask_claude_json) -> list[dict]:
    tools = "WebSearch,WebFetch" if allow_live_search else ""
    raw = claude(_pick_prompt(packets, playbook), model="opus", timeout=240,
                 retries=1, allowed_tools=tools)
    picks = _valid_picks(raw, set(packets))
    if picks:
        return picks[:_PICKS_N]
    # deterministic fallback — never fabricate
    ranked = sorted(packets.items(),
                    key=lambda kv: (kv[1].get("momentum") or {}).get("trailing_return", 0.0),
                    reverse=True)
    return [{"symbol": s, "reasoning": "fallback: momentum rank (Claude unavailable)",
             "confidence": None} for s, _ in ranked[:_PICKS_N]]
```

(`_triage_prompt`, `_pick_prompt`, `_valid_picks` are small pure helpers — `_valid_picks` returns `[]` unless `raw` is a dict with a `picks` list of objects whose `symbol` ∈ packet keys.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_analyst_predictor.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add api/services/analyst_predictor.py tests/test_analyst_predictor.py
git commit -m "feat(analyst): two-stage Opus predictor (triage + deep-pick + fallback)"
```

---

## Task 7: `predict_for_date` — orchestrate + persist

**Files:**
- Modify: `api/services/analyst_predictor.py` — add `predict_for_date`
- Test: `tests/test_analyst_predict_for_date.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_analyst_predict_for_date.py
from api.services import analyst_predictor as ap
from src.utils.db import get_connection, init_db


def test_predict_persists_ten_rows_with_mode(monkeypatch):
    init_db()
    # stub the assemblers + predictor internals to avoid network
    monkeypatch.setattr(ap, "_assemble_compact",
                        lambda syms, d: [{"symbol": s, "momentum_pct": 1.0} for s in syms])
    monkeypatch.setattr(ap, "triage", lambda rows, **k: [r["symbol"] for r in rows][:5])
    monkeypatch.setattr(ap, "_assemble_full",
                        lambda syms, d, **k: {s: {"momentum": {"trailing_return": 1.0}} for s in syms})
    monkeypatch.setattr(
        ap, "deep_pick",
        lambda packets, **k: [{"symbol": s, "reasoning": "r", "confidence": 0.5}
                              for s in list(packets)[:10]])
    monkeypatch.setattr(ap, "_universe", lambda: [f"SYN_{i:03d}" for i in range(12)])

    res = ap.predict_for_date("2026-02-02", mode="bootstrap")
    assert res["count"] >= 1
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT symbol, rank, mode FROM daily_predictions WHERE prediction_date='2026-02-02' ORDER BY rank"
        ).fetchall()
        conn.execute("DELETE FROM daily_predictions WHERE prediction_date='2026-02-02'")
        conn.commit()
    finally:
        conn.close()
    assert rows and rows[0]["mode"] == "bootstrap"
    assert rows[0]["rank"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_analyst_predict_for_date.py -q`
Expected: FAIL — `predict_for_date` undefined.

- [ ] **Step 3: Implement**

```python
def predict_for_date(as_of: str, *, mode: str) -> dict:
    """Run the two-stage analyst for `as_of` and persist top-10 to daily_predictions.

    mode: 'bootstrap' (PIT, no live search) | 'live' (full board + search).
    Idempotent per date: deletes any existing rows for `as_of` first.
    """
    from api.services import analyst_playbook, predictions_service
    init_db()
    strategy_version = predictions_service.ensure_ai_analyst_strategy()
    playbook = analyst_playbook.read()
    allow_live = (mode == "live")

    compact = _assemble_compact(_universe(), as_of)
    shortlist = triage(compact, playbook=playbook)
    packets = _assemble_full(shortlist, as_of, allow_live_search=allow_live)
    picks = deep_pick(packets, playbook=playbook, allow_live_search=allow_live)

    _persist(as_of, picks, mode=mode, strategy_version=strategy_version)
    return {"date": as_of, "mode": mode, "count": len(picks),
            "shortlist": len(shortlist)}
```

`_universe` defaults to `predictions_service._load_universe_ab`. `_assemble_compact`/`_assemble_full` delegate to `analyst_pit_service`. `_persist` writes rank 1..10 into `daily_predictions` with `mode`, `score=confidence`, `reasoning`, `strategy_version`, `created_at`, and `components_json=json.dumps(pick_evidence)` after a `DELETE FROM daily_predictions WHERE prediction_date=?` (idempotent).

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_analyst_predict_for_date.py -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add api/services/analyst_predictor.py tests/test_analyst_predict_for_date.py
git commit -m "feat(analyst): predict_for_date orchestration + idempotent persist"
```

---

## Task 8: Playbook module (`analyst_playbook.md`)

**Files:**
- Create: `api/services/analyst_playbook.py`
- Test: `tests/test_analyst_playbook.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_analyst_playbook.py
from api.services import analyst_playbook as pb


def test_read_autocreates_with_version_tag(tmp_path, monkeypatch):
    monkeypatch.setattr(pb, "_PATH", tmp_path / "analyst_playbook.md")
    content = pb.read()
    assert pb._VERSION_TAG in content


def test_write_then_read_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(pb, "_PATH", tmp_path / "analyst_playbook.md")
    pb.write(pb._VERSION_TAG + "\n# learned\n- tech gaps win")
    assert "tech gaps win" in pb.read()


def test_rewrite_rejects_response_missing_tag(monkeypatch, tmp_path):
    monkeypatch.setattr(pb, "_PATH", tmp_path / "analyst_playbook.md")
    before = pb.read()
    res = pb.rewrite(history=[{"x": 1}], accuracy={}, claude=lambda *a, **k: "no tag here")
    assert res["updated"] is False
    assert pb.read() == before   # unchanged on bad response
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_analyst_playbook.py -q`
Expected: FAIL — module undefined.

- [ ] **Step 3: Implement** (mirrors the verified `_read_skills`/`_write_skills`/`update_prediction_skills` shape, but a separate file)

```python
"""The AI analyst's accumulated playbook (separate from momentum skills.md)."""
from __future__ import annotations
import os, tempfile
from pathlib import Path
from src.utils.claude_cli import ask_claude

_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "predictions" / "analyst_playbook.md"
_VERSION_TAG = "<!-- analyst-playbook-v1 -->"
_TEMPLATE = f"""{_VERSION_TAG}
# AI Analyst Playbook

Accumulated, graded observations about what precedes a top-15% gainer.
Rewritten weekly from real outcomes. Empty until the first rewrite.
"""


def _ensure() -> Path:
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    if not _PATH.exists():
        _PATH.write_text(_TEMPLATE, encoding="utf-8")
    return _PATH


def read() -> str:
    _ensure()
    try:
        return _PATH.read_text(encoding="utf-8")
    except Exception:
        return _TEMPLATE


def write(content: str) -> None:
    _ensure()
    fd, tmp = tempfile.mkstemp(dir=str(_PATH.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp, _PATH)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def rewrite(*, history, accuracy, claude=None) -> dict:
    """Ask Opus to rewrite the playbook from graded history. Atomic; rejects a
    response missing the version tag (leaves the playbook unchanged)."""
    claude = claude or (lambda prompt: ask_claude(prompt, model="opus", timeout=240))
    if not history:
        return {"updated": False, "reason": "no_history"}
    prompt = _build_prompt(read(), history, accuracy)
    new = claude(prompt) or ""
    if _VERSION_TAG not in new:
        return {"updated": False, "reason": "missing_version_tag"}
    write(new[new.find(_VERSION_TAG):])
    return {"updated": True, "bytes": len(new)}
```

(`_build_prompt` composes current playbook + history + accuracy and instructs Opus to return the full markdown starting with the version tag.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_analyst_playbook.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add api/services/analyst_playbook.py tests/test_analyst_playbook.py
git commit -m "feat(analyst): analyst_playbook module (read/write/rewrite)"
```

---

## Task 9: Bootstrap orchestrator (walk-forward, resumable)

**Files:**
- Create: `scripts/bootstrap_ai_analyst.py`
- Test: `tests/test_bootstrap_ai_analyst.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bootstrap_ai_analyst.py
from scripts import bootstrap_ai_analyst as boot
from src.utils.db import get_connection, init_db


def test_walk_forward_skips_already_predicted(monkeypatch):
    init_db()
    calls = []
    monkeypatch.setattr(boot, "_trading_days", lambda n: ["2026-02-02", "2026-02-03", "2026-02-04"])
    monkeypatch.setattr(boot, "predict_for_date",
                        lambda d, mode: calls.append(d) or {"count": 10})
    monkeypatch.setattr(boot, "record_actuals_for_date", lambda d: {"recorded": 10})
    monkeypatch.setattr(boot, "_is_week_end", lambda d: False)
    # pre-seed one date as already predicted
    conn = get_connection()
    try:
        conn.execute("INSERT OR IGNORE INTO daily_predictions "
                     "(prediction_date, rank, symbol, strategy_version, created_at, mode) "
                     "VALUES ('2026-02-03', 1, 'SYN_X', 1, datetime('now'), 'bootstrap')")
        conn.commit()
    finally:
        conn.close()
    boot.run(days=3)
    conn = get_connection()
    try:
        conn.execute("DELETE FROM daily_predictions WHERE symbol='SYN_X'")
        conn.commit()
    finally:
        conn.close()
    assert "2026-02-03" not in calls   # skipped (resumable)
    assert "2026-02-02" in calls and "2026-02-04" in calls


def test_week_end_triggers_rewrite(monkeypatch):
    init_db()
    rewrites = []
    monkeypatch.setattr(boot, "_trading_days", lambda n: ["2026-02-06"])  # a Friday
    monkeypatch.setattr(boot, "predict_for_date", lambda d, mode: {"count": 10})
    monkeypatch.setattr(boot, "record_actuals_for_date", lambda d: {"recorded": 10})
    monkeypatch.setattr(boot, "_is_week_end", lambda d: True)
    monkeypatch.setattr(boot, "_rewrite_playbook_window", lambda d: rewrites.append(d))
    boot.run(days=1)
    assert rewrites == ["2026-02-06"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_bootstrap_ai_analyst.py -q`
Expected: FAIL — module undefined.

- [ ] **Step 3: Implement**

```python
"""Cold-start the AI analyst: strict point-in-time 90-day walk-forward.

For each past trading day (oldest→newest): predict (bootstrap mode, no live
search), grade open→close, and every week-end rewrite the playbook from that
week's graded results. Idempotent/resumable — days already predicted are
skipped. Run: .venv/bin/python -m scripts.bootstrap_ai_analyst [--days 90]
"""
from __future__ import annotations
import argparse, logging
from api.services.analyst_predictor import predict_for_date
from api.services.predictions_service import record_actuals_for_date, get_accuracy_window, _load_history_with_context
from api.services import analyst_playbook
from src.utils.db import get_connection, init_db

logger = logging.getLogger(__name__)


def _already_predicted(date: str) -> bool:
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT 1 FROM daily_predictions WHERE prediction_date=? LIMIT 1", (date,)
        ).fetchone() is not None
    finally:
        conn.close()


def _trading_days(n: int) -> list[str]:
    """Last `n` trading days (oldest→newest), YYYY-MM-DD, ending yesterday.

    Uses the NYSE calendar when pandas_market_calendars is installed; otherwise
    falls back to business days (Mon–Fri). The fallback over-counts holidays
    slightly — harmless for a cold-start window, since the assembler simply
    skips any day with no price bar <= D.
    """
    import datetime as _dt
    import pandas as pd
    end = _dt.date.today() - _dt.timedelta(days=1)
    try:
        import pandas_market_calendars as mcal
        sched = mcal.get_calendar("NYSE").schedule(
            start_date=(end - _dt.timedelta(days=n * 2)).isoformat(),
            end_date=end.isoformat())
        return [d.date().isoformat() for d in sched.index][-n:]
    except Exception:
        return [d.date().isoformat() for d in pd.bdate_range(end=end, periods=n)]


def _is_week_end(date: str) -> bool:
    import datetime as _dt
    d = _dt.date.fromisoformat(date)
    return d.weekday() == 4  # Friday


def _rewrite_playbook_window(date: str) -> None:
    history = _load_history_with_context(window_days=7)
    accuracy = get_accuracy_window(window_days=7, hit_threshold_pct=15)
    analyst_playbook.rewrite(history=history, accuracy=accuracy)


def run(days: int = 90) -> dict:
    init_db()
    predicted = graded = 0
    for d in _trading_days(days):
        if _already_predicted(d):
            continue
        predict_for_date(d, mode="bootstrap"); predicted += 1
        record_actuals_for_date(d); graded += 1
        if _is_week_end(d):
            _rewrite_playbook_window(d)
    acc = get_accuracy_window(window_days=days, hit_threshold_pct=15)
    logger.info("bootstrap done: predicted=%d graded=%d hit_rate=%s",
                predicted, graded, acc.get("hit_rate"))
    return {"predicted": predicted, "graded": graded, "accuracy": acc}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=90)
    print(run(ap.parse_args().days))
```

For `_trading_days`: prefer an NYSE calendar; if the calendar library is unavailable, fall back to `pandas.bdate_range(end=yesterday, periods=n)` (business days) — document the approximation in the docstring. Pick the provider during implementation (check `requirements.txt`).

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_bootstrap_ai_analyst.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/bootstrap_ai_analyst.py tests/test_bootstrap_ai_analyst.py
git commit -m "feat(analyst): resumable 90-day walk-forward bootstrap orchestrator"
```

---

## Task 10: Daily signal archive

**Files:**
- Create: `api/services/analyst_archive_service.py`
- Test: `tests/test_analyst_archive.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_analyst_archive.py
import json
from api.services import analyst_archive_service as arch
from src.utils.db import get_connection, init_db


def test_archive_writes_full_board(monkeypatch):
    init_db()
    monkeypatch.setattr(arch, "_universe", lambda: ["SYN_A1", "SYN_A2"])
    monkeypatch.setattr(arch, "_assemble_full",
                        lambda syms, d, **k: {s: {"momentum": {"trailing_return": 1.0},
                                                  "options_flow": 0.3} for s in syms})
    arch.archive_signals_for_date("2026-02-05")
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT symbol, signals_json FROM signal_archive WHERE as_of_date='2026-02-05'"
        ).fetchall()
        conn.execute("DELETE FROM signal_archive WHERE as_of_date='2026-02-05'")
        conn.commit()
    finally:
        conn.close()
    assert {r["symbol"] for r in rows} == {"SYN_A1", "SYN_A2"}
    assert "options_flow" in json.loads(rows[0]["signals_json"])   # full live board stored
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_analyst_archive.py -q`
Expected: FAIL — module undefined.

- [ ] **Step 3: Implement**

```python
"""Daily full-board signal archive — written every LIVE day so future
backtests read honest stored history instead of reconstructing it."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from api.services import analyst_pit_service, predictions_service
from src.utils.db import get_connection, init_db

_universe = predictions_service._load_universe_ab


def _assemble_full(symbols, as_of, **kw):
    return analyst_pit_service.assemble_full(symbols, as_of, allow_live_search=True)


def archive_signals_for_date(as_of: str) -> dict:
    """Store the full live signal board for every universe symbol on `as_of`.
    Idempotent per (date, symbol). Live-only signals included."""
    init_db()
    packets = _assemble_full(_universe(), as_of, allow_live_search=True)
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        for sym, pkt in packets.items():
            conn.execute(
                "INSERT OR REPLACE INTO signal_archive (as_of_date, symbol, signals_json, captured_at) "
                "VALUES (?,?,?,?)",
                (as_of, sym, json.dumps(pkt, default=str), now),
            )
        conn.commit()
        return {"date": as_of, "archived": len(packets)}
    finally:
        conn.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_analyst_archive.py -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add api/services/analyst_archive_service.py tests/test_analyst_archive.py
git commit -m "feat(analyst): daily full-board signal archive"
```

---

## Task 11: Live scheduler wiring + activate `ai_analyst_v1`

**Files:**
- Modify: `api/main.py` — repoint the 6:30 / 16:15 jobs; add weekly playbook rewrite; activate strategy at startup
- Test: `tests/test_analyst_live_jobs.py`

- [ ] **Step 1: Write the failing test** (test the job bodies, not the scheduler threads)

```python
# tests/test_analyst_live_jobs.py
import api.main as m


def test_live_predict_job_uses_analyst(monkeypatch):
    called = {}
    monkeypatch.setattr(m, "_analyst_predict_for_date",
                        lambda d, mode: called.setdefault("predict", (d, mode)))
    m._generate_predictions_today()
    assert called["predict"][1] == "live"


def test_actuals_job_also_archives(monkeypatch):
    seq = []
    monkeypatch.setattr(m, "record_actuals_for_date", lambda d: seq.append(("actuals", d)))
    monkeypatch.setattr(m, "archive_signals_for_date", lambda d: seq.append(("archive", d)))
    m._record_predictions_actuals()
    assert [s[0] for s in seq] == ["actuals", "archive"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_analyst_live_jobs.py -q`
Expected: FAIL — job bodies not yet repointed / imports missing.

- [ ] **Step 3: Implement**

In `api/main.py`:
- Import `from api.services.analyst_predictor import predict_for_date as _analyst_predict_for_date`, `from api.services.analyst_archive_service import archive_signals_for_date`, `from api.services.predictions_service import record_actuals_for_date, ensure_ai_analyst_strategy, activate_strategy`, `from api.services import analyst_playbook`.
- Repoint `_generate_predictions_today()` (line 106) to call `_analyst_predict_for_date(today_et(), mode="live")`.
- Extend `_record_predictions_actuals()` (line 113) to call `record_actuals_for_date(today)` then `archive_signals_for_date(today)`.
- Add `_weekly_analyst_playbook()` scheduled Friday 16:30 ET (weekday check == 4) → `analyst_playbook.rewrite(history=_load_history_with_context(7), accuracy=get_accuracy_window(window_days=7, hit_threshold_pct=15))`.
- At startup (where strategies/scheduler init): `activate_strategy(ensure_ai_analyst_strategy())` so `ai_analyst_v1` replaces `5d_momentum_v1` as active.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_analyst_live_jobs.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add api/main.py tests/test_analyst_live_jobs.py
git commit -m "feat(analyst): live scheduler (predict/actuals+archive/weekly playbook) + activate ai_analyst_v1"
```

---

## Task 12: API routes — playbook + bootstrap status

**Files:**
- Modify: `api/routes/predictions.py`
- Test: `tests/test_analyst_routes.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_analyst_routes.py
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


def test_analyst_playbook_route():
    r = client.get("/predictions/analyst/playbook")
    assert r.status_code == 200
    assert "playbook" in r.json()


def test_bootstrap_status_route():
    r = client.get("/predictions/bootstrap/status")
    assert r.status_code == 200
    body = r.json()
    assert "predicted_days" in body and "hit_rate" in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_analyst_routes.py -q`
Expected: FAIL — routes 404.

- [ ] **Step 3: Implement** in `api/routes/predictions.py`

```python
@router.get("/analyst/playbook")
def analyst_playbook_route() -> dict:
    from api.services import analyst_playbook
    return {"playbook": analyst_playbook.read()}


@router.get("/bootstrap/status")
def bootstrap_status() -> dict:
    from api.services.predictions_service import get_accuracy_window
    from src.utils.db import get_connection
    conn = get_connection()
    try:
        n = conn.execute(
            "SELECT COUNT(DISTINCT prediction_date) c FROM daily_predictions WHERE mode='bootstrap'"
        ).fetchone()["c"]
    finally:
        conn.close()
    acc = get_accuracy_window(window_days=90, hit_threshold_pct=15)
    return {"predicted_days": n, "hit_rate": acc.get("hit_rate"),
            "days_evaluated": acc.get("days_evaluated")}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_analyst_routes.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add api/routes/predictions.py tests/test_analyst_routes.py
git commit -m "feat(analyst): playbook + bootstrap-status API routes"
```

---

## Task 13: Full-suite gate + manual bootstrap smoke

**Files:** none new (verification task)

- [ ] **Step 1: Run the whole analyst test set**

Run:
```bash
python3 -m pytest tests/test_analyst_schema.py tests/test_ai_analyst_strategy.py \
  tests/test_ai_analyst_accuracy.py tests/test_analyst_pit_compact.py \
  tests/test_analyst_pit_full.py tests/test_analyst_predictor.py \
  tests/test_analyst_predict_for_date.py tests/test_analyst_playbook.py \
  tests/test_bootstrap_ai_analyst.py tests/test_analyst_archive.py \
  tests/test_analyst_live_jobs.py tests/test_analyst_routes.py -q
```
Expected: all PASS.

- [ ] **Step 2: Run the existing prediction tests (no regressions)**

Run: `python3 -m pytest tests/ -q -k "predict or universe or schema"`
Expected: all PASS.

- [ ] **Step 3: Manual cold-start smoke (small window, real Claude)**

Run: `.venv/bin/python -m scripts.bootstrap_ai_analyst --days 3`
Expected: logs `bootstrap done: predicted=3 graded=3 hit_rate=<float>`; `GET /predictions/bootstrap/status` shows `predicted_days >= 3`. (Uses the real `claude` CLI — $0 on subscription; a few minutes wall-clock.)

- [ ] **Step 4: Commit (if any smoke-fix needed)**

```bash
git add -A && git commit -m "test(analyst): full-suite gate + bootstrap smoke fixes"
```

---

## Post-implementation

After all tasks: run `superpowers:finishing-a-development-branch` on `feat/ai-analyst`.

Then the **real 90-day cold-start** is a one-time operator action (long background job):
```bash
.venv/bin/python -m scripts.bootstrap_ai_analyst --days 90
```
followed by confirming `ai_analyst_v1` is the active strategy and the live scheduler jobs are firing.

## Notes / deferred (from spec "open items")

- Compact-row column set may be tuned during Task 4 (keep it small — Stage-1 reads ~1,022 rows).
- Dated-news search provider (Exa `end_published_date` vs Tavily) picked during Task 5.
- The bootstrap reads price history per `as_of`; for performance the orchestrator should prefetch the A+B price frame **once** and pass slices to the assembler (optimize in Task 9 if the naive per-day fetch is too slow).
