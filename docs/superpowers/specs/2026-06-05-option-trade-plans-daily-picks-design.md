# Option Trade Plans for Daily Picks — Design Spec

**Date:** 2026-06-05
**Status:** Approved (pending spec review)

## Goal

Enrich the existing **Daily Picks** page (8-agent "what to buy today" picks) so
each picked stock also shows an **option trade plan** computed from real market
data: a direction, an **entry** level, an **exit-for-profit** (target), an
**exit-for-loss** (stop), the **risk:reward** ratio, the underlying technical
support/resistance levels, and a **suggested option contract** (strike/expiry).

The agent pick-generation pipeline is unchanged. This adds an enrichment layer
plus a frontend rendering of the new fields.

## Core Constraint — Real Data Only (CLAUDE.md)

Every number shown is derived from real market data or is explicitly null. No
fabricated tickers, prices, levels, or contracts. When options-chain data is
unavailable for a symbol, the contract field is `null` and the UI shows
"options data unavailable" — never a made-up contract. This is decision-support
research output, not order execution and not financial advice; the UI carries
an options-risk disclaimer.

## Non-Goals (YAGNI)

- **No bearish/put plans on the agent-picks page.** Agents only generate BUY
  ideas, so every plan is bullish/call-oriented. (The analysis engine is still
  direction-parameterized for a possible future Discover hookup, but the
  daily-picks page passes `direction="bullish"` only.)
- **No order execution, no broker integration.**
- **No backtest** of these levels; the plan is a forward-looking snapshot "as of
  now," so there is no point-in-time/lookahead path to guarantee here.
- **No new options data provider** — reuse the existing Polygon + yfinance
  gateway path.
- **No change to how agents pick** (still 8 claude-CLI agents via
  `ask_claude_json`; $0 on the subscription — do not migrate to the SDK).

## Architecture

Agent generation stays as-is. A new enrichment layer computes plans for the
**unique** set of picked symbols and attaches them to the payload.

```
daily_picks_service.get_daily_picks()
   ├── (unchanged) 8 agents -> consensus/contrarians
   └── option_picks_service.enrich(unique_symbols)        [NEW orchestration]
          ├── DataGateway: quote + historical -> technical.analyze
          ├── DataGateway: options summary/chain
          ├── analysis/option_trade_plan.build_trade_plan(...)   [NEW pure]
          └── analysis/contract_selector.select_contract(...)    [NEW pure]
   -> payload["option_plans"] = { "AAPL": {plan}, ... }
```

Layer compliance: the two new modules under `src/analysis/` are **pure** (input
data, output dicts; no I/O, no imports from `data/`/`reports/`/`app`). All
fetching stays in the data layer via `DataGateway`. Orchestration (which calls
data + analysis) lives in `api/services/`, consistent with the existing
`daily_picks_service` / `discover_service` pattern.

## Components

### 1. `src/analysis/option_trade_plan.py` (NEW, pure)

```python
def build_trade_plan(
    *, direction: str, price: Decimal, atr: Decimal,
    support: Decimal | None, resistance: Decimal | None,
    atr_mult: Decimal = Decimal("2"), rr_fallback: Decimal = Decimal("2"),
) -> dict:
    """Compute entry/stop/target + R:R from technical inputs. Pure, no I/O.

    direction: "bullish" | "bearish".
    Returns {direction, entry, stop_loss, take_profit, technical_target,
             rr_ratio, rr_basis} where rr_basis is "technical" or "ratio".
    """
```

Rules (bullish; bearish mirrors):
- `entry = price`.
- `stop_loss = price - atr_mult*atr` (bullish) / `price + atr_mult*atr` (bearish).
- `technical_target = resistance` (bullish) / `support` (bearish) when that level
  is on the profit side of `entry` (resistance > entry / support < entry).
- If no usable technical level (None, or already broken through), set
  `take_profit = entry + rr_fallback*(entry-stop_loss)` (bullish) and
  `rr_basis = "ratio"`; else `take_profit = technical_target`,
  `rr_basis = "technical"`.
- `rr_ratio = (take_profit-entry)/(entry-stop_loss)` (bullish), rounded to 2dp.
- Guard: if `atr <= 0` or `entry-stop_loss == 0`, return a plan with
  `stop_loss=None, take_profit=None, rr_ratio=None` (cannot compute) rather than
  dividing by zero or fabricating. All money values are `Decimal`.

### 2. `src/analysis/contract_selector.py` (NEW, pure)

```python
def select_contract(chain, direction: str, *, dte_target: int = 35,
                     now_date: str | None = None) -> dict | None:
    """Pick a suggested contract from an ALREADY-FETCHED OptionsChain.

    Bullish -> a near-the-money call; bearish -> a near-the-money put.
    Chooses the listed expiry closest to dte_target days out, then the strike
    nearest the underlying price. Returns
    {type, strike, expiry, premium, delta, iv, dte} or None if the chain is
    empty / has no usable side / lacks priced contracts.
    """
```

