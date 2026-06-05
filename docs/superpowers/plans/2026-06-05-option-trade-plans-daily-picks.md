# Option Trade Plans for Daily Picks — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enrich the Daily Picks payload so each agent-picked stock carries a real-data bullish option trade plan — entry, exit-for-profit (target), exit-for-loss (ATR stop), R:R, technical support/resistance, and a best-effort suggested option contract — rendered on the daily-picks page.

**Architecture:** Two new **pure** analysis modules compute the levels and pick a contract from already-fetched data. A new gateway method exposes the options chain. A new orchestration service enriches the unique picked symbols (cheap technicals always; contract best-effort/nullable). `daily_picks_service` attaches an `option_plans: {symbol: plan}` map to its existing dict payload. The frontend renders the new fields. Agent generation is untouched.

**Tech Stack:** Python, Decimal (money), `src/analysis/technical.py`, `DataGateway` (Polygon options), pytest with injected fakes + temp DB; Next.js/React + TypeScript frontend.

**Reference spec:** `docs/superpowers/specs/2026-06-05-option-trade-plans-daily-picks-design.md`

**Conventions (match existing code):**
- `from __future__ import annotations` at top of new Python modules.
- Analysis layer is pure: no I/O, no imports from `data/`/`reports/`/`app`.
- Money as `Decimal`; serialized to **string** in the payload (mirrors `congress._trade_to_dict`).
- Errors → `log_api_call(...)` + return null/empty; never fabricate (CLAUDE.md).
- Tests: temp-DB fixture (autouse in `tests/conftest.py`), inject fakes, synthetic symbols (`SYN_*`), no network. Use `python3`.

---

## File Structure

- **Create:** `src/analysis/option_trade_plan.py` — pure level/R:R math.
- **Create:** `src/analysis/contract_selector.py` — pure contract pick from a chain.
- **Create:** `api/services/option_picks_service.py` — enrichment orchestration + cache.
- **Modify:** `src/data/gateway.py` — add `get_options_chain`.
- **Modify:** `api/services/daily_picks_service.py` — attach `option_plans` to payload.
- **Modify:** `frontend/lib/api/types.ts` — `OptionPlan` type + `option_plans` on the daily-picks response.
- **Modify:** `frontend/app/daily-picks/page.tsx` — render plans.
- **Create tests:** `tests/test_option_trade_plan.py`, `tests/test_contract_selector.py`, `tests/test_option_picks_service.py`, `tests/test_daily_picks_option_plans.py`.

---

## Task 1: Pure trade-plan math

**Files:**
- Create: `src/analysis/option_trade_plan.py`
- Test: `tests/test_option_trade_plan.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_option_trade_plan.py`:

```python
"""Pure tests for option_trade_plan.build_trade_plan (no I/O)."""
from __future__ import annotations

from decimal import Decimal

from src.analysis.option_trade_plan import build_trade_plan


def D(x):
    return Decimal(str(x))


def test_bullish_uses_resistance_as_target():
    p = build_trade_plan(direction="bullish", price=D(100), atr=D(2),
                          support=D(95), resistance=D(110))
    assert p["direction"] == "bullish"
    assert p["entry"] == D(100)
    assert p["stop_loss"] == D(96)          # 100 - 2*2
    assert p["take_profit"] == D(110)       # resistance, on profit side
    assert p["technical_target"] == D(110)
    assert p["rr_basis"] == "technical"
    assert p["rr_ratio"] == 2.5             # (110-100)/(100-96)


def test_bullish_broken_out_falls_back_to_ratio():
    # resistance below price (already broken out) -> 2:1 ratio target
    p = build_trade_plan(direction="bullish", price=D(100), atr=D(2),
                          support=D(95), resistance=D(98))
    assert p["rr_basis"] == "ratio"
    assert p["stop_loss"] == D(96)
    assert p["take_profit"] == D(108)       # 100 + 2*(100-96)
    assert p["rr_ratio"] == 2.0


def test_bearish_mirrors():
    p = build_trade_plan(direction="bearish", price=D(100), atr=D(2),
                          support=D(90), resistance=D(105))
    assert p["stop_loss"] == D(104)         # 100 + 2*2
    assert p["take_profit"] == D(90)        # support, on profit side
    assert p["rr_basis"] == "technical"
    assert p["rr_ratio"] == 2.5             # (100-90)/(104-100)


def test_zero_atr_yields_null_levels():
    p = build_trade_plan(direction="bullish", price=D(100), atr=D(0),
                          support=D(95), resistance=D(110))
    assert p["entry"] == D(100)
    assert p["stop_loss"] is None
    assert p["take_profit"] is None
    assert p["rr_ratio"] is None
    assert p["rr_basis"] is None


def test_none_atr_yields_null_levels():
    p = build_trade_plan(direction="bullish", price=D(100), atr=None,
                          support=D(95), resistance=D(110))
    assert p["stop_loss"] is None
    assert p["rr_ratio"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_option_trade_plan.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.analysis.option_trade_plan'`

