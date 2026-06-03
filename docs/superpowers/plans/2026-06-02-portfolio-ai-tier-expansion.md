# Portfolio AI — Tier Expansion + Promote to #1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Portfolio AI screen the actual knowledge graph (not the hardcoded 69-symbol `STOCK_DB`), give the user explicit control over scope via a tier selector, and promote the panel to position #1 on the AI Agent page.

**Architecture:** Add a `tier` parameter to `run_portfolio_pick(...)`. When provided, query `stocks_universe` joined with `stock_industry` to derive the symbol list instead of reading `STOCK_DB.keys()`. Keep the existing 69-symbol path as the "Mega-caps" preset so we don't regress the fast-path. Frontend gains a 4-button tier selector inline in the panel header (no hidden settings dropdown — visible state is critical when each tier dramatically changes wait time). Page reorders to put `<PortfolioPickPanel>` first.

**Tech Stack:** Python 3.11 (FastAPI + Pydantic v2), Next.js 15 + React 19 + Tailwind, SQLite via `src.utils.db`. No new dependencies.

**Decisions baked in (revise here if you disagree before executing):**
- **Default tier: `A` (160 stocks, ~4 min)** — first-time users hit "Run" expecting fast feedback. The 17-min A+B wait would feel broken. Power users will manually pick A+B for broader coverage.
- **Selector location: inline panel header** — visible state. The user must SEE how broad the screen is before clicking Run, because the scope drives wait time from 4 min → 50 min. Hiding it in a settings dropdown invites accidental long runs.
- **Keep the legacy 69-symbol path** as a "Mega-caps" preset (fastest, no DB query). Useful as the smoke-test mode.
- **Tier D not exposed** in the selector — it's 1,414 micro-caps, would push wait to ~73 min, and the Portfolio AI prompt isn't tuned for micro-caps.

---

## File Structure

**New files:**
- `tests/test_portfolio_universe.py` — tests for the new tier-based universe query

**Modified files:**
- `api/services/portfolio_agent_service.py` — add `_universe_for_tier()` + accept `tier` parameter on `run_portfolio_pick()` and `screen_universe()`
- `api/schemas.py:786-788` — add `tier` field to `PortfolioAgentRequest`
- `api/routes/agent.py:82-86` — pass `tier` through to the service
- `frontend/lib/api/types.ts` — add `PortfolioTier` type + extend the request body
- `frontend/lib/api/endpoints.ts:394-398` — accept + forward `tier` parameter
- `frontend/components/agent/portfolio-pick-panel.tsx` — tier selector chip row + wait-time hint
- `frontend/app/agent/page.tsx:130-138` — reorder so `<PortfolioPickPanel>` is first

---

## Task 1: Add a graph-aware universe query in the service

The current code hardcodes `STOCK_DB.keys()` at the top of `screen_universe`. We add a `_universe_for_tier(tier)` helper that returns the right symbol list for a named preset. `STOCK_DB` stays as the "mega" preset path so the fast option never breaks.

**Files:**
- Modify: `api/services/portfolio_agent_service.py` — insert helper near line 35, modify `screen_universe` (line 116) and `run_portfolio_pick` (line 255)
- Create: `tests/test_portfolio_universe.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_portfolio_universe.py`:

