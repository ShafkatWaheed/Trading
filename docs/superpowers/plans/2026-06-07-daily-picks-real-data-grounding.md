# Daily Picks Real-Data Grounding — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the daily-picks agents fabricating/refusing by giving each agent a real-data candidate screen (per-agent discovery), then a single Claude synthesis pass that ranks + writes rationale, with a deterministic fallback so the page is never empty when candidates exist.

**Architecture:** One `discover_service.get_opportunities` call provides the real-data scored universe. A new lens registry has each of the 8 agents independently *select* its candidates by its lens (6 lenses from the opportunity-card strategy/sub-score fields; `value`/`options` add a bounded gateway screen). A new synthesis module calls Claude to rank/dedupe/explain real candidates, falling back to the existing deterministic `compute_consensus_and_contrarian`. `daily_picks_service` orchestrates this in place of the cold prompt and stops caching empty payloads.

**Tech Stack:** Python, `discover_service`, `DataGateway`, `ask_claude_json` (claude CLI), pytest with injected fakes + temp DB. Use `python3`.

**Reference spec:** `docs/superpowers/specs/2026-06-07-daily-picks-real-data-grounding-design.md`

**Conventions:** `from __future__ import annotations`; analysis layer pure (no I/O); services may call data+analysis+claude; errors → `log_api_call` + degrade, never fabricate; tests use the autouse temp-DB fixture, inject fakes, synthetic symbols `SYN_*`, no network/LLM.

**Hard constraint:** Do NOT import, call, or modify `api/services/brief_service.py`. Candidate data comes only from `discover_service` + `DataGateway`.

---

## File Structure
- **Create:** `src/analysis/daily_picks_scoring.py` — pure conviction/ranking helpers.
- **Create:** `api/services/daily_picks_agents.py` — lens registry + `discover_for_agent`.
- **Create:** `api/services/daily_picks_synthesis.py` — Claude synthesis + deterministic fallback.
- **Modify:** `api/services/daily_picks_service.py` — orchestrate discovery+synthesis; cache fix; drop cold prompt.
- **Create tests:** `tests/test_daily_picks_scoring.py`, `tests/test_daily_picks_agents.py`, `tests/test_daily_picks_synthesis.py`; extend `tests/test_daily_picks_option_plans.py` usage in a new `tests/test_daily_picks_grounded_service.py`.

---

## Task 1: Pure scoring helpers

**Files:**
- Create: `src/analysis/daily_picks_scoring.py`
- Test: `tests/test_daily_picks_scoring.py`

- [ ] **Step 1: Write the failing test**

```python
"""Pure tests for daily_picks_scoring (no I/O)."""
from __future__ import annotations

from src.analysis.daily_picks_scoring import conviction_from_score, rank_candidates


def test_conviction_thresholds():
    assert conviction_from_score(85) == "high"
    assert conviction_from_score(70) == "high"
    assert conviction_from_score(69.9) == "med"
    assert conviction_from_score(45) == "med"
    assert conviction_from_score(44.9) == "low"
    assert conviction_from_score(0) == "low"
    assert conviction_from_score(None) == "low"


def test_rank_candidates_sorts_desc_and_truncates():
    cands = [{"symbol": "A", "score": 10}, {"symbol": "B", "score": 90},
             {"symbol": "C", "score": 50}]
    out = rank_candidates(cands, key="score", top_n=2)
    assert [c["symbol"] for c in out] == ["B", "C"]


def test_rank_candidates_stable_for_ties():
    cands = [{"symbol": "A", "score": 50}, {"symbol": "B", "score": 50}]
    out = rank_candidates(cands, key="score", top_n=5)
    assert [c["symbol"] for c in out] == ["A", "B"]  # input order preserved on ties
```

- [ ] **Step 2: Run — expect FAIL** (`ModuleNotFoundError`)

Run: `python3 -m pytest tests/test_daily_picks_scoring.py -v`

- [ ] **Step 3: Implement**

```python
"""Pure scoring/ranking helpers for daily picks. No I/O, no src imports beyond stdlib."""
from __future__ import annotations


def conviction_from_score(score: float | None) -> str:
    """Map a 0-100 opportunity score to high/med/low. None -> 'low'."""
    if score is None:
        return "low"
    s = float(score)
    if s >= 70:
        return "high"
    if s >= 45:
        return "med"
    return "low"


def rank_candidates(cands: list[dict], *, key: str, top_n: int) -> list[dict]:
    """Stable descending sort by `key` (missing/None -> 0), truncated to top_n."""
    ranked = sorted(cands, key=lambda c: float(c.get(key) or 0), reverse=True)
    return ranked[:top_n]
```