- [ ] **Step 3: Implement**

Create `src/analysis/option_trade_plan.py`:

```python
"""Pure option trade-plan math: entry / stop / target / R:R from technicals.

Per CLAUDE.md: analysis layer is pure -- input values, output a dict. No I/O,
no imports from data/reports/app. Money is Decimal. Returns null levels rather
than dividing by zero or fabricating a target.
"""
from __future__ import annotations

from decimal import Decimal


def build_trade_plan(
    *,
    direction: str,
    price: Decimal,
    atr: Decimal | None,
    support: Decimal | None,
    resistance: Decimal | None,
    atr_mult: Decimal = Decimal("2"),
    rr_fallback: Decimal = Decimal("2"),
) -> dict:
    """Compute a directional trade plan.

    direction: "bullish" (target above, stop below) or "bearish" (mirror).
    Returns keys: direction, entry, stop_loss, take_profit, technical_target,
    rr_ratio, rr_basis. stop_loss/take_profit/rr_ratio are None when ATR is
    missing/non-positive (cannot place a stop). rr_basis is "technical" when the
    target is a real S/R level, "ratio" when it falls back to a fixed R:R, or
    None when levels are null.
    """
    plan = {
        "direction": direction,
        "entry": price,
        "stop_loss": None,
        "take_profit": None,
        "technical_target": None,
        "rr_ratio": None,
        "rr_basis": None,
    }
    if atr is None or atr <= 0:
        return plan

    if direction == "bearish":
        stop = price + atr_mult * atr
        tech = support if (support is not None and support < price) else None
        target = tech if tech is not None else price - rr_fallback * (stop - price)
        risk = stop - price
        reward = price - target
    else:  # bullish (default)
        stop = price - atr_mult * atr
        tech = resistance if (resistance is not None and resistance > price) else None
        target = tech if tech is not None else price + rr_fallback * (price - stop)
        risk = price - stop
        reward = target - price

    plan["stop_loss"] = stop
    plan["take_profit"] = target
    plan["technical_target"] = tech
    plan["rr_basis"] = "technical" if tech is not None else "ratio"
    if risk and risk != 0:
        plan["rr_ratio"] = round(float(reward / risk), 2)
    return plan
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_option_trade_plan.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/analysis/option_trade_plan.py tests/test_option_trade_plan.py
git commit -m "feat(analysis): pure option trade-plan math (entry/stop/target/RR)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Pure contract selector

**Files:**
- Create: `src/analysis/contract_selector.py`
- Test: `tests/test_contract_selector.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_contract_selector.py`:

```python
"""Pure tests for contract_selector.select_contract (no I/O)."""
from __future__ import annotations

from decimal import Decimal

from src.analysis.contract_selector import select_contract
from src.models.data_types import OptionContract, OptionsChain


def _contract(ctype, strike, exp, bid, ask, last, iv, delta):
    return OptionContract(
        symbol=f"{ctype}{strike}", underlying="SYN", contract_type=ctype,
        strike=Decimal(str(strike)), expiration=exp,
        bid=Decimal(str(bid)), ask=Decimal(str(ask)), last_price=Decimal(str(last)),
        volume=10, open_interest=100, implied_volatility=Decimal(str(iv)),
        delta=Decimal(str(delta)),
    )


def _chain(exp, calls, puts, price=100):
    return OptionsChain(underlying="SYN", underlying_price=Decimal(str(price)),
                        expiration=exp, calls=calls, puts=puts)