```python
"""Tests for the tier-based universe resolver in portfolio_agent_service."""
from __future__ import annotations

import pytest

from src.utils.db import get_connection, init_db


@pytest.fixture
def seeded_universe(tmp_path, monkeypatch):
    """Per-test temp DB with a synthetic universe across all 4 tiers."""
    from src.utils import db
    test_db = tmp_path / "t.db"
    monkeypatch.setattr(db, "DB_PATH", test_db)
    init_db()
    conn = get_connection()
    # 3 A-tier, 4 B-tier, 5 C-tier, 2 D-tier (synthetic symbols only)
    rows = (
        [("SYN_A1", "A"), ("SYN_A2", "A"), ("SYN_A3", "A")]
        + [("SYN_B1", "B"), ("SYN_B2", "B"), ("SYN_B3", "B"), ("SYN_B4", "B")]
        + [("SYN_C1", "C"), ("SYN_C2", "C"), ("SYN_C3", "C"), ("SYN_C4", "C"), ("SYN_C5", "C")]
        + [("SYN_D1", "D"), ("SYN_D2", "D")]
    )
    for sym, tier in rows:
        conn.execute(
            "INSERT INTO stocks_universe (symbol, name, tier, source) VALUES (?, ?, ?, 'test')",
            (sym, f"Test {sym}", tier),
        )
    conn.commit()
    conn.close()
    yield test_db


def test_universe_for_tier_a_only(seeded_universe):
    from api.services.portfolio_agent_service import _universe_for_tier
    out = _universe_for_tier("A")
    assert set(out) == {"SYN_A1", "SYN_A2", "SYN_A3"}


def test_universe_for_tier_ab(seeded_universe):
    from api.services.portfolio_agent_service import _universe_for_tier
    out = _universe_for_tier("A+B")
    assert len(out) == 7
    assert "SYN_A1" in out and "SYN_B4" in out
    assert "SYN_C1" not in out and "SYN_D1" not in out


def test_universe_for_tier_abc(seeded_universe):
    from api.services.portfolio_agent_service import _universe_for_tier
    out = _universe_for_tier("A+B+C")
    assert len(out) == 12
    assert "SYN_D1" not in out
    assert "SYN_D2" not in out


def test_universe_for_tier_mega_uses_stock_db(seeded_universe):
    """The 'mega' preset reads STOCK_DB, NOT the test universe."""
    from api.services.portfolio_agent_service import _universe_for_tier
    out = _universe_for_tier("mega")
    # Should match STOCK_DB keys (real mega-caps like AAPL), not synthetic test rows
    assert "AAPL" in out
    assert "SYN_A1" not in out


def test_universe_for_tier_unknown_raises(seeded_universe):
    from api.services.portfolio_agent_service import _universe_for_tier
    with pytest.raises(ValueError, match="unknown tier"):
        _universe_for_tier("X")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_portfolio_universe.py -v`
Expected: 5 FAILs with `ImportError: cannot import name '_universe_for_tier'`.

- [ ] **Step 3: Implement the helper**

Open `api/services/portfolio_agent_service.py`. Locate the import block (lines 14–22) and after the existing imports add:

```python
from src.utils.db import get_connection
```

Then insert this helper right above the `# ── Step 1 — screen the universe ─────` section header (around line 45):

```python
# ── Tier-based universe resolver ─────────────────────────────────────
#
# "mega"  — the legacy hardcoded 69 mega-caps (STOCK_DB). Fastest path.
# "A"     — Tier A from stocks_universe (~160 blue chips). Default.
# "A+B"   — Tier A+B (~1,022 stocks; S&P + Russell 1000 + QQQ + TSX 60).
# "A+B+C" — Tier A+B+C (~2,942 stocks; adds Russell 2000 small caps).
#
# Tier D is intentionally NOT exposed — it's 1,414 micro/SPAC names that
# push the screen past 60 minutes and aren't a fit for this prompt.

_VALID_TIERS = ("mega", "A", "A+B", "A+B+C")


def _universe_for_tier(tier: str) -> list[str]:
    """Return the list of symbols to screen for the given tier preset."""
    if tier == "mega":
        return list(STOCK_DB.keys())

    if tier not in _VALID_TIERS:
        raise ValueError(f"unknown tier {tier!r}; expected one of {_VALID_TIERS}")

    tier_set = {
        "A":      ("A",),
        "A+B":    ("A", "B"),
        "A+B+C":  ("A", "B", "C"),
    }[tier]

    placeholders = ",".join("?" for _ in tier_set)
    conn = get_connection()
    try:
        rows = conn.execute(
            f"""
            SELECT symbol FROM stocks_universe
            WHERE tier IN ({placeholders})
            ORDER BY CASE tier WHEN 'A' THEN 0 WHEN 'B' THEN 1 ELSE 2 END,
                     COALESCE(market_cap, 0) DESC
            """,
            tier_set,
        ).fetchall()
        return [r["symbol"] for r in rows]
    finally:
        conn.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_portfolio_universe.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add api/services/portfolio_agent_service.py tests/test_portfolio_universe.py
git commit -m "feat(agent): add tier-based universe resolver for Portfolio AI"
```

