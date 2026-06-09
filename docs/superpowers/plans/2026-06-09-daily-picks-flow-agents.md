# Daily Picks Flow Agents — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-point the Insider, Flow, and Macro daily-picks agents at real data (SEC insider summary, congress_trades + institution_holdings, sector tape + dividend) so they stop returning 0 picks.

**Architecture:** In `api/services/daily_picks_agents.py`, give each of the 3 agents a dedicated data-backed selector (instead of the never-produced strategy tags), each intersecting its signal with the scored `opportunities` pool so picks keep their technical levels + score. Flow uses cheap bulk DB queries; Macro uses the cached sector tape + cached fundamentals; Insider uses the cached per-symbol SEC summary (bounded to top-15).

**Tech Stack:** Python, SQLite (`congress_trades`, `institution_holdings`), `smart_money_service.get_sector_tape`, `DataGateway.get_insider_summary`/`get_fundamentals`. pytest with temp DB + injected gateway/monkeypatch (no network).

**Reference spec:** `docs/superpowers/specs/2026-06-09-daily-picks-flow-agents-design.md`

**Conventions:** reuse existing `_pick(card, extra)`, `_evidence`, `rank_candidates`, `_PICKS_PER_AGENT` (5), `_SHORTLIST` (15) in the file. Per-agent failures degrade to `[]`. Tests: synthetic `SYN_*` symbols, `source='test'`, temp DB, no network. Use `python3`. Do NOT touch momentum/contrarian/disruption/value/options or brief.

**Context — current routing** (`discover_for_agent`):
```python
    if agent_key in _STRATEGY_LENSES:
        return _strategy_select(agent_key, opportunities)
    if agent_key == "value":
        return _value_select(opportunities, gateway)
    if agent_key == "options":
        return _options_select(opportunities, gateway)
    return []
```
`_STRATEGY_LENSES` currently includes `insider`, `flow`, `macro` — those keys get **removed** (one per task) as each gets a selector. `_pick(card, extra)` returns `{symbol, evidence, conviction}`. `rank_candidates(cands, *, key, top_n)`. Card dicts have `symbol`, `score`, `sector`.

---

## Task 1: Flow agent (bulk congress + 13F)

**Files:** Modify `api/services/daily_picks_agents.py`; Test `tests/test_daily_picks_flow_agent.py`.

- [ ] **Step 1: Write the failing test**

```python
"""Flow agent selects opportunities with congressional buying or 13F breadth."""
from __future__ import annotations

import api.services.daily_picks_agents as dpa
from src.utils.db import get_connection, init_db


def _card(sym, score=70):
    return {"symbol": sym, "strategy": "Neutral", "score": score,
            "secondary_strategies": [], "sub_scores": {}, "sector": "Tech", "price": 100}


def _seed(monkeypatch):
    init_db()
    c = get_connection()
    c.execute("DELETE FROM congress_trades WHERE source='test'")
    c.execute("DELETE FROM institution_holdings WHERE source='test'")
    # SYN_A: 2 recent congressional BUYS
    for i in range(2):
        c.execute(
            "INSERT INTO congress_trades (filing_uuid, txn_index, chamber, politician_name, "
            "party, ticker, transaction_type, transaction_date, source) "
            "VALUES (?,?,?,?,?,?,?,date('now','-10 day'),'test')",
            (f"t{i}", i, "House", "Rep X", "R", "SYN_A", "buy"),
        )
    # SYN_B: held by 5 distinct institutions
    for k in range(5):
        c.execute(
            "INSERT INTO institution_holdings (cik, symbol, value_usd, shares, as_of, source) "
            "VALUES (?,?,?,?,date('now'),'test')",
            (f"CIK{k}", "SYN_B", 1000.0, 10),
        )
    c.commit(); c.close()


def test_flow_selects_congress_and_institutional(monkeypatch):
    _seed(monkeypatch)
    opps = [_card("SYN_A", 88), _card("SYN_B", 80), _card("SYN_C", 75)]
    picks = dpa.discover_for_agent("flow", opportunities=opps, gateway=None)
    syms = {p["symbol"] for p in picks}
    assert "SYN_A" in syms and "SYN_B" in syms
    assert "SYN_C" not in syms      # no flow signal
    assert all("evidence" in p and "conviction" in p for p in picks)


def test_flow_empty_when_no_signal(monkeypatch):
    init_db()
    c = get_connection()
    c.execute("DELETE FROM congress_trades"); c.execute("DELETE FROM institution_holdings")
    c.commit(); c.close()
    picks = dpa.discover_for_agent("flow", opportunities=[_card("SYN_C")], gateway=None)
    assert picks == []
```