def _two_expiry_chains():
    # underlying at 100; two expiries, strikes 95/100/105
    near = _chain("2026-06-20", calls=[
        _contract("call", 95, "2026-06-20", 6, 6.4, 6.2, 0.30, 0.7),
        _contract("call", 100, "2026-06-20", 3, 3.4, 3.2, 0.28, 0.5),
        _contract("call", 105, "2026-06-20", 1, 1.4, 1.2, 0.27, 0.3),
    ], puts=[
        _contract("put", 100, "2026-06-20", 3, 3.4, 3.2, 0.29, -0.5),
    ])
    far = _chain("2026-08-21", calls=[
        _contract("call", 100, "2026-08-21", 5, 5.4, 5.2, 0.31, 0.55),
    ], puts=[])
    return [near, far]


def test_bullish_picks_nearest_dte_and_strike():
    # now=2026-06-01, dte_target=35 -> 2026-06-20 (19d) vs 2026-08-21 (81d):
    # |19-35|=16 < |81-35|=46 -> near expiry. Nearest strike to 100 -> 100.
    c = select_contract(_two_expiry_chains(), "bullish",
                        dte_target=35, now_date="2026-06-01")
    assert c is not None
    assert c["type"] == "call"
    assert c["strike"] == Decimal("100")
    assert c["expiry"] == "2026-06-20"
    assert c["premium"] == Decimal("3.2")   # mid of 3.0/3.4
    assert c["delta"] == Decimal("0.5")
    assert c["iv"] == Decimal("0.28")
    assert c["dte"] == 19


def test_bearish_picks_put():
    c = select_contract(_two_expiry_chains(), "bearish",
                        dte_target=35, now_date="2026-06-01")
    assert c is not None
    assert c["type"] == "put"
    assert c["strike"] == Decimal("100")


def test_empty_chains_returns_none():
    assert select_contract([], "bullish", now_date="2026-06-01") is None


def test_no_calls_returns_none_for_bullish():
    chain = _chain("2026-06-20", calls=[], puts=[
        _contract("put", 100, "2026-06-20", 3, 3.4, 3.2, 0.29, -0.5)])
    assert select_contract([chain], "bullish", now_date="2026-06-01") is None


def test_unpriced_contract_skipped():
    # only an unpriced call (bid/ask/last all 0) -> None
    chain = _chain("2026-06-20", calls=[
        _contract("call", 100, "2026-06-20", 0, 0, 0, 0.0, 0.5)], puts=[])
    assert select_contract([chain], "bullish", now_date="2026-06-01") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_contract_selector.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.analysis.contract_selector'`

- [ ] **Step 3: Implement**

Create `src/analysis/contract_selector.py`:

```python
"""Pure contract selection from an already-fetched options chain.

Per CLAUDE.md: analysis layer is pure -- operates on the passed OptionsChain
list, no network. Returns None (never a fabricated contract) when there is no
usable, priced contract on the needed side. `now_date` is injectable so DTE math
is deterministic in tests.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal


def _today(now_date: str | None) -> date:
    if now_date:
        return datetime.strptime(now_date, "%Y-%m-%d").date()
    return datetime.utcnow().date()


def _dte(expiration: str, today: date) -> int | None:
    try:
        return (datetime.strptime(expiration, "%Y-%m-%d").date() - today).days
    except Exception:
        return None


def _premium(c) -> Decimal | None:
    """Mid of bid/ask when both positive, else last_price when positive."""
    if c.bid and c.ask and c.bid > 0 and c.ask > 0:
        return (c.bid + c.ask) / 2
    if c.last_price and c.last_price > 0:
        return c.last_price
    return None


def select_contract(chains, direction: str, *, dte_target: int = 35,
                    now_date: str | None = None) -> dict | None:
    """Pick a near-the-money, priced contract on the side implied by direction.

    chains: list[OptionsChain] (one per expiration), as returned by
    DataGateway.get_options_chain. Bullish -> call, bearish -> put. Chooses the
    expiry whose DTE is closest to dte_target (only expiries that have a priced
    contract on the needed side), then the strike nearest the underlying price.
    Returns {type, strike, expiry, premium, delta, iv, dte} or None.
    """
    if not chains:
        return None
    today = _today(now_date)
    want = "put" if direction == "bearish" else "call"

    # Candidate expiries: those with at least one priced contract on our side.
    scored = []
    for ch in chains:
        side = ch.puts if want == "put" else ch.calls
        priced = [c for c in side if _premium(c) is not None]
        if not priced:
            continue
        d = _dte(ch.expiration, today)
        if d is None:
            continue
        scored.append((abs(d - dte_target), d, ch, priced))
    if not scored:
        return None

    scored.sort(key=lambda t: (t[0], t[1]))
    _, dte, chosen, priced = scored[0]
    price = chosen.underlying_price
    best = min(priced, key=lambda c: abs(c.strike - price))
    return {
        "type": want,
        "strike": best.strike,
        "expiry": chosen.expiration,
        "premium": _premium(best),
        "delta": best.delta,
        "iv": best.implied_volatility,
        "dte": dte,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_contract_selector.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/analysis/contract_selector.py tests/test_contract_selector.py
git commit -m "feat(analysis): pure near-the-money contract selector

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Expose the options chain on the gateway

**Files:**
- Modify: `src/data/gateway.py` (add method in the "Options & Level 2" section, right after `get_options_summary`, ~line 117)
- Test: `tests/test_gateway_options_chain.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_gateway_options_chain.py`:

```python
"""DataGateway.get_options_chain delegates to the polygon provider and
returns [] on any error (no fabrication)."""
from __future__ import annotations

