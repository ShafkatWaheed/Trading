"""Deterministic Tier A/B/C/D classifier.

Pure function + thresholds — no I/O, no network, runnable offline. The actual
data inputs (market cap, ADV, index memberships) come from upstream loaders;
this module only decides which tier a given input maps to.

Rules (overridable via TierThresholds):

  Tier A — "tradeable spine"
      in_sp500 AND market_cap >= 50B AND avg_dollar_volume >= 250M
      OR explicitly seeded in tier_a_seed.py

  Tier B — "primary screening universe"
      in_sp500 OR in_russell1000 OR in_tsx60 OR in_qqq
      (i.e. any liquid mid-large cap not already in A)

  Tier C — "moderate liquidity"
      in_russell2000 OR (exchange in {NASDAQ-Global-Market, TSX-broad})

  Tier D — everything else (NASDAQ Capital, TSXV, CSE, OTC)

Usage:
    info = StockClassificationInputs(
        symbol="NVDA", market_cap=3.5e12, avg_dollar_volume=20e9,
        in_sp500=True, in_russell1000=True, in_qqq=True,
        in_russell2000=False, in_tsx60=False,
    )
    tier = classify_tier(info)         # "A"
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TierThresholds:
    """Thresholds for tier-A admission. Tunable; defaults sized for ~150 names."""

    a_market_cap_min: float = 50e9       # $50B
    a_dollar_volume_min: float = 250e6   # $250M average daily dollar volume


@dataclass(frozen=True)
class StockClassificationInputs:
    symbol: str
    market_cap: float | None = None
    avg_dollar_volume: float | None = None
    in_sp500: bool = False
    in_russell1000: bool = False
    in_russell2000: bool = False
    in_tsx60: bool = False
    in_qqq: bool = False
    nasdaq_market_tier: str | None = None  # "Global Select" | "Global Market" | "Capital Market"
    on_tsx_broad: bool = False             # senior TSX board, but not in TSX 60
    on_tsxv: bool = False
    on_cse: bool = False
    hand_seeded_tier_a: bool = False       # forced via tier_a_seed.py


def classify_tier(s: StockClassificationInputs, thresholds: TierThresholds | None = None) -> str:
    """Return 'A' | 'B' | 'C' | 'D' for the given stock's metadata."""
    th = thresholds or TierThresholds()

    # Override: hand-curated Tier A always wins.
    if s.hand_seeded_tier_a:
        return "A"

    # Tier A — quality threshold.
    if (
        s.in_sp500
        and (s.market_cap or 0) >= th.a_market_cap_min
        and (s.avg_dollar_volume or 0) >= th.a_dollar_volume_min
    ):
        return "A"

    # Tier B — any major-index member not already in A.
    if s.in_sp500 or s.in_russell1000 or s.in_tsx60 or s.in_qqq:
        return "B"

    # Tier C — Russell 2000 or NASDAQ Global Market or TSX broad.
    if s.in_russell2000:
        return "C"
    if s.nasdaq_market_tier in ("Global Select", "Global Market"):
        return "C"
    if s.on_tsx_broad:
        return "C"

    # Tier D — everything else.
    return "D"


def classify_universe(
    rows: list[StockClassificationInputs],
    thresholds: TierThresholds | None = None,
) -> dict[str, str]:
    """Classify a list of inputs in one shot. Returns {symbol: tier}."""
    return {row.symbol: classify_tier(row, thresholds) for row in rows}
