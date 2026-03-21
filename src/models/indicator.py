from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field


class SignalType(Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class Signal(BaseModel):
    name: str
    signal_type: SignalType
    description: str


class TechnicalIndicators(BaseModel):
    symbol: str
    timestamp: datetime

    # Trend
    sma_20: Decimal | None = None
    sma_50: Decimal | None = None
    sma_200: Decimal | None = None
    ema_12: Decimal | None = None
    ema_26: Decimal | None = None

    # Momentum
    rsi_14: Decimal | None = None
    macd: Decimal | None = None
    macd_signal: Decimal | None = None
    macd_histogram: Decimal | None = None
    stoch_k: Decimal | None = None
    stoch_d: Decimal | None = None

    # Volatility
    bb_upper: Decimal | None = None
    bb_middle: Decimal | None = None
    bb_lower: Decimal | None = None
    atr_14: Decimal | None = None

    # Volume
    avg_volume_20: int | None = None
    volume_trend: str = ""

    # Derived
    current_price: Decimal | None = None
    trend: str = ""
    support: Decimal | None = None
    resistance: Decimal | None = None
    signals: list[Signal] = Field(default_factory=list)

    @property
    def bullish_count(self) -> int:
        return sum(1 for s in self.signals if s.signal_type == SignalType.BULLISH)

    @property
    def bearish_count(self) -> int:
        return sum(1 for s in self.signals if s.signal_type == SignalType.BEARISH)

    @property
    def overall_signal(self) -> str:
        diff = self.bullish_count - self.bearish_count
        if diff >= 3:
            return "Strong Buy"
        if diff >= 1:
            return "Buy"
        if diff <= -3:
            return "Strong Sell"
        if diff <= -1:
            return "Sell"
        return "Neutral"