from decimal import Decimal

from src.data.gateway import DataGateway
from src.models.data_types import OptionsChain


class _FakePolygon:
    def __init__(self, result=None, boom=False):
        self._result = result or []
        self._boom = boom

    def get_options_chain(self, symbol):
        if self._boom:
            raise RuntimeError("polygon 429 rate limit")
        return self._result


def test_get_options_chain_delegates(monkeypatch):
    gw = DataGateway()
    chain = OptionsChain(underlying="SYN", underlying_price=Decimal("100"),
                         expiration="2026-06-20")
    monkeypatch.setattr(gw, "_get_polygon", lambda: _FakePolygon([chain]))
    out = gw.get_options_chain("SYN")
    assert out == [chain]


def test_get_options_chain_returns_empty_on_error(monkeypatch):
    gw = DataGateway()
    monkeypatch.setattr(gw, "_get_polygon", lambda: _FakePolygon(boom=True))
    assert gw.get_options_chain("SYN") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_gateway_options_chain.py -v`
Expected: FAIL — `AttributeError: 'DataGateway' object has no attribute 'get_options_chain'`

- [ ] **Step 3: Implement**

In `src/data/gateway.py`, immediately after the `get_options_summary` method (before `get_microstructure`), add:

```python
    def get_options_chain(self, symbol: str) -> list[OptionsChain]:
        """Full options chain (one OptionsChain per expiration) from Polygon.

        Returns [] on any error (rate limit / no data) -- never fabricates.
        """
        try:
            return self._get_polygon().get_options_chain(symbol)
        except Exception:
            return []
```

Ensure `OptionsChain` is imported in `gateway.py`. Check the existing imports near the top; if `OptionsChain` is not already imported from `src.models.data_types`, add it to that import line. (`OptionsSummary` is already imported there — add `OptionsChain` alongside it.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_gateway_options_chain.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/data/gateway.py tests/test_gateway_options_chain.py
git commit -m "feat(data): expose get_options_chain on DataGateway

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Enrichment service

**Files:**
- Create: `api/services/option_picks_service.py`
- Test: `tests/test_option_picks_service.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_option_picks_service.py`:

```python
"""enrich_symbols builds {symbol: option_plan} from an injected gateway.

Temp-DB fixture (conftest) isolates the cache. No network."""
from __future__ import annotations

import pandas as pd

from api.services import option_picks_service
from src.models.data_types import OptionContract, OptionsChain
from src.utils.db import get_connection, init_db


def _df_uptrend():
    # 60 rows trending up; close ~100 at the end. Gives ATR + S/R.
    rows = []
    for i in range(60):
        base = 80 + i * 0.35
        rows.append({"date": f"2026-0{1+i//28}-{1+i%28:02d}",
                     "open": base, "high": base + 1.5, "low": base - 1.5,
                     "close": base, "volume": 1_000_000})
    return pd.DataFrame(rows)


