"""Shared dataclasses for sector-influence signals and information.

Two output shapes:
  - `StockInformation` — human-facing context. Used by all 15 sources.
  - `SignalReading`    — quant-facing numeric reading. Used ONLY by the
                         7 scored signals (FDA, gov contracts, ITC,
                         exec turnover, container rates, EIA, building
                         permits). Information sources MUST NOT emit
                         SignalReading.

Both carry as_of (when the underlying event is valid). SignalReading
additionally carries available_at (when a backtest can FIRST see it).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

Direction = Literal["bullish", "bearish", "neutral"]
Confidence = Literal["high", "med", "low"]
Severity = Literal["high", "med", "low"]


@dataclass(frozen=True)
class Fact:
    """A single dated fact backing a StockInformation entry."""
    text: str
    as_of: str                  # ISO 8601 UTC
    source: str                 # 'uspto' | 'openfda' | 'usaspending' | ...
    source_url: str | None
    confidence: float           # 0.0–1.0; 1.0 = authoritative ID match


@dataclass(frozen=True)
class StockInformation:
    """Display-only information about a stock, for cards and narratives.

    Emitted by all 15 sector-influence sources. NEVER used to score the
    Bubble Score or feed a backtest — use SignalReading for those.
    """
    ticker: str
    topic: str
    headline: str
    facts: list[Fact]
    narrative: str | None       # Claude-generated; None until generated
    implications: list[str]
    related_catalysts: list[str]
    confidence: Confidence
    as_of: str
    sources_used: list[str]
    severity: Severity          # used by Risk-narrative top-3 prioritization

    def __post_init__(self) -> None:
        if self.confidence not in ("high", "med", "low"):
            raise ValueError(f"invalid confidence: {self.confidence!r}")
        if self.severity not in ("high", "med", "low"):
            raise ValueError(f"invalid severity: {self.severity!r}")


@dataclass(frozen=True)
class SignalReading:
    """Quant-facing numeric reading for the 7 scored signals.

    Strict point-in-time discipline: backtester filters on `available_at`,
    never on `as_of`. Use Decimal for the value field — never float.
    """
    ticker: str | None
    sector: str | None
    signal_name: str
    value: Decimal
    z_score: Decimal | None
    direction: Direction
    confidence: Confidence
    as_of: str
    available_at: str
    point_in_time_lag_days: int
    source: str

    def __post_init__(self) -> None:
        if self.ticker is None and self.sector is None:
            raise ValueError("SignalReading requires ticker or sector")
        if not isinstance(self.value, Decimal):
            raise TypeError(
                f"SignalReading.value must be Decimal, got {type(self.value).__name__}"
            )
        if self.z_score is not None and not isinstance(self.z_score, Decimal):
            raise TypeError("SignalReading.z_score must be Decimal or None")
        if self.direction not in ("bullish", "bearish", "neutral"):
            raise ValueError(f"invalid direction: {self.direction!r}")
        if self.confidence not in ("high", "med", "low"):
            raise ValueError(f"invalid confidence: {self.confidence!r}")
        if self.available_at < self.as_of:
            raise ValueError(
                f"available_at ({self.available_at}) cannot be before as_of ({self.as_of})"
            )
        if self.point_in_time_lag_days < 0:
            raise ValueError("point_in_time_lag_days must be ≥ 0")