- Operates only on the passed `OptionsChain` model (`src/models/data_types.py`);
  no network. `now_date` is injectable for deterministic DTE math in tests
  (avoids `Date.now()`-style nondeterminism).
- `premium` = mid of bid/ask when available, else last; `None`-safe.
- Returns `None` (not a guess) when calls/puts are missing or unpriced.

### 3. `api/services/option_picks_service.py` (NEW, orchestration)

```python
def enrich_symbols(symbols: list[str], *, gateway=None) -> dict[str, dict]:
    """Build {symbol: option_plan} for the given symbols. gateway injectable
    for tests. Best-effort per symbol: underlying levels always attempted;
    contract is best-effort (null on unavailable/rate-limited/illiquid).
    Cached per symbol+day."""
```

Per symbol:
1. `gw.get_quote` + `gw.get_historical` → `technical.analyze(...)` for
   `price, atr_14, support, resistance`. Direction = `"bullish"` (agent picks).
2. `build_trade_plan(...)` → levels.
3. `gw.get_options_summary(symbol)` and/or the chain → `select_contract(...)`.
   Wrapped in try/except: any failure (rate limit, no data) → `contract = None`,
   logged via `log_api_call("option_picks", symbol, "error", ...)`.
4. Assemble `{direction, entry, stop_loss, take_profit, technical_target,
   support, resistance, atr, rr_ratio, rr_basis, contract, contract_status}`
   where `contract_status` ∈ {"ok","unavailable"}.

Caching: `option_plans:v1:{symbol}:{today}` via `cache_get/cache_set`. Only the
**unique** symbol set (consensus + contrarians + each agent's picks, deduped) is
enriched — bounding Polygon free-tier (5/min) exposure. If the unique set is
large, contract lookups that fail on rate limits simply yield `null` contracts;
the page still renders levels.

### 4. `daily_picks_service.get_daily_picks` (MODIFY)

After consensus/contrarians are computed, collect the unique uppercased symbols
across `agents[*].picks[*].symbol` + consensus + contrarians, call
`option_picks_service.enrich_symbols(...)`, and add `payload["option_plans"]`
(a `{symbol: plan}` map). Wrapped so enrichment failure degrades to
`option_plans: {}` and never breaks the existing picks payload. The 8-hour
day-cache continues to wrap the whole payload (plans included).

### 5. Frontend `frontend/app/daily-picks/page.tsx` (MODIFY)

For each pick row (consensus, contrarian, and per-agent), look up
`option_plans[symbol]` and render: direction badge (Calls/Puts), **Entry**,
**Exit (profit)** = take_profit, **Exit (loss)** = stop_loss, **R:R**, small
"S/R: support–resistance" detail, and the suggested contract
(`TYPE strike exp` + premium/IV) or a muted "options data unavailable" when
`contract_status == "unavailable"`. Add a one-line options-risk disclaimer near
the section. Types updated in `frontend/lib/api/types.ts`; no new endpoint
(same `/daily-picks` payload).

## Error Handling & Data Integrity

- Missing/failed quote or historical → that symbol's plan is omitted from
  `option_plans` (frontend simply shows no plan for it); logged.
- `build_trade_plan` returns null levels rather than dividing by zero.
- `select_contract` returns `None` rather than guessing.
- No synthetic fallback anywhere; all gateway calls in try/except with
  `log_api_call`.
- Decimal for all money; serialized to string in the payload map (mirroring the
  congress adapter's `_trade_to_dict` Decimal-as-str convention) and parsed on
  the frontend.

## Testing (temp DB, injected gateway, no network)

1. **`tests/test_option_trade_plan.py`** — pure: bullish technical target;
   bullish broken-out → ratio fallback (`rr_basis="ratio"`); bearish mirror;
   `rr_ratio` math; `atr<=0` and `entry==stop` guards → null levels; Decimal in/out.
2. **`tests/test_contract_selector.py`** — synthetic `OptionsChain` fixture:
   selects nearest-DTE expiry + nearest strike; bullish→call, bearish→put;
   premium = mid; empty chain / missing side / unpriced → `None`;
   `now_date` injected for deterministic DTE.
3. **`tests/test_option_picks_service.py`** — fake gateway returns canned
   quote/historical/options; assert `enrich_symbols` shape, `contract_status`,
   that a gateway options failure yields `contract=None` but levels still
   present, and that caching avoids a second gateway call. Synthetic symbols
   (`SYN_*`), temp DB.

## Out of Scope / Follow-ups

- Wiring the (already bidirectional) engine to the Discover screener for true
  bearish/put plans.
- IV-rank-based contract quality filtering beyond basic liquidity.