def _chains():
    c = OptionContract(symbol="C100", underlying="SYN_AAA", contract_type="call",
                       strike=__import__("decimal").Decimal("100"),
                       expiration="2026-07-10",
                       bid=__import__("decimal").Decimal("3"),
                       ask=__import__("decimal").Decimal("3.4"),
                       last_price=__import__("decimal").Decimal("3.2"),
                       volume=10, open_interest=100,
                       implied_volatility=__import__("decimal").Decimal("0.3"),
                       delta=__import__("decimal").Decimal("0.5"))
    return [OptionsChain(underlying="SYN_AAA",
                         underlying_price=__import__("decimal").Decimal("100"),
                         expiration="2026-07-10", calls=[c], puts=[])]


class _FakeGateway:
    def __init__(self, *, chains=None, chain_boom=False):
        self._chains = chains if chains is not None else []
        self._chain_boom = chain_boom

    def get_historical(self, symbol, period_days=180):
        return _df_uptrend()

    def get_options_chain(self, symbol):
        if self._chain_boom:
            raise RuntimeError("rate limited")
        return self._chains


def test_enrich_builds_levels_and_contract():
    gw = _FakeGateway(chains=_chains())
    out = option_picks_service.enrich_symbols(["SYN_AAA"], gateway=gw)
    plan = out["SYN_AAA"]
    assert plan["direction"] == "bullish"
    assert plan["entry"] is not None
    assert plan["stop_loss"] is not None       # serialized as string
    assert plan["contract_status"] == "ok"
    assert plan["contract"]["type"] == "call"
    assert plan["contract"]["strike"] == "100"


def test_enrich_levels_present_when_contract_unavailable():
    gw = _FakeGateway(chains=[])               # no chain -> no contract
    out = option_picks_service.enrich_symbols(["SYN_BBB"], gateway=gw)
    plan = out["SYN_BBB"]
    assert plan["entry"] is not None           # levels still computed
    assert plan["contract"] is None
    assert plan["contract_status"] == "unavailable"


def test_enrich_contract_error_is_best_effort():
    gw = _FakeGateway(chain_boom=True)
    out = option_picks_service.enrich_symbols(["SYN_CCC"], gateway=gw)
    plan = out["SYN_CCC"]
    assert plan["contract"] is None
    assert plan["contract_status"] == "unavailable"
    assert plan["stop_loss"] is not None


