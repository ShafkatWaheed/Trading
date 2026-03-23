"""Technical analysis: compute indicators and generate signals."""

from datetime import datetime
from decimal import Decimal

import pandas as pd
import ta

from src.models.indicator import Signal, SignalType, TechnicalIndicators


def analyze(symbol: str, df: pd.DataFrame) -> TechnicalIndicators:
    """Run full technical analysis on historical price data.

    Args:
        symbol: Stock ticker.
        df: DataFrame with columns: date, open, high, low, close, volume.
    """
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    # Trend - Moving Averages
    sma_20 = ta.trend.sma_indicator(close, window=20)
    sma_50 = ta.trend.sma_indicator(close, window=50)
    sma_200 = ta.trend.sma_indicator(close, window=200)
    ema_12 = ta.trend.ema_indicator(close, window=12)
    ema_26 = ta.trend.ema_indicator(close, window=26)

    # Momentum
    rsi = ta.momentum.rsi(close, window=14)
    macd_line = ta.trend.macd(close)
    macd_signal = ta.trend.macd_signal(close)
    macd_hist = ta.trend.macd_diff(close)
    stoch = ta.momentum.stoch(high, low, close, window=14)
    stoch_signal = ta.momentum.stoch_signal(high, low, close, window=14)

    # Volatility
    bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
    atr = ta.volatility.average_true_range(high, low, close, window=14)

    # Get latest values
    latest = len(df) - 1
    current_price = Decimal(str(close.iloc[latest]))

    indicators = TechnicalIndicators(
        symbol=symbol,
        timestamp=datetime.utcnow(),
        current_price=current_price,
        sma_20=_dec(sma_20.iloc[latest]),
        sma_50=_dec(sma_50.iloc[latest]),
        sma_200=_dec(sma_200.iloc[latest]) if len(df) >= 200 else None,
        ema_12=_dec(ema_12.iloc[latest]),
        ema_26=_dec(ema_26.iloc[latest]),
        rsi_14=_dec(rsi.iloc[latest]),
        macd=_dec(macd_line.iloc[latest]),
        macd_signal=_dec(macd_signal.iloc[latest]),
        macd_histogram=_dec(macd_hist.iloc[latest]),
        stoch_k=_dec(stoch.iloc[latest]),
        stoch_d=_dec(stoch_signal.iloc[latest]),
        bb_upper=_dec(bb.bollinger_hband().iloc[latest]),
        bb_middle=_dec(bb.bollinger_mavg().iloc[latest]),
        bb_lower=_dec(bb.bollinger_lband().iloc[latest]),
        atr_14=_dec(atr.iloc[latest]),
        avg_volume_20=int(volume.tail(20).mean()),
    )

    # Determine trend
    if indicators.sma_50 and indicators.sma_200:
        if indicators.sma_50 > indicators.sma_200:
            indicators.trend = "uptrend"
        elif indicators.sma_50 < indicators.sma_200:
            indicators.trend = "downtrend"
        else:
            indicators.trend = "sideways"
    elif indicators.sma_20 and indicators.sma_50:
        if current_price > indicators.sma_50:
            indicators.trend = "uptrend"
        else:
            indicators.trend = "downtrend"

    # Volume trend
    recent_vol = volume.tail(5).mean()
    avg_vol = volume.tail(20).mean()
    if recent_vol > avg_vol * 1.2:
        indicators.volume_trend = "increasing"
    elif recent_vol < avg_vol * 0.8:
        indicators.volume_trend = "decreasing"
    else:
        indicators.volume_trend = "stable"

    # Support / Resistance (simple: recent low/high)
    indicators.support = _dec(low.tail(20).min())
    indicators.resistance = _dec(high.tail(20).max())

    # Generate signals
    indicators.signals = _generate_signals(indicators)

    return indicators


def _generate_signals(ind: TechnicalIndicators) -> list[Signal]:
    signals: list[Signal] = []

    # RSI
    if ind.rsi_14 is not None:
        if ind.rsi_14 > 70:
            signals.append(Signal(name="RSI", signal_type=SignalType.BEARISH, description="Overbought (RSI > 70)"))
        elif ind.rsi_14 < 30:
            signals.append(Signal(name="RSI", signal_type=SignalType.BULLISH, description="Oversold (RSI < 30)"))

    # MACD crossover
    if ind.macd_histogram is not None:
        if ind.macd_histogram > 0:
            signals.append(Signal(name="MACD", signal_type=SignalType.BULLISH, description="MACD above signal line"))
        else:
            signals.append(Signal(name="MACD", signal_type=SignalType.BEARISH, description="MACD below signal line"))

    # Price vs SMAs
    if ind.current_price and ind.sma_50:
        if ind.current_price > ind.sma_50:
            signals.append(Signal(name="SMA50", signal_type=SignalType.BULLISH, description="Price above SMA(50)"))
        else:
            signals.append(Signal(name="SMA50", signal_type=SignalType.BEARISH, description="Price below SMA(50)"))

    if ind.current_price and ind.sma_200:
        if ind.current_price > ind.sma_200:
            signals.append(Signal(name="SMA200", signal_type=SignalType.BULLISH, description="Price above SMA(200)"))
        else:
            signals.append(Signal(name="SMA200", signal_type=SignalType.BEARISH, description="Price below SMA(200)"))

    # Golden/Death cross
    if ind.sma_50 and ind.sma_200:
        if ind.sma_50 > ind.sma_200:
            signals.append(Signal(name="Cross", signal_type=SignalType.BULLISH, description="Golden cross (SMA50 > SMA200)"))
        else:
            signals.append(Signal(name="Cross", signal_type=SignalType.BEARISH, description="Death cross (SMA50 < SMA200)"))

    # Bollinger Bands
    if ind.current_price and ind.bb_lower and ind.bb_upper:
        if ind.current_price < ind.bb_lower:
            signals.append(Signal(name="BB", signal_type=SignalType.BULLISH, description="Price below lower Bollinger Band"))
        elif ind.current_price > ind.bb_upper:
            signals.append(Signal(name="BB", signal_type=SignalType.BEARISH, description="Price above upper Bollinger Band"))

    return signals


def _dec(value) -> Decimal | None:
    if pd.isna(value):
        return None
    return Decimal(str(round(float(value), 4)))