---

## Task 2: Plumb the `tier` parameter through screen_universe + run_portfolio_pick

`screen_universe` currently defaults to `STOCK_DB.keys()`. We make it tier-aware while keeping the existing `symbols=` override for callers that still pass an explicit list.

**Files:**
- Modify: `api/services/portfolio_agent_service.py` lines 116–132 and 255–268

- [ ] **Step 1: Update `screen_universe`**

Replace the function signature + body of `screen_universe` (line 116):

```python
def screen_universe(symbols: list[str] | None = None,
                    top_n: int = _SCREEN_TOP_N,
                    tier: str = "mega") -> list[dict]:
    """Screen the universe and return top-N candidates ranked by opportunity score.

    Resolution order for the symbol list:
      1. explicit `symbols=[...]` override (used by tests)
      2. `tier` preset → resolved via _universe_for_tier(tier)

    `tier` defaults to "mega" so existing callers (no tier kwarg passed) get
    the legacy 69-symbol behaviour unchanged.
    """
    init_db()
    universe = list(symbols) if symbols is not None else _universe_for_tier(tier)

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=_MAX_PARALLEL_SCREEN) as pool:
        for r in pool.map(_screen_one, universe):
            if r is not None:
                results.append(r)

    results.sort(
        key=lambda r: (r.get("opportunity") or {}).get("total", 0) or 0,
        reverse=True,
    )
    return results[:top_n]
```

- [ ] **Step 2: Update `run_portfolio_pick`**

Replace the function signature and the first few lines (line 255):

```python
def run_portfolio_pick(top_n: int = _SCREEN_TOP_N,
                       min_agents: int = _MIN_AGENTS_FOR_CONSENSUS,
                       tier: str = "A") -> dict:
    """Run the full live pipeline. Returns the result; does not execute trades."""
    candidates = screen_universe(top_n=top_n, tier=tier)
    universe = _universe_for_tier(tier)
    if not candidates:
        return {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "universe_size": len(universe),
            "tier": tier,
            "error": "No candidates passed screening",
            "candidates_screened": [],
            "agent_votes": [],
            "consensus_picks": [],
            "final_portfolio": [],
        }
```

Also replace the `"universe_size": len(STOCK_DB)` near line 313 with:

```python
        "universe_size": len(universe),
        "tier": tier,
```