- [ ] **Step 4: Run — expect PASS** (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/analysis/daily_picks_scoring.py tests/test_daily_picks_scoring.py
git commit -m "feat(analysis): pure conviction/ranking helpers for daily picks

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Per-agent lens discovery

**Files:**
- Create: `api/services/daily_picks_agents.py`
- Test: `tests/test_daily_picks_agents.py`

**Context:** `discover_service.get_opportunities(...)` returns `{"opportunities": [card, ...]}` where each card has real fields incl. `symbol`, `score` (0-100), `strategy` (one of the 16 strategy names), `secondary_strategies` (list), `sub_scores` (`{volume, price, flow, risk_reward}`), `sector`, `price`. **Before coding, open `api/services/discover_service.py` and confirm these exact card keys** (esp. that the card has `"symbol"`). The 8 agent keys are `momentum, value, contrarian, macro, disruption, insider, options, flow`.

Six lenses select purely from the card fields (already real data, no extra calls). Two lenses (`value`, `options`) add a **bounded** gateway screen over the top candidates.

- [ ] **Step 1: Write the failing test**

```python
"""daily_picks_agents.discover_for_agent — deterministic, injected gateway."""
from __future__ import annotations

import pytest

from api.services import daily_picks_agents as dpa


def _card(symbol, strategy, score, sub_flow=0, secondary=None, sector="Tech"):
    return {"symbol": symbol, "strategy": strategy, "score": score,
            "secondary_strategies": secondary or [],
            "sub_scores": {"volume": 0, "price": 0, "flow": sub_flow, "risk_reward": 0},
            "sector": sector, "price": 100}


_OPPS = [
    _card("SYN_MOM", "Momentum", 88),
    _card("SYN_BRK", "Breakout", 75),
    _card("SYN_OVS", "Oversold Bounce", 62),
    _card("SYN_MR", "Mean Reversion", 55),
    _card("SYN_INS", "Insider Accumulation", 80),
    _card("SYN_CON", "Congress Buying", 71, sub_flow=90),
    _card("SYN_SEC", "Sector Leader", 66),
    _card("SYN_NEU", "Neutral", 40),
]


class _FakeGateway:
    """Returns canned fundamentals/options for value/options lenses."""
    def __init__(self, *, cheap={"SYN_MOM"}, bullish={"SYN_BRK"}):
        self._cheap, self._bullish = cheap, bullish

    def get_fundamentals(self, symbol):
        class F: pass
        f = F()
        # cheap symbols get a low PE + positive margin; others expensive
        f.pe_ratio = 12.0 if symbol in self._cheap else 90.0
        f.profit_margin = 0.2 if symbol in self._cheap else 0.2
        return f

    def get_options_summary(self, symbol):
        if symbol not in self._bullish:
            return None
        class O: pass
        o = O()
        o.put_call_ratio = 0.5  # bullish (<0.7)
        return o


def test_momentum_selects_momentum_family():
    picks = dpa.discover_for_agent("momentum", opportunities=_OPPS, gateway=_FakeGateway())
    syms = {p["symbol"] for p in picks}
    assert "SYN_MOM" in syms and "SYN_BRK" in syms
    assert "SYN_OVS" not in syms  # contrarian strategy, not momentum
    assert all("evidence" in p and "conviction" in p for p in picks)
    assert picks[0]["symbol"] == "SYN_MOM"  # ranked by score desc


def test_contrarian_selects_mean_reversion_family():
    picks = dpa.discover_for_agent("contrarian", opportunities=_OPPS, gateway=_FakeGateway())
    syms = {p["symbol"] for p in picks}
    assert syms == {"SYN_OVS", "SYN_MR"}


def test_insider_selects_insider_accumulation():
    picks = dpa.discover_for_agent("insider", opportunities=_OPPS, gateway=_FakeGateway())
    assert [p["symbol"] for p in picks] == ["SYN_INS"]


def test_value_uses_gateway_fundamentals():
    picks = dpa.discover_for_agent("value", opportunities=_OPPS,
                                   gateway=_FakeGateway(cheap={"SYN_MOM", "SYN_SEC"}))
    syms = {p["symbol"] for p in picks}
    assert syms <= {"SYN_MOM", "SYN_SEC"}  # only cheap-PE names survive
    assert "SYN_BRK" not in syms


def test_options_uses_gateway_bullish_flow():
    picks = dpa.discover_for_agent("options", opportunities=_OPPS,
                                   gateway=_FakeGateway(bullish={"SYN_OVS"}))
    assert [p["symbol"] for p in picks] == ["SYN_OVS"]


def test_unknown_agent_returns_empty():
    assert dpa.discover_for_agent("nope", opportunities=_OPPS, gateway=_FakeGateway()) == []


def test_gateway_error_in_value_yields_empty_not_crash():
    class Boom(_FakeGateway):
        def get_fundamentals(self, symbol):
            raise RuntimeError("rate limited")
    picks = dpa.discover_for_agent("value", opportunities=_OPPS, gateway=Boom())
    assert picks == []  # degrade, no crash
```

- [ ] **Step 2: Run — expect FAIL** (`ModuleNotFoundError`)

Run: `python3 -m pytest tests/test_daily_picks_agents.py -v`

- [ ] **Step 3: Implement**

```python
"""Per-agent candidate discovery for daily picks (service layer).

Each agent independently SELECTS its candidates from the real-data opportunity
cards (discover_service) by its lens; `value` and `options` add a bounded
gateway screen. Deterministic, no LLM. Returns up to _PICKS_PER_AGENT picks per
agent with the real evidence that justifies them. Per-agent errors degrade to
[] (never crash the run). No brief import.
"""
from __future__ import annotations

from src.analysis.daily_picks_scoring import conviction_from_score, rank_candidates

_PICKS_PER_AGENT = 5
_SHORTLIST = 15  # bound gateway calls for value/options lenses

# Lenses that select purely on the card 'strategy' field.
_STRATEGY_LENSES = {
    "momentum": {"Momentum", "Breakout", "Golden Cross", "Volume Spike", "Gap Fill"},
    "contrarian": {"Oversold Bounce", "Mean Reversion", "Support Bounce"},
    "macro": {"Sector Leader", "Dividend Play"},
    "disruption": {"Breakout", "Momentum", "Earnings Catalyst"},
    "insider": {"Insider Accumulation"},
    "flow": {"Congress Buying"},
}


def _evidence(card: dict) -> dict:
    return {
        "strategy": card.get("strategy"),
        "score": card.get("score"),
        "sub_scores": card.get("sub_scores"),
        "sector": card.get("sector"),
    }


def _pick(card: dict, extra: dict | None = None) -> dict:
    ev = _evidence(card)
    if extra:
        ev.update(extra)
    return {
        "symbol": card["symbol"],
        "evidence": ev,
        "conviction": conviction_from_score(card.get("score")),
    }


def _strategy_select(agent_key: str, opportunities: list[dict]) -> list[dict]:
    wanted = _STRATEGY_LENSES[agent_key]
    matched = [c for c in opportunities
               if c.get("strategy") in wanted
               or any(s in wanted for s in (c.get("secondary_strategies") or []))]
    top = rank_candidates(matched, key="score", top_n=_PICKS_PER_AGENT)
    return [_pick(c) for c in top]


def _value_select(opportunities: list[dict], gateway) -> list[dict]:
    """Cheap-valuation screen via real fundamentals over the top shortlist."""
    shortlist = rank_candidates(opportunities, key="score", top_n=_SHORTLIST)
    out = []
    for c in shortlist:
        f = gateway.get_fundamentals(c["symbol"])
        pe = getattr(f, "pe_ratio", None)
        margin = getattr(f, "profit_margin", None)
        if pe is not None and 0 < float(pe) <= 25 and (margin is None or float(margin) > 0):
            out.append(_pick(c, {"pe_ratio": float(pe)}))
    return out[:_PICKS_PER_AGENT]


def _options_select(opportunities: list[dict], gateway) -> list[dict]:
    """Bullish options flow (put/call < 0.7) via real options summary."""
    shortlist = rank_candidates(opportunities, key="score", top_n=_SHORTLIST)
    out = []
    for c in shortlist:
        summ = gateway.get_options_summary(c["symbol"])
        pcr = getattr(summ, "put_call_ratio", None) if summ else None
        if pcr is not None and float(pcr) < 0.7:
            out.append(_pick(c, {"put_call_ratio": float(pcr)}))
    return out[:_PICKS_PER_AGENT]


def discover_for_agent(agent_key: str, *, opportunities: list[dict], gateway) -> list[dict]:
    """Return up to 5 picks for one agent. Degrades to [] on any error."""
    try:
        if agent_key in _STRATEGY_LENSES:
            return _strategy_select(agent_key, opportunities)
        if agent_key == "value":
            return _value_select(opportunities, gateway)
        if agent_key == "options":
            return _options_select(opportunities, gateway)
        return []
    except Exception:
        return []
```

- [ ] **Step 4: Run — expect PASS** (7 tests)

- [ ] **Step 5: Commit**

```bash
git add api/services/daily_picks_agents.py tests/test_daily_picks_agents.py
git commit -m "feat(api): per-agent real-data candidate discovery for daily picks

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Claude synthesis with deterministic fallback

**Files:**
- Create: `api/services/daily_picks_synthesis.py`
- Test: `tests/test_daily_picks_synthesis.py`

**Context:** The existing `src/analysis/daily_picks_consensus.compute_consensus_and_contrarian(agent_results) -> {"consensus": [...], "contrarians": [...]}` is the deterministic fallback. `agent_results` items look like `{"agent_key","agent_name","risk_tolerance","picks":[{"symbol","rationale","conviction"}],"error"}`.

- [ ] **Step 1: Write the failing test**

```python
"""daily_picks_synthesis.synthesize — Claude ranking with deterministic fallback."""
from __future__ import annotations

import api.services.daily_picks_synthesis as syn


def _agents():
    return [
        {"agent_key": "momentum", "agent_name": "Momentum Trader", "risk_tolerance": "aggressive",
         "picks": [{"symbol": "AAA", "rationale": "", "conviction": "high"},
                   {"symbol": "BBB", "rationale": "", "conviction": "med"}], "error": None},
        {"agent_key": "insider", "agent_name": "Insider Shadow", "risk_tolerance": "moderate",
         "picks": [{"symbol": "AAA", "rationale": "", "conviction": "high"}], "error": None},
    ]


def test_synthesize_uses_claude_json_when_available(monkeypatch):
    def fake_json(prompt, **kw):
        return {"consensus": [{"symbol": "AAA", "agent_count": 2, "agents": ["momentum", "insider"],
                               "rationale": "Two lenses converge on AAA."}],
                "contrarians": [{"agent_key": "momentum", "agent_name": "Momentum Trader",
                                 "symbol": "BBB", "rationale": "Momentum's unique call.",
                                 "conviction": "med"}]}
    monkeypatch.setattr(syn, "ask_claude_json", fake_json)
    out = syn.synthesize(_agents(), {"vix": 15})
    assert out["consensus"][0]["symbol"] == "AAA"
    assert out["consensus"][0]["rationale"]
    assert out["contrarians"][0]["symbol"] == "BBB"


def test_synthesize_falls_back_when_claude_returns_none(monkeypatch):
    monkeypatch.setattr(syn, "ask_claude_json", lambda prompt, **kw: None)
    out = syn.synthesize(_agents(), {})
    # deterministic fallback: AAA picked by 2 agents -> consensus
    assert any(c["symbol"] == "AAA" for c in out["consensus"])
    assert "contrarians" in out


def test_synthesize_empty_agents_returns_empty(monkeypatch):
    monkeypatch.setattr(syn, "ask_claude_json", lambda prompt, **kw: None)
    out = syn.synthesize([], {})
    assert out == {"consensus": [], "contrarians": []}
```

- [ ] **Step 2: Run — expect FAIL** (`ModuleNotFoundError`)

Run: `python3 -m pytest tests/test_daily_picks_synthesis.py -v`

- [ ] **Step 3: Implement**

```python
"""Synthesis pass for daily picks: rank + consensus/contrarian + rationale.

Hands Claude the agents' REAL picks + evidence and asks it to rank/dedupe/explain
(never to invent), so it does not hit the 'refuse to fabricate' path. If the LLM
fails/parses empty, falls back to the deterministic compute_consensus_and_contrarian
so the page is never empty when candidates exist. No brief import.
"""
from __future__ import annotations

import json

from src.analysis.daily_picks_consensus import compute_consensus_and_contrarian
from src.utils.claude_cli import ask_claude_json
from src.utils.db import log_api_call


def _build_prompt(agent_results: list[dict], market_ctx: dict) -> str:
    lines = []
    for a in agent_results:
        picks = a.get("picks") or []
        if not picks:
            continue
        lines.append(f"{a.get('agent_name')} ({a.get('agent_key')}):")
        for p in picks:
            lines.append(f"  - {p['symbol']} [{p.get('conviction','')}] evidence={json.dumps(p.get('evidence') or {})}")
    body = "\n".join(lines)
    return f"""You are ranking REAL stock candidates already screened by 8 strategy agents.
Do NOT invent tickers — only use the symbols below. Use the evidence to rank.

Market context: {json.dumps(market_ctx or {})}

Agent picks:
{body}

Produce JSON only:
{{"consensus":[{{"symbol":"...","agent_count":N,"agents":["key",...],"rationale":"1-2 sentences citing the evidence"}}],
  "contrarians":[{{"agent_key":"...","agent_name":"...","symbol":"...","rationale":"...","conviction":"high|med|low"}}]}}
Consensus = symbols multiple agents independently picked, ranked by conviction+agent_count.
Contrarians = each agent's strongest pick no other agent chose.
"""


def synthesize(agent_results: list[dict], market_ctx: dict) -> dict:
    """Return {"consensus": [...], "contrarians": [...]}. Never raises."""
    has_picks = any((a.get("picks") for a in agent_results))
    if not has_picks:
        return {"consensus": [], "contrarians": []}

    try:
        result = ask_claude_json(_build_prompt(agent_results, market_ctx),
                                 model="haiku", timeout=120, retries=1)
        if isinstance(result, dict) and isinstance(result.get("consensus"), list):
            result.setdefault("contrarians", [])
            log_api_call("daily_picks_synth", "synthesize", "success")
            return {"consensus": result["consensus"], "contrarians": result["contrarians"]}
    except Exception as exc:
        log_api_call("daily_picks_synth", "synthesize", "error", error=str(exc)[:200])

    # Deterministic fallback — guarantees non-empty when agents have picks.
    log_api_call("daily_picks_synth", "synthesize", "fallback")
    return compute_consensus_and_contrarian(agent_results)
```

- [ ] **Step 4: Run — expect PASS** (3 tests)

- [ ] **Step 5: Commit**

```bash
git add api/services/daily_picks_synthesis.py tests/test_daily_picks_synthesis.py
git commit -m "feat(api): Claude synthesis for daily picks with deterministic fallback

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Rewire daily_picks_service (discovery + synthesis + cache fix)

**Files:**
- Modify: `api/services/daily_picks_service.py`
- Test: `tests/test_daily_picks_grounded_service.py`

**Context:** READ `api/services/daily_picks_service.py` first. Today `get_daily_picks` runs `_run_one_agent` (cold `ask_claude_json` "pick 5") per agent via `ThreadPoolExecutor`, then `compute_consensus_and_contrarian`, then (from the option_plans work) attaches `option_plans`, then `cache_set`. You will: replace the per-agent cold call with `daily_picks_agents.discover_for_agent`, replace consensus with `daily_picks_synthesis.synthesize`, and guard the cache. Keep `agent_results` shape and the option_plans block intact.

- [ ] **Step 1: Write the failing test**

```python
"""get_daily_picks produces non-empty grounded picks and doesn't cache empties."""
from __future__ import annotations

import api.services.daily_picks_service as dps
from src.utils.db import get_connection, init_db


def _fake_opps():
    return {"opportunities": [
        {"symbol": "AAA", "strategy": "Momentum", "score": 88,
         "secondary_strategies": [], "sub_scores": {}, "sector": "Tech", "price": 100},
        {"symbol": "BBB", "strategy": "Insider Accumulation", "score": 80,
         "secondary_strategies": [], "sub_scores": {}, "sector": "Tech", "price": 50},
    ]}


def _clear_cache():
    init_db()
    c = get_connection(); c.execute("DELETE FROM cache WHERE key LIKE 'daily_picks:%'")
    c.commit(); c.close()


def test_grounded_picks_non_empty(monkeypatch):
    _clear_cache()
    import api.services.discover_service as disc
    monkeypatch.setattr(disc, "get_opportunities", lambda **kw: _fake_opps())
    monkeypatch.setattr(dps, "_market_ctx", lambda: {})
    # synthesis stubbed to deterministic-ish output so no claude call
    import api.services.daily_picks_synthesis as syn
    monkeypatch.setattr(syn, "synthesize",
                        lambda agents, ctx: {"consensus": [{"symbol": "AAA", "agent_count": 1,
                                                            "agents": ["momentum"], "rationale": "r"}],
                                             "contrarians": []})
    # avoid real option enrichment network
    import api.services.option_picks_service as ops
    monkeypatch.setattr(ops, "enrich_symbols", lambda syms, **kw: {})

    payload = dps.get_daily_picks(force=True)
    assert payload["consensus"][0]["symbol"] == "AAA"
    # at least one agent surfaced a pick
    assert any(a["picks"] for a in payload["agents"])


def test_empty_run_not_cached(monkeypatch):
    _clear_cache()
    import api.services.discover_service as disc
    monkeypatch.setattr(disc, "get_opportunities", lambda **kw: {"opportunities": []})
    monkeypatch.setattr(dps, "_market_ctx", lambda: {})
    import api.services.daily_picks_synthesis as syn
    monkeypatch.setattr(syn, "synthesize", lambda agents, ctx: {"consensus": [], "contrarians": []})
    import api.services.option_picks_service as ops
    monkeypatch.setattr(ops, "enrich_symbols", lambda syms, **kw: {})

    payload = dps.get_daily_picks(force=True)
    assert payload["consensus"] == []
    c = get_connection()
    row = c.execute("SELECT COUNT(*) FROM cache WHERE key LIKE 'daily_picks:%'").fetchone()[0]
    c.close()
    assert row == 0  # empty payload must NOT be cached
```

- [ ] **Step 2: Run — expect FAIL** (consensus empty / cache present, since old code still runs cold agents)

Run: `python3 -m pytest tests/test_daily_picks_grounded_service.py -v`

- [ ] **Step 3: Implement**

Make these edits to `api/services/daily_picks_service.py`:

3a. Update imports near the top (add discover + the two new modules; keep existing):
```python
from api.services import daily_picks_agents, daily_picks_synthesis
```
(Leave the existing `from src.personalities import AGENT_PERSONALITIES`, `ask_claude_json`, `cache_get/cache_set` imports.)

3b. Replace `_run_one_agent` with a discovery-based version (keep the same return shape):
```python
def _run_one_agent(agent_key: str, ctx: dict, opportunities: list[dict]) -> dict:
    """Discover this agent's picks from real data. Returns the agent_results shape."""
    p = AGENT_PERSONALITIES[agent_key]
    from src.data.gateway import DataGateway
    try:
        raw = daily_picks_agents.discover_for_agent(
            agent_key, opportunities=opportunities, gateway=DataGateway())
        picks = [{"symbol": r["symbol"], "rationale": "",
                  "conviction": r.get("conviction", ""), "evidence": r.get("evidence", {})}
                 for r in raw]
        return {"agent_key": agent_key, "agent_name": p["name"],
                "risk_tolerance": p.get("risk_tolerance", ""), "picks": picks, "error": None}
    except Exception as e:
        return {"agent_key": agent_key, "agent_name": p["name"],
                "risk_tolerance": p.get("risk_tolerance", ""), "picks": [], "error": str(e)[:200]}
```

3c. In `get_daily_picks`, fetch opportunities once before the agent loop, pass to `_run_one_agent`, and replace the consensus computation with synthesis. Find the block that builds `agent_results` via the ThreadPoolExecutor and the `compute_consensus_and_contrarian` call; replace with:
```python
    ctx = _market_ctx()
    from api.services import discover_service
    opportunities = (discover_service.get_opportunities(limit=60, period="1M") or {}).get("opportunities", [])

    agents = list(AGENT_PERSONALITIES.keys())
    agent_results: list[dict] = []
    with ThreadPoolExecutor(max_workers=_MAX_PARALLEL) as pool:
        futures = {pool.submit(_run_one_agent, k, ctx, opportunities): k for k in agents}
        for f in as_completed(futures):
            agent_results.append(f.result())
    order = {k: i for i, k in enumerate(agents)}
    agent_results.sort(key=lambda r: order.get(r["agent_key"], 999))

    consensus_payload = daily_picks_synthesis.synthesize(agent_results, ctx)
```
(Keep the existing `payload = {...}` dict that reads `consensus_payload.get("consensus", [])` / `("contrarians", [])`, and keep the `option_plans` enrichment block unchanged.)

3d. Guard the cache — replace the existing `cache_set(...)` block at the end with:
```python
    has_picks = bool(payload.get("consensus")) or any(a.get("picks") for a in agent_results)
    if has_picks:
        try:
            cache_set(cache_key, payload, ttl_minutes=_CACHE_TTL_HOURS * 60)
        except Exception:
            pass
    return payload
```

3e. Delete the now-dead `_build_agent_prompt` function (the cold fabrication prompt). Confirm nothing else references it (`grep -rn "_build_agent_prompt" api/ src/ tests/` → only its definition).

- [ ] **Step 4: Run the new + adjacent tests**

Run: `python3 -m pytest tests/test_daily_picks_grounded_service.py tests/test_daily_picks_option_plans.py tests/test_daily_picks_agents.py tests/test_daily_picks_synthesis.py -v`
Expected: all PASS. (If `test_daily_picks_option_plans.py` monkeypatches `_run_one_agent` with the old 2-arg signature, update that test's stub to the new `(k, ctx, opportunities)` signature — keep its intent.)

- [ ] **Step 5: Commit**

```bash
git add api/services/daily_picks_service.py tests/test_daily_picks_grounded_service.py tests/test_daily_picks_option_plans.py
git commit -m "feat(api): ground daily picks in real data via discovery + synthesis; stop caching empties

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Regression check

**Files:** none (verification only)

- [ ] **Step 1: New + related tests**

Run:
```bash
python3 -m pytest tests/test_daily_picks_scoring.py tests/test_daily_picks_agents.py \
  tests/test_daily_picks_synthesis.py tests/test_daily_picks_grounded_service.py \
  tests/test_daily_picks_option_plans.py -v
```
Expected: all PASS.

- [ ] **Step 2: Broader suite (exclude pre-existing broken/hanging files)**

Run (exclude the integration suite that makes live calls + the 12 `ta`-collection-error files):
```bash
python3 -m pytest tests/ -q -p no:cacheprovider \
  --ignore=tests/test_integration.py \
  --ignore=tests/test_api.py --ignore=tests/test_backtester_lookahead_integration.py \
  --ignore=tests/test_backtester_no_lookahead.py --ignore=tests/test_causal_chain_news_integration.py \
  --ignore=tests/test_freshness.py --ignore=tests/test_graph_relevance.py \
  --ignore=tests/test_neighborhood_api.py --ignore=tests/test_news_impact_api.py \
  --ignore=tests/test_news_impact_graph_expansion.py --ignore=tests/test_ownership_api.py \
  --ignore=tests/test_peer_api.py --ignore=tests/test_universe_api.py
```
Expected: new tests pass; only the known pre-existing failures remain (entity_aliases, institutions_seed_loader, sec_13f_loader, sentiment, wave1/wave2 smoke). No NEW failures attributable to this work.

- [ ] **Step 3: Data-integrity grep on new tests**

```bash
grep -nE "trading\.db|DB_PATH|sqlite3\.connect" tests/test_daily_picks_*.py
```
Expected: no matches.

---

## Self-Review Notes (author)

- **Spec coverage:** per-agent discovery (T2, 6 strategy lenses + value/options gateway screens), synthesis + deterministic fallback (T3), service rewire + cache fix + dead-prompt removal (T4), pure scoring (T1), regression (T5). Brief never imported. option_plans block preserved (T4). Payload shape kept; `evidence`/`conviction` additive.
- **Type/shape consistency:** `discover_for_agent(agent_key, *, opportunities, gateway) -> list[{symbol, evidence, conviction}]` consumed verbatim in `_run_one_agent`. `synthesize(agent_results, market_ctx) -> {consensus, contrarians}` consumed verbatim where `consensus_payload` is read. `agent_results` item shape matches `compute_consensus_and_contrarian`'s expected input and the option_plans symbol-collection (`a["picks"][*]["symbol"]`).
- **Known seams flagged for the implementer:** confirm the opportunity-card keys in discover_service (esp. `symbol`); update the old `_run_one_agent` stub in `test_daily_picks_option_plans.py` to the new 3-arg signature.
- **Deferred:** Estimate-Revisions + Analyst-Consensus agents (need Finnhub→gateway wiring) — not in this plan.