def test_enrich_is_cached(monkeypatch):
    calls = {"n": 0}

    class CountingGateway(_FakeGateway):
        def get_historical(self, symbol, period_days=180):
            calls["n"] += 1
            return _df_uptrend()

    gw = CountingGateway(chains=_chains())
    option_picks_service.enrich_symbols(["SYN_DDD"], gateway=gw)
    first = calls["n"]
    option_picks_service.enrich_symbols(["SYN_DDD"], gateway=gw)
    assert calls["n"] == first                 # second call served from cache
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_option_picks_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'api.services.option_picks_service'`

- [ ] **Step 3: Implement**

Create `api/services/option_picks_service.py`:

```python
"""Enrich picked symbols with a real-data bullish option trade plan.

Orchestration (data + analysis), per CLAUDE.md -- lives in the service layer.
For each symbol: historical bars -> technical.analyze (price/ATR/support/
resistance) -> build_trade_plan; options chain -> select_contract (best-effort,
nullable). Decimals serialized to strings. Cached per symbol+day. No fabrication
-- any failure yields null contract (levels still computed) or omits the symbol.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from src.analysis import technical
from src.analysis.contract_selector import select_contract
from src.analysis.option_trade_plan import build_trade_plan
from src.utils.db import cache_get, cache_set, log_api_call

_CACHE_TTL_HOURS = 8
_DIRECTION = "bullish"  # agent daily picks are all BUY ideas


def _s(v) -> str | None:
    """Decimal/number -> string, passthrough None."""
    return None if v is None else str(v)


def _serialize_contract(c: dict | None) -> dict | None:
    if c is None:
        return None
    return {
        "type": c["type"],
        "strike": _s(c["strike"]),
        "expiry": c["expiry"],
        "premium": _s(c["premium"]),
        "delta": _s(c["delta"]),
        "iv": _s(c["iv"]),
        "dte": c["dte"],
    }


def _plan_for(symbol: str, gateway) -> dict | None:
    """Build one symbol's plan dict, or None if levels can't be computed."""
    try:
        df = gateway.get_historical(symbol, period_days=180)
    except Exception as exc:
        log_api_call("option_picks", symbol, "error", error=f"historical: {exc}")
        return None
    if df is None or len(df) < 20:
        return None

    ind = technical.analyze(symbol, df)
    if ind.current_price is None:
        return None

    plan = build_trade_plan(
        direction=_DIRECTION,
        price=ind.current_price,
        atr=ind.atr_14,
        support=ind.support,
        resistance=ind.resistance,
    )

    # Best-effort contract.
    contract = None
    try:
        chains = gateway.get_options_chain(symbol)
        contract = select_contract(chains, _DIRECTION) if chains else None
    except Exception as exc:
        log_api_call("option_picks", symbol, "error", error=f"chain: {exc}")
        contract = None

    return {
        "direction": plan["direction"],
        "entry": _s(plan["entry"]),
        "stop_loss": _s(plan["stop_loss"]),
        "take_profit": _s(plan["take_profit"]),
        "technical_target": _s(plan["technical_target"]),
        "support": _s(ind.support),
        "resistance": _s(ind.resistance),
        "atr": _s(ind.atr_14),
        "rr_ratio": plan["rr_ratio"],
        "rr_basis": plan["rr_basis"],
        "contract": _serialize_contract(contract),
        "contract_status": "ok" if contract is not None else "unavailable",
    }


def enrich_symbols(symbols: list[str], *, gateway=None) -> dict[str, dict]:
    """Return {symbol: plan} for the unique uppercased symbols. gateway is
    injectable for tests; defaults to a fresh DataGateway. Cached per symbol+day.
    Symbols whose levels can't be computed are omitted."""
    if gateway is None:
        from src.data.gateway import DataGateway
        gateway = DataGateway()

    today = date.today().isoformat()
    out: dict[str, dict] = {}
    seen = set()
    for raw in symbols:
        sym = (raw or "").upper().strip()
        if not sym or sym in seen:
            continue
        seen.add(sym)

        cache_key = f"option_plans:v1:{sym}:{today}"
        cached = cache_get(cache_key)
        if cached:
            out[sym] = cached
            continue

        plan = _plan_for(sym, gateway)
        if plan is not None:
            cache_set(cache_key, plan, ttl_minutes=_CACHE_TTL_HOURS * 60)
            out[sym] = plan
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_option_picks_service.py -v`
Expected: PASS (4 tests).

> Note: `cache_get`/`cache_set` store JSON-serializable dicts; the plan dict uses only str/None/number, so it round-trips cleanly. The `test_enrich_is_cached` test relies on the temp-DB `cache` table from the conftest fixture.

- [ ] **Step 5: Commit**

```bash
git add api/services/option_picks_service.py tests/test_option_picks_service.py
git commit -m "feat(api): option-picks enrichment service (best-effort contract)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Attach `option_plans` to the daily-picks payload

**Files:**
- Modify: `api/services/daily_picks_service.py` (in `get_daily_picks`, where `payload` is assembled, ~lines 135-150)
- Test: `tests/test_daily_picks_option_plans.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_daily_picks_option_plans.py`:

```python
"""get_daily_picks attaches option_plans for the unique picked symbols.

We stub the agent run + enrichment so no claude CLI / network is touched."""
from __future__ import annotations

import api.services.daily_picks_service as dps


def test_payload_includes_option_plans(monkeypatch):
    # Stub the 8-agent run with two agents picking overlapping symbols.
    fake_agents = [
        {"agent_key": "a1", "agent_name": "A1", "risk_tolerance": "",
         "picks": [{"symbol": "AAA", "rationale": "x", "conviction": "high"},
                   {"symbol": "BBB", "rationale": "y", "conviction": "med"}],
         "error": None},
        {"agent_key": "a2", "agent_name": "A2", "risk_tolerance": "",
         "picks": [{"symbol": "AAA", "rationale": "z", "conviction": "high"}],
         "error": None},
    ]
    monkeypatch.setattr(dps, "_run_one_agent",
                        lambda k, ctx: fake_agents[0] if k == "a1" else fake_agents[1])
    monkeypatch.setattr(dps, "AGENT_PERSONALITIES", {"a1": {"name": "A1"},
                                                     "a2": {"name": "A2"}})
    monkeypatch.setattr(dps, "_market_ctx", lambda: {})

    captured = {}

    def fake_enrich(symbols, **kw):
        captured["symbols"] = sorted(set(s.upper() for s in symbols))
        return {s.upper(): {"direction": "bullish", "entry": "100"}
                for s in symbols}

    import api.services.option_picks_service as ops
    monkeypatch.setattr(ops, "enrich_symbols", fake_enrich)

    payload = dps.get_daily_picks(force=True)
    assert "option_plans" in payload
    assert set(captured["symbols"]) == {"AAA", "BBB"}
    assert payload["option_plans"]["AAA"]["direction"] == "bullish"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_daily_picks_option_plans.py -v`