(Add a local `universe = _universe_for_tier(tier)` before the return-dict if it's not already in scope — it is in the early-return path above, but the return dict is in the success path, so add it there too.)

Find the success-path return statement (around line 311) and ensure these two keys are present.

- [ ] **Step 3: Add a tier-roundtrip test**

Append to `tests/test_portfolio_universe.py`:

```python
def test_screen_universe_honors_tier_filter(seeded_universe, monkeypatch):
    """`tier='A'` only screens the 3 SYN_A* symbols. Use a stub _screen_one
    that returns a synthetic candidate so we don't hit yfinance."""
    from api.services import portfolio_agent_service as svc

    def fake_screen_one(symbol):
        return {
            "symbol": symbol, "sector": "Test",
            "snap": {"price": 10.0, "rsi": None, "macd_hist": None,
                     "sma_50": None, "sma_200": None,
                     "bb_upper": None, "bb_lower": None,
                     "vol_ratio": None, "change_5d": None, "change_20d": None,
                     "date": "2026-01-01"},
            "opportunity": {"total": 50, "label": "—", "strategy": "Neutral"},
            "signal_sum": {"bull": 0, "bear": 0, "alignment_pct": 0, "dominant": "neutral"},
        }

    monkeypatch.setattr(svc, "_screen_one", fake_screen_one)
    out = svc.screen_universe(top_n=10, tier="A")
    assert {c["symbol"] for c in out} == {"SYN_A1", "SYN_A2", "SYN_A3"}
```

- [ ] **Step 4: Run all portfolio-universe tests**

Run: `pytest tests/test_portfolio_universe.py -v`
Expected: 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add api/services/portfolio_agent_service.py tests/test_portfolio_universe.py
git commit -m "feat(agent): plumb tier parameter through screen_universe + run_portfolio_pick"
```

---

## Task 3: Surface `tier` in the FastAPI request schema + route

**Files:**
- Modify: `api/schemas.py:786-788`
- Modify: `api/routes/agent.py:82-86`

- [ ] **Step 1: Extend the request schema**

Replace `PortfolioAgentRequest` at `api/schemas.py:786`:

```python
class PortfolioAgentRequest(BaseModel):
    top_n: int = Field(default=15, ge=5, le=30)
    min_agents: int = Field(default=3, ge=2, le=7)
    # Universe preset. "mega" = legacy 69 mega-caps (fast); "A" = ~160 blue chips
    # from the graph (~4 min default); "A+B" = ~1,022 (~17 min); "A+B+C" = ~2,942.
    tier: str = Field(default="A", pattern="^(mega|A|A\\+B|A\\+B\\+C)$")
```

Also extend the response shape — find `PortfolioAgentResponse` (around line 838) and add a `tier: str | None = None` field so the UI can echo back what was actually run.

- [ ] **Step 2: Pass `tier` through the route**

Replace the body of `portfolio_pick` at `api/routes/agent.py:82`:

```python
@router.post("/portfolio-pick", response_model=PortfolioAgentResponse)
def portfolio_pick(req: PortfolioAgentRequest = PortfolioAgentRequest()) -> dict:
    return portfolio_agent_service.run_portfolio_pick(
        top_n=req.top_n, min_agents=req.min_agents, tier=req.tier,
    )
```

- [ ] **Step 3: Smoke-test the new param**

Restart uvicorn:

```bash
PID=$(ps aux | grep -E "uvicorn api.main" | grep -v grep | awk '{print $2}' | head -1)
kill "$PID" 2>/dev/null; sleep 1
nohup .venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000 > /tmp/uvicorn.log 2>&1 &
sleep 3
```

Then hit the endpoint with the legacy "mega" preset (fast, ~70-90s — same as today):

```bash
curl -sX POST http://127.0.0.1:8000/agent/portfolio-pick \
  -H "Content-Type: application/json" \
  -d '{"top_n": 5, "min_agents": 3, "tier": "mega"}' \
  | .venv/bin/python -c "import sys, json; d=json.load(sys.stdin); print('universe_size:', d.get('universe_size')); print('tier:', d.get('tier')); print('candidates:', len(d.get('candidates_screened', [])))"
```

Expected: `universe_size: 69 · tier: mega · candidates: 5`.

- [ ] **Step 4: Smoke-test Tier A**

```bash
curl -sX POST http://127.0.0.1:8000/agent/portfolio-pick \
  -H "Content-Type: application/json" \
  -d '{"top_n": 5, "min_agents": 3, "tier": "A"}' \
  | .venv/bin/python -c "import sys, json; d=json.load(sys.stdin); print('universe_size:', d.get('universe_size')); print('tier:', d.get('tier'))"
```

Expected: `universe_size: 160 · tier: A`. This run will take ~4 min — leave it running while you do Task 4 (frontend), and check on it after.

- [ ] **Step 5: Commit**

```bash
git add api/schemas.py api/routes/agent.py
git commit -m "feat(api): expose tier preset on /agent/portfolio-pick"
```

---

## Task 4: Frontend types + endpoint binding

**Files:**
- Modify: `frontend/lib/api/types.ts` (search for `PortfolioAgentResponse` / `PortfolioAgentRequest` — these may not exist as named types yet; the request is currently inline at the binding site)
- Modify: `frontend/lib/api/endpoints.ts:394-398`

- [ ] **Step 1: Add a `PortfolioTier` union type**

Open `frontend/lib/api/types.ts` and append at the end:

```ts
export type PortfolioTier = "mega" | "A" | "A+B" | "A+B+C";
```

If a `PortfolioAgentResponse` type already exists in this file, extend it with `tier?: PortfolioTier | null`. If not, that's fine — the response is consumed only inside the panel, where we'll cast inline.

- [ ] **Step 2: Update the endpoint binding**

Replace `portfolioPick` at `frontend/lib/api/endpoints.ts:394`:

```ts
  portfolioPick: (body: { top_n?: number; min_agents?: number; tier?: PortfolioTier } = {}) =>
    api.post<PortfolioAgentResponse>("/agent/portfolio-pick", {
      top_n: body.top_n ?? 15,
      min_agents: body.min_agents ?? 3,
      tier: body.tier ?? "A",
    }),
```

If `PortfolioTier` is unresolved, add it to the top-of-file `import type` block near `PortfolioAgentResponse`.

- [ ] **Step 3: Run the frontend typecheck**

Run: `cd frontend && npx tsc --noEmit 2>&1 | grep -E "portfolio|endpoints|types\.ts" | head -10`
Expected: no new errors. (Pre-existing project errors on other files are out of scope.)

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/api/types.ts frontend/lib/api/endpoints.ts
git commit -m "feat(frontend): wire tier param into portfolioPick endpoint binding"
```

---

## Task 5: Tier selector UI in the panel header

The selector is a 4-button chip row at the top of the panel. Each chip shows:
- The tier name ("A", "A+B", etc.)
- The approximate stock count
- The approximate wait time

Active selection is visually prominent (filled accent background). Below the selector, we show a one-line "About to screen N stocks · ~M min" hint so the user sees exactly what they're committing to before clicking Run.

**Files:**
- Modify: `frontend/components/agent/portfolio-pick-panel.tsx`

- [ ] **Step 1: Add the tier state + chip row at the top of the panel**

Open the panel component. Below the existing `const [topN, setTopN] = useState(15);` declarations (around line 45), add:

```ts
  const [tier, setTier] = useState<PortfolioTier>("A");
```

Add the import at the top of the file:

```ts
import type { PortfolioTier } from "@/lib/api/types";
```

Modify the mutation call to send the tier:

```ts
  const mutation = useMutation({
    mutationFn: (body: { top_n: number; min_agents: number; tier: PortfolioTier }) =>
      agentApi.portfolioPick(body),
  });
```

And the click handler that calls `mutation.mutate(...)` — wherever it lives in the panel, change the payload to include `tier`. (Search for `mutation.mutate(` in this file.)

- [ ] **Step 2: Render the chip row**

Insert this block at the very top of the panel's main render body (right after the panel header, before the existing controls). Estimate constants live in the component file as a top-level constant:

```tsx
const TIER_PRESETS: { tier: PortfolioTier; label: string; count: string; eta: string; }[] = [
  { tier: "mega",   label: "Mega-caps",  count: "~69",     eta: "~70-90s" },
  { tier: "A",      label: "Tier A",     count: "~160",    eta: "~4 min" },
  { tier: "A+B",    label: "Tier A+B",   count: "~1,022",  eta: "~17 min" },
  { tier: "A+B+C",  label: "Tier A+B+C", count: "~2,942",  eta: "~50 min" },
];
```

```tsx
{/* Tier selector */}
<div className="mb-3">
  <div className="text-[10px] uppercase tracking-wider text-text-muted font-mono mb-1.5">
    Universe
  </div>
  <div className="flex flex-wrap gap-1.5">
    {TIER_PRESETS.map((p) => {
      const active = tier === p.tier;
      return (
        <button
          key={p.tier}
          type="button"
          onClick={() => setTier(p.tier)}
          disabled={mutation.isPending}
          className={cn(
            "px-2.5 py-1.5 rounded-md border text-[11px] transition-colors flex items-baseline gap-1.5 font-mono",
            active
              ? "bg-accent-blue/15 border-accent-blue/50 text-accent-blue"
              : "bg-bg-card2 border-bg-border text-text-secondary hover:bg-bg-card",
            mutation.isPending && "opacity-50 cursor-not-allowed",
          )}
        >
          <span className="font-semibold">{p.label}</span>
          <span className="text-text-muted tabular-nums">{p.count}</span>
          <span className="text-text-dim tabular-nums">· {p.eta}</span>
        </button>
      );
    })}
  </div>
</div>
```

- [ ] **Step 3: Update the mutation call to pass `tier`**

Find the line inside the panel that triggers the mutation (it'll look something like `mutation.mutate({ top_n: topN, min_agents: minAgents })`). Replace with:

```ts
mutation.mutate({ top_n: topN, min_agents: minAgents, tier })
```

- [ ] **Step 4: Surface which tier was actually run in the result panel**

Wherever the success-state header renders (search for `result.universe_size`), add a small badge next to it:

```tsx
{result.tier && (
  <span className="badge badge-blue text-[10px] uppercase tracking-wider ml-2">
    Tier {result.tier === "mega" ? "Mega" : result.tier}
  </span>
)}
```

- [ ] **Step 5: Run the frontend in dev and click through**

```bash
ps aux | grep "next dev" | grep -v grep > /dev/null || (cd frontend && nohup npx next dev -p 3000 > /tmp/next.log 2>&1 &)
sleep 5
curl -s -o /dev/null -w "/agent HTTP %{http_code}\n" http://localhost:3000/agent
```

Then manually load `localhost:3000/agent` and verify:
- 4 tier chips appear at the top of the Portfolio AI panel
- "Tier A" is selected by default with blue highlight
- Clicking another tier swaps the highlight
- Clicking "Run Portfolio Pick" with "Mega-caps" selected completes in ~70-90s

- [ ] **Step 6: Commit**

```bash
git add frontend/components/agent/portfolio-pick-panel.tsx
git commit -m "feat(agent): tier selector chip row in Portfolio AI panel header"
```

---

## Task 6: Promote Portfolio AI to position #1 on the Agent page

**Files:**
- Modify: `frontend/app/agent/page.tsx:130-138`

- [ ] **Step 1: Reorder the sections**

Find lines 130-138 in `frontend/app/agent/page.tsx`. The current order is:

```tsx
<GapFinderCard />
<PortfolioStrategyReference />
<PortfolioPickPanel />
```

Change to:

```tsx
{/* Portfolio AI pick — marquee feature, screen graph + 7 agents vote */}
<PortfolioPickPanel />

{/* Gap Finder — AI portfolio adviser. Reads journal, runs trigger
    sensors, Claude judges with WebSearch/WebFetch enabled. */}
<GapFinderCard />

{/* Strategy reference — explains the portfolio AI pipeline */}
<PortfolioStrategyReference />
```

- [ ] **Step 2: Verify the page still renders**

```bash
curl -s -o /tmp/agent.html -w "HTTP %{http_code}\n" http://localhost:3000/agent
tail -10 /tmp/next.log | grep -iE "error" | grep -v "socket hang up\|ECONNREFUSED" | head -3 || echo "no errors"
```

Expected: `HTTP 200`, no compile errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/agent/page.tsx
git commit -m "feat(agent): promote Portfolio AI panel to position #1 on /agent"
```

---

## Task 7: End-to-end verification

- [ ] **Step 1: Run the full test suite**

```bash
.venv/bin/pytest tests/test_portfolio_universe.py tests/test_nasdaq_listings_loader.py -v
```

Expected: ALL PASS.

- [ ] **Step 2: Browser smoke test**

Open `localhost:3000/agent`:
1. Confirm Portfolio AI is now the first card on the page
2. Confirm the tier selector shows 4 chips at the top of the panel
3. Confirm "Tier A · ~160 · ~4 min" is highlighted by default
4. Click "Mega-caps" (fastest), then "Run Portfolio Pick"
5. After completion, confirm the result panel shows `universe_size: 69` and a "Tier Mega" badge
6. Click "Tier A", click Run again. Confirm the universe_size displays 160 after ~4 min

- [ ] **Step 3: Push**

```bash
git push origin main
```

---

## Self-Review Notes (post-write)

**Spec coverage check:**
- "Default tier" question → Task 1 defaults to `"A"` via `_universe_for_tier`; Task 3 hardcodes `"A"` as the schema default; Task 5 sets `useState<PortfolioTier>("A")` as the panel default. ✓
- "Selector location" question → Task 5 places the chip row inline at the top of the panel header (not a settings dropdown). ✓
- "Screen the whole graph" original ask → Tier A+B (1,022) and A+B+C (2,942) are user-selectable; "Tier A+B+C" is 43× the previous 69-symbol universe, satisfying the "search the whole graph" intent at a wait the user explicitly opts into. ✓
- "First in AI agents" original ask → Task 6 reorders. ✓

**Type-consistency check:**
- `_universe_for_tier(tier: str) -> list[str]` in service ↔ used by `screen_universe(tier=...)` and `run_portfolio_pick(tier=...)` ↔ exposed via `PortfolioAgentRequest.tier: str` (pydantic constrained) ↔ frontend `PortfolioTier = "mega" | "A" | "A+B" | "A+B+C"`. Matches. ✓
- The pydantic `pattern` literal `"^(mega|A|A\\+B|A\\+B\\+C)$"` escapes the `+` for regex; matches the four TS string literals. ✓

**Layer-rule check (CLAUDE.md):**
- `api/services/portfolio_agent_service.py` already imports from `src/data/` + `src/utils/db.py` — adding `get_connection` is consistent with the existing pattern.
- No new cross-layer violations.

**Test isolation:**
- `seeded_universe` fixture uses `monkeypatch.setattr(db, "DB_PATH", test_db)` — temp DB per test, doesn't touch production. ✓
- All synthetic symbols use the `SYN_*` prefix per CLAUDE.md test-isolation rule. ✓
- `test_universe_for_tier_mega_uses_stock_db` doesn't query the DB at all (STOCK_DB is a Python dict), so the test DB being seeded vs not doesn't matter. ✓

**Risk: A+B is ~17 min, A+B+C is ~50 min.** Users who click these without reading the wait estimate will think the app froze. Task 5 step 2 mitigates by labelling the eta on every chip; an enhancement worth deferring is showing a live progress bar (% of universe screened) so the wait feels grounded — see "Out of Scope" below.

---

## Out of Scope (deferred to later phases)

- **Background-job pipeline** for Portfolio AI runs so the user can navigate away and come back to results. Would require `refresh_jobs`-style polling. Worth doing if the user complains about the wait UX.
- **Cached opportunity scores** — pre-compute the screen nightly across A+B+C and store in a new table, so Portfolio AI reads the cache and only the 7 Claude calls remain. Would bring A+B+C from 50 min → 70-90s. This is the "Tier 2" idea from the original conversation; defer until you find yourself wanting it.
- **Tier D opt-in** — disabled by design today. Open a separate plan if you want micro-cap research workflows.
- **Watchlist mode** — "screen only my watchlist". Defer until the watchlist feature itself is more developed.
- **Cancel mid-run** — the underlying serial yfinance fetch isn't interruptible without backend work. Use the tier selector to opt into shorter runs instead.
