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