Expected: FAIL — `KeyError: 'option_plans'` (key not in payload yet).

- [ ] **Step 3: Implement**

In `api/services/daily_picks_service.py`, in `get_daily_picks`, AFTER the `payload` dict is built (after the line `"from_cache": False,` closing the dict) and BEFORE the `cache_set` block, insert:

```python
    # Enrich the unique picked symbols with a bullish option trade plan.
    # Best-effort: never break the picks payload if enrichment fails.
    try:
        from api.services import option_picks_service
        symbols: list[str] = []
        for a in agent_results:
            for pk in a.get("picks", []) or []:
                if isinstance(pk, dict) and pk.get("symbol"):
                    symbols.append(pk["symbol"])
        for row in consensus_payload.get("consensus", []):
            if row.get("symbol"):
                symbols.append(row["symbol"])
        for row in consensus_payload.get("contrarians", []):
            if row.get("symbol"):
                symbols.append(row["symbol"])
        payload["option_plans"] = option_picks_service.enrich_symbols(symbols)
    except Exception:
        payload["option_plans"] = {}
```

> The test monkeypatches `option_picks_service.enrich_symbols`, so the `from api.services import option_picks_service` import must resolve the module (it does) and the call goes through the patched attribute. Keep the import inside the try (lazy) to match the existing lazy-import style in this file.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_daily_picks_option_plans.py -v`
Expected: PASS.

- [ ] **Step 5: Run the related suites for no regression**

Run: `python3 -m pytest tests/test_daily_picks_option_plans.py tests/test_option_picks_service.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add api/services/daily_picks_service.py tests/test_daily_picks_option_plans.py
git commit -m "feat(api): attach option_plans map to daily-picks payload

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Frontend — types + render plans on the daily-picks page

**Files:**
- Modify: `frontend/lib/api/types.ts`
- Modify: `frontend/app/daily-picks/page.tsx`

> READ both files first. Match the existing component/styling patterns on the page (Tailwind classes, card layout, how a pick row is currently rendered). Do NOT restructure the page — add to it.

- [ ] **Step 1: Add the types**