- [ ] **Step 2: Run — expect FAIL**

Run: `python3 -m pytest tests/test_daily_picks_flow_agent.py -v`
Expected: FAIL — `flow` currently routes via `_STRATEGY_LENSES` (tag match) → returns `[]`, so `test_flow_selects_congress_and_institutional` fails (SYN_A/SYN_B not selected).

> Before implementing: run `python3 -c "import sqlite3;c=sqlite3.connect('trading.db');print([r[1] for r in c.execute('PRAGMA table_info(congress_trades)')]);print([r[1] for r in c.execute('PRAGMA table_info(institution_holdings)')])"` and confirm the columns used above exist and that no OTHER column is NOT NULL without a default. If a NOT NULL column is missing from the test INSERTs, add it with a dummy value. (Columns referenced: congress_trades.ticker/transaction_type/transaction_date/source; institution_holdings.symbol/cik/source.)

- [ ] **Step 3: Implement**

In `api/services/daily_picks_agents.py`:

(a) Add the DB import near the top (after the scoring import):
```python
from src.utils.db import get_connection, init_db
```
(b) Add constants near the other module constants:
```python
_CONGRESS_BUY_MIN = 2     # >= this many recent congressional buys
_INST_HOLDER_MIN = 5      # >= this many distinct 13F holders
```
(c) Add the selector (a bulk-read helper + the selector; mirrors `_strategy_select`'s rank-then-`_pick` pattern):
```python
def _flow_signals() -> tuple[set[str], dict[str, int], dict[str, int]]:
    """Bulk read: tickers with recent congressional buys + 13F breadth.

    Returns (symbols, congress_counts, institution_counts). Empty on any error.
    """
    init_db()
    congress: dict[str, int] = {}
    inst: dict[str, int] = {}
    try:
        conn = get_connection()
        try:
            for r in conn.execute(
                "SELECT ticker, COUNT(*) AS n FROM congress_trades "
                "WHERE transaction_type='buy' AND transaction_date >= date('now','-180 day') "
                "GROUP BY ticker HAVING n >= ?", (_CONGRESS_BUY_MIN,)
            ):
                if r["ticker"]:
                    congress[r["ticker"].upper()] = r["n"]
            for r in conn.execute(
                "SELECT symbol, COUNT(DISTINCT cik) AS h FROM institution_holdings "
                "GROUP BY symbol HAVING h >= ?", (_INST_HOLDER_MIN,)
            ):
                if r["symbol"]:
                    inst[r["symbol"].upper()] = r["h"]
        finally:
            conn.close()
    except Exception:
        return set(), {}, {}
    return set(congress) | set(inst), congress, inst


def _flow_select(opportunities: list[dict]) -> list[dict]:
    symbols, congress, inst = _flow_signals()
    if not symbols:
        return []
    matched_cards = [c for c in opportunities if (c.get("symbol") or "").upper() in symbols]
    top = rank_candidates(matched_cards, key="score", top_n=_PICKS_PER_AGENT)
    return [_pick(c, {"congress_buys": congress.get((c.get("symbol") or "").upper()),
                      "institutions": inst.get((c.get("symbol") or "").upper())})
            for c in top]
```

(d) Remove `"flow"` from `_STRATEGY_LENSES`, and add its route in `discover_for_agent` (after the `options` branch):
```python
        if agent_key == "flow":
            return _flow_select(opportunities)
```

- [ ] **Step 4: Run — expect PASS**

Run: `python3 -m pytest tests/test_daily_picks_flow_agent.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add api/services/daily_picks_agents.py tests/test_daily_picks_flow_agent.py
git commit -m "feat(api): flow agent via bulk congress + 13F (was empty strategy tag)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Macro agent (sector tape inflow + dividend)

**Files:** Modify `api/services/daily_picks_agents.py`; Test `tests/test_daily_picks_macro_agent.py`.

- [ ] **Step 1: Write the failing test**

```python
"""Macro agent selects opportunities in inflow sectors + dividend plays."""
from __future__ import annotations

import api.services.daily_picks_agents as dpa


def _card(sym, sector, score=70):
    return {"symbol": sym, "strategy": "Neutral", "score": score,
            "secondary_strategies": [], "sub_scores": {}, "sector": sector, "price": 100}


class _FakeFund:
    def __init__(self, dy): self.dividend_yield = dy


class _FakeGateway:
    def __init__(self, divs): self._divs = divs           # {symbol: yield}
    def get_fundamentals(self, sym):
        from decimal import Decimal
        dy = self._divs.get(sym)
        return _FakeFund(Decimal(str(dy)) if dy is not None else None)


def test_macro_selects_inflow_sector_and_dividend(monkeypatch):
    import api.services.smart_money_service as sm
    monkeypatch.setattr(sm, "get_sector_tape",
                        lambda **kw: {"sectors": [{"sector": "Technology", "direction": "inflow"},
                                                  {"sector": "Energy", "direction": "outflow"}]})
    opps = [_card("SYN_T", "Technology", 88),    # inflow sector
            _card("SYN_E", "Energy", 80),        # outflow sector, no div
            _card("SYN_D", "Energy", 60)]        # dividend play
    gw = _FakeGateway({"SYN_D": 4.0, "SYN_T": 0.0, "SYN_E": 0.0})
    picks = dpa.discover_for_agent("macro", opportunities=opps, gateway=gw)
    syms = {p["symbol"] for p in picks}
    assert "SYN_T" in syms      # inflow sector
    assert "SYN_D" in syms      # dividend >= 3%
    assert "SYN_E" not in syms  # outflow sector + no dividend


def test_macro_empty_when_no_inflow_no_dividend(monkeypatch):
    import api.services.smart_money_service as sm
    monkeypatch.setattr(sm, "get_sector_tape", lambda **kw: {"sectors": []})
    opps = [_card("SYN_E", "Energy", 70)]
    picks = dpa.discover_for_agent("macro", opportunities=opps, gateway=_FakeGateway({}))
    assert picks == []
```

- [ ] **Step 2: Run — expect FAIL**

Run: `python3 -m pytest tests/test_daily_picks_macro_agent.py -v`
Expected: FAIL — `macro` still routes via `_STRATEGY_LENSES` (or, after Task 1, returns `[]`).

- [ ] **Step 3: Implement**

In `api/services/daily_picks_agents.py`:

(a) Add constant: `_DIV_YIELD_MIN = 3.0`.
(b) Add the selector. Note: `_pick` stores the card `score` in `evidence["score"]` (via `_evidence`), so the final ranking sorts on that. Do NOT call `rank_candidates` on `_pick` dicts — it expects **card** dicts; only the dividend-shortlist step (which iterates cards) uses it.
```python
def _macro_select(opportunities: list[dict], gateway) -> list[dict]:
    # Inflow sectors from the cached sector tape (case-insensitive match).
    inflow: set[str] = set()
    try:
        from api.services import smart_money_service
        tape = smart_money_service.get_sector_tape() or {}
        inflow = {(s.get("sector") or "").lower()
                  for s in tape.get("sectors", []) if s.get("direction") == "inflow"}
    except Exception:
        inflow = set()

    chosen: dict[str, dict] = {}   # symbol -> _pick dict (dedup)
    # 1) opportunities in an inflow sector
    if inflow:
        for c in opportunities:
            if (c.get("sector") or "").lower() in inflow:
                sym = (c.get("symbol") or "").upper()
                chosen[sym] = _pick(c, {"sector": c.get("sector"), "sector_inflow": True})
    # 2) dividend plays among the top _SHORTLIST by score
    for c in rank_candidates(opportunities, key="score", top_n=_SHORTLIST):
        sym = (c.get("symbol") or "").upper()
        if sym in chosen:
            continue
        try:
            f = gateway.get_fundamentals(c["symbol"])
            dy = getattr(f, "dividend_yield", None)
            if dy is not None and float(dy) >= _DIV_YIELD_MIN:
                chosen[sym] = _pick(c, {"sector": c.get("sector"), "dividend_yield": float(dy)})
        except Exception:
            continue
    # rank the chosen picks by their card score (stored in evidence by _evidence)
    picks = sorted(chosen.values(),
                   key=lambda p: float(p["evidence"].get("score") or 0), reverse=True)
    return picks[:_PICKS_PER_AGENT]
```

(c) Remove `"macro"` from `_STRATEGY_LENSES`; add route:
```python
        if agent_key == "macro":
            return _macro_select(opportunities, gateway)
```

- [ ] **Step 4: Run — expect PASS**

Run: `python3 -m pytest tests/test_daily_picks_macro_agent.py -v`
Expected: PASS (2 tests). Also `python3 -m pytest tests/test_daily_picks_flow_agent.py -q` (Task 1 still green).

- [ ] **Step 5: Commit**

```bash
git add api/services/daily_picks_agents.py tests/test_daily_picks_macro_agent.py
git commit -m "feat(api): macro agent via sector-tape inflow + dividend (was empty strategy tag)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Insider agent (cached per-symbol SEC)

**Files:** Modify `api/services/daily_picks_agents.py`; Test `tests/test_daily_picks_insider_agent.py`.

- [ ] **Step 1: Write the failing test**

```python
"""Insider agent selects opportunities with insider buying (cached SEC summary)."""
from __future__ import annotations

import api.services.daily_picks_agents as dpa


def _card(sym, score=70):
    return {"symbol": sym, "strategy": "Neutral", "score": score,
            "secondary_strategies": [], "sub_scores": {}, "sector": "Tech", "price": 100}


class _Sum:
    def __init__(self, *, cluster=False, signal="neutral", buys=0, net=0):
        self.cluster_buy = cluster; self.signal = signal
        self.total_buys = buys; self.net_shares = net


class _FakeGateway:
    def __init__(self, m, boom=()):
        self._m = m; self._boom = set(boom)
    def get_insider_summary(self, sym, days=90):
        if sym in self._boom:
            raise RuntimeError("SEC 500")
        return self._m.get(sym)


def test_insider_selects_buying_signals():
    opps = [_card("SYN_C", 90), _card("SYN_S", 85), _card("SYN_N", 80)]
    gw = _FakeGateway({
        "SYN_C": _Sum(cluster=True),
        "SYN_S": _Sum(signal="strong buy"),
        "SYN_N": _Sum(signal="neutral", buys=0),
    })
    picks = dpa.discover_for_agent("insider", opportunities=opps, gateway=gw)
    syms = {p["symbol"] for p in picks}
    assert syms == {"SYN_C", "SYN_S"}     # cluster + strong-buy; not neutral
    assert all("evidence" in p for p in picks)


def test_insider_skips_symbol_on_error():
    opps = [_card("SYN_X", 90), _card("SYN_Y", 80)]
    gw = _FakeGateway({"SYN_Y": _Sum(cluster=True)}, boom=["SYN_X"])
    picks = dpa.discover_for_agent("insider", opportunities=opps, gateway=gw)
    assert [p["symbol"] for p in picks] == ["SYN_Y"]   # SYN_X errored -> skipped
```

- [ ] **Step 2: Run — expect FAIL**

Run: `python3 -m pytest tests/test_daily_picks_insider_agent.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

In `api/services/daily_picks_agents.py`:

(a) Add constant: `_INSIDER_SHORTLIST = 15`.
(b) Add the selector:
```python
def _insider_select(opportunities: list[dict], gateway) -> list[dict]:
    out = []
    for c in rank_candidates(opportunities, key="score", top_n=_INSIDER_SHORTLIST):
        if len(out) >= _PICKS_PER_AGENT:
            break
        try:
            s = gateway.get_insider_summary(c["symbol"], days=90)
        except Exception:
            continue
        if s is None:
            continue
        buying = (getattr(s, "cluster_buy", False)
                  or getattr(s, "signal", "") in ("buy", "strong buy")
                  or (getattr(s, "total_buys", 0) or 0) >= 3)
        if buying:
            out.append(_pick(c, {"signal": getattr(s, "signal", ""),
                                 "cluster_buy": getattr(s, "cluster_buy", False),
                                 "total_buys": getattr(s, "total_buys", 0),
                                 "net_shares": getattr(s, "net_shares", 0)}))
    return out
```
(c) Remove `"insider"` from `_STRATEGY_LENSES`; add route:
```python
        if agent_key == "insider":
            return _insider_select(opportunities, gateway)
```

- [ ] **Step 4: Run — expect PASS**

Run: `python3 -m pytest tests/test_daily_picks_insider_agent.py tests/test_daily_picks_flow_agent.py tests/test_daily_picks_macro_agent.py tests/test_daily_picks_agents.py -v`
Expected: all PASS. Confirm `_STRATEGY_LENSES` now contains only `momentum`, `contrarian`, `disruption`.

- [ ] **Step 5: Commit**

```bash
git add api/services/daily_picks_agents.py tests/test_daily_picks_insider_agent.py
git commit -m "feat(api): insider agent via cached SEC insider summary (was empty strategy tag)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Regression + live smoke

**Files:** none (verification only)

- [ ] **Step 1: Daily-picks suite**

Run:
```bash
python3 -m pytest tests/test_daily_picks_agents.py tests/test_daily_picks_flow_agent.py \
  tests/test_daily_picks_macro_agent.py tests/test_daily_picks_insider_agent.py \
  tests/test_daily_picks_scoring.py tests/test_daily_picks_synthesis.py \
  tests/test_daily_picks_service.py tests/test_daily_picks_grounded_service.py \
  tests/test_daily_picks_option_plans.py -q
```
Expected: all PASS.

- [ ] **Step 2: Live smoke (against the real populated DB) — do the 3 agents now find candidates?**

Run:
```bash
timeout 150 python3 -c "
import api.services.discover_service as disc, api.services.daily_picks_agents as dpa
from src.data.gateway import DataGateway
opps=(disc.get_opportunities(limit=200, period='1M') or {}).get('opportunities',[])
gw=DataGateway()
for k in ['flow','macro','insider']:
    print(k, '->', len(dpa.discover_for_agent(k, opportunities=opps, gateway=gw)), 'picks')
"
```
Expected: `flow` and `macro` return ≥1 pick (data is populated); `insider` may be 0–N depending on real Form-4 activity. (Network for insider/dividend — allow time. If it hangs >150s, note it; the agents are bounded so it should finish.)

- [ ] **Step 3: Data-integrity grep**

```bash
grep -nE "trading\.db|DB_PATH|sqlite3\.connect" tests/test_daily_picks_flow_agent.py tests/test_daily_picks_macro_agent.py tests/test_daily_picks_insider_agent.py
```
Expected: no matches (tests use `get_connection`/`init_db` on the temp DB).

---

## Self-Review Notes (author)

- **Spec coverage:** Flow bulk congress+13F (T1), Macro sector-tape inflow + dividend (T2), Insider cached per-symbol SEC bounded to 15 (T3); each removes its key from `_STRATEGY_LENSES` + adds a route; momentum/contrarian/disruption/value/options untouched; regression + live smoke (T4). Synthetic-symbol temp-DB tests throughout.
- **Type/shape consistency:** all three selectors return lists of `_pick(card, extra)` dicts (`{symbol, evidence, conviction}`), consumed identically by `discover_for_agent`'s callers and the option_plans symbol-collection. `rank_candidates(cards, key="score", top_n=...)` used on **card** dicts (not `_pick` dicts) in every selector. `InsiderSummary` fields (`cluster_buy`/`signal`/`total_buys`/`net_shares`) and `StockFundamentals.dividend_yield` match the models. Sector match is case-insensitive.
- **Flagged for implementer:** verify `congress_trades`/`institution_holdings` NOT NULL columns before the seed INSERTs (PRAGMA check in T1 Step 2); the macro selector sorts on `evidence["score"]` (set by `_evidence`) — confirm `_evidence` includes `score` (it does: `"score": card.get("score")`).
- **Known:** Flow's 13F signal is institutional **breadth** (≥5 holders), not period-over-period accumulation (out of scope per spec).