In `frontend/lib/api/types.ts`, add an `OptionPlan` type and a `SuggestedContract` type, and add an optional `option_plans` field to whatever type models the `/daily-picks` response (find the existing daily-picks response type; if the response is currently typed loosely as `any`/`Record<string, unknown>`, add a dedicated `option_plans?: Record<string, OptionPlan>` where it's consumed):

```typescript
export interface SuggestedContract {
  type: "call" | "put";
  strike: string | null;
  expiry: string;
  premium: string | null;
  delta: string | null;
  iv: string | null;
  dte: number;
}

export interface OptionPlan {
  direction: "bullish" | "bearish";
  entry: string | null;
  stop_loss: string | null;
  take_profit: string | null;
  technical_target: string | null;
  support: string | null;
  resistance: string | null;
  atr: string | null;
  rr_ratio: number | null;
  rr_basis: "technical" | "ratio" | null;
  contract: SuggestedContract | null;
  contract_status: "ok" | "unavailable";
}
```

- [ ] **Step 2: Render the plan on each pick**

In `frontend/app/daily-picks/page.tsx`:
1. Read `option_plans` from the daily-picks response (`Record<string, OptionPlan>`, default `{}`).
2. For each pick (consensus, contrarian, and per-agent rows), look up `plans[symbol]` and, when present, render a compact block beneath/beside the ticker. Suggested layout (adapt to existing styles):

```tsx
{plan && (
  <div className="mt-1 text-xs grid grid-cols-3 gap-x-3 gap-y-0.5">
    <span className="inline-flex items-center rounded px-1.5 py-0.5 bg-emerald-900/40 text-emerald-300">
      {plan.direction === "bullish" ? "Calls" : "Puts"}
    </span>
    <span>Entry <b>{plan.entry ?? "—"}</b></span>
    <span>R:R <b>{plan.rr_ratio ?? "—"}</b></span>
    <span className="text-emerald-400">Exit ▲ {plan.take_profit ?? "—"}</span>
    <span className="text-red-400">Exit ▼ {plan.stop_loss ?? "—"}</span>
    <span className="text-zinc-400">
      S/R {plan.support ?? "—"}–{plan.resistance ?? "—"}
    </span>
    <span className="col-span-3 text-zinc-400">
      {plan.contract_status === "ok" && plan.contract
        ? `${plan.contract.type.toUpperCase()} ${plan.contract.strike} @ ${plan.contract.expiry} · prem ${plan.contract.premium ?? "—"} · IV ${plan.contract.iv ?? "—"}`
        : "options data unavailable"}
    </span>
  </div>
)}
```

3. Add a one-line disclaimer near the top of the picks section:

```tsx
<p className="text-[11px] text-zinc-500 mt-1">
  Option levels are model-derived from technicals for research only — not trading advice. Options carry substantial risk.
</p>
```

- [ ] **Step 3: Typecheck / build**

Run: `cd frontend && npx tsc --noEmit` (or `npm run lint` if tsc isn't wired).
Expected: no type errors from the new code. (If the project has a `npm run build`, prefer that, but tsc is faster.)

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/api/types.ts frontend/app/daily-picks/page.tsx
git commit -m "feat(frontend): show option trade plans on daily-picks page

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Full-suite regression check

**Files:** none (verification only)

- [ ] **Step 1: Run the new tests together**

Run:
```bash
python3 -m pytest tests/test_option_trade_plan.py tests/test_contract_selector.py \
  tests/test_gateway_options_chain.py tests/test_option_picks_service.py \
  tests/test_daily_picks_option_plans.py -v
```
Expected: all PASS.

- [ ] **Step 2: Run the broader Python suite (excluding pre-existing broken-collection files)**

The repo has 12 test files that fail to collect on `main` due to a missing third-party package (`ta`) — unrelated to this work. Run the rest:

```bash
python3 -m pytest tests/ -q \
  --ignore=tests/test_api.py \
  --ignore=tests/test_backtester_lookahead_integration.py \
  --ignore=tests/test_backtester_no_lookahead.py \
  --ignore=tests/test_causal_chain_news_integration.py \
  --ignore=tests/test_freshness.py \
  --ignore=tests/test_graph_relevance.py \
  --ignore=tests/test_neighborhood_api.py \
  --ignore=tests/test_news_impact_api.py \
  --ignore=tests/test_news_impact_graph_expansion.py \
  --ignore=tests/test_ownership_api.py \
  --ignore=tests/test_peer_api.py \
  --ignore=tests/test_universe_api.py
```
Expected: the new tests pass; pre-existing failures (the 14 seen on `main`: entity_aliases, institutions, sec_13f, integration/wave smoke — all from missing `ta`/data) are unchanged. No NEW failures attributable to this work. If a failure looks new, investigate before declaring done.

- [ ] **Step 3: Confirm no production-DB references in new tests**

Run:
```bash
grep -nE "trading\.db|DB_PATH|sqlite3\.connect" \
  tests/test_option_trade_plan.py tests/test_contract_selector.py \
  tests/test_gateway_options_chain.py tests/test_option_picks_service.py \
  tests/test_daily_picks_option_plans.py
```
Expected: no matches.

---

## Self-Review Notes (author)

- **Spec coverage:** levels math (T1), contract pick (T2), chain access (T3), enrichment + caching + best-effort/nullable contract (T4), payload attachment over unique symbols (T5), frontend render + disclaimer (T6), regression + data-integrity grep (T7). Direction fixed to bullish in the service (`_DIRECTION`) per spec; engine stays bidirectional (T1/T2 test bearish). Decimal-as-string serialization in T4.
- **Type consistency:** `build_trade_plan` keys (direction, entry, stop_loss, take_profit, technical_target, rr_ratio, rr_basis) are consumed verbatim in `_plan_for`. `select_contract` keys (type, strike, expiry, premium, delta, iv, dte) match `_serialize_contract` and the TS `SuggestedContract`. `OptionPlan` TS fields match the dict assembled in `_plan_for`. Gateway method name `get_options_chain` matches T3 + the call in T4.
- **Known seam:** the contract path depends on Polygon (free tier 5/min); T4 proves levels still render when the chain errors/empties (contract null, status "unavailable"). No silent fabrication.
```
