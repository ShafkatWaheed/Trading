"""Unit tests for macro regime analysis module."""

from datetime import datetime
from decimal import Decimal

from src.analysis.macro import analyze, MacroScore
from src.models.data_types import MacroSnapshot


def _make_snapshot(**overrides) -> MacroSnapshot:
    """Build a MacroSnapshot with normal defaults."""
    defaults = dict(
        timestamp=datetime(2026, 3, 22),
        fed_funds_rate=Decimal("3.5"),
        treasury_10y=Decimal("4.0"),
        treasury_2y=Decimal("3.5"),
        vix=Decimal("18"),
        unemployment_rate=Decimal("4.5"),
        gdp_growth=Decimal("2.0"),
        cpi_yoy=Decimal("2.5"),
    )
    defaults.update(overrides)
    return MacroSnapshot(**defaults)


def test_recession_warning() -> None:
    """Inverted yield curve (10Y < 2Y) should produce a negative score."""
    snap = _make_snapshot(
        treasury_10y=Decimal("3.0"),
        treasury_2y=Decimal("4.5"),  # inverted
        vix=Decimal("22"),           # slightly elevated but not extreme
    )
    assert snap.yield_curve_inverted, "Yield curve should be inverted"

    result = analyze(snap)
    assert result.score < 0, (
        f"Inverted yield curve should give negative score, got {result.score}"
    )
    assert any("yield curve" in f.lower() for f in result.factors), (
        "Should mention yield curve in factors"
    )


def test_high_volatility() -> None:
    """VIX > 30 should produce a negative score and high_volatility regime."""
    snap = _make_snapshot(vix=Decimal("40"))
    assert snap.regime == "high_volatility"

    result = analyze(snap)
    assert result.score < 0, (
        f"VIX > 35 should give negative score, got {result.score}"
    )
    assert any("vix" in f.lower() for f in result.factors), (
        "Should mention VIX in factors"
    )


def test_normal_regime() -> None:
    """All indicators in normal ranges should produce a score near 0."""
    snap = _make_snapshot(
        fed_funds_rate=Decimal("3.5"),    # between 2 and 5
        treasury_10y=Decimal("4.0"),
        treasury_2y=Decimal("3.5"),       # not inverted
        vix=Decimal("18"),                # between 15 and 25
        unemployment_rate=Decimal("4.5"), # between 4 and 6
        gdp_growth=Decimal("2.0"),        # between 0 and 3
    )
    result = analyze(snap)

    assert result.score == 0, (
        f"Normal indicators should give score ~0, got {result.score}"
    )
    assert result.regime == "normal"


def test_strong_labor() -> None:
    """Low unemployment (< 4%) should contribute a positive factor."""
    snap = _make_snapshot(
        unemployment_rate=Decimal("3.2"),
        fed_funds_rate=Decimal("3.5"),  # normal
        vix=Decimal("18"),              # normal
        gdp_growth=Decimal("2.0"),      # normal
    )
    result = analyze(snap)

    assert result.score > 0, (
        f"Strong labor market should give positive score, got {result.score}"
    )
    assert any("labor" in f.lower() or "unemployment" in f.lower() for f in result.factors), (
        "Should mention labor/unemployment in factors"
    )


def test_accommodative_policy_and_growth() -> None:
    """Low fed rate + strong GDP should be a tailwind."""
    snap = _make_snapshot(
        fed_funds_rate=Decimal("1.5"),
        gdp_growth=Decimal("4.0"),
        vix=Decimal("12"),                # low vol bonus
        unemployment_rate=Decimal("3.5"), # strong labor bonus
    )
    result = analyze(snap)

    assert result.score == 2, (
        f"Maximum tailwind conditions should cap at +2, got {result.score}"
    )


def test_everything_bad() -> None:
    """All negative signals should cap at -2."""
    snap = _make_snapshot(
        treasury_10y=Decimal("3.0"),
        treasury_2y=Decimal("4.5"),     # inverted
        vix=Decimal("40"),              # extreme fear
        fed_funds_rate=Decimal("6.0"),  # restrictive
        unemployment_rate=Decimal("7"), # weak labor
        gdp_growth=Decimal("-1"),       # contraction
    )
    result = analyze(snap)

    assert result.score == -2, (
        f"Maximum headwind should cap at -2, got {result.score}"
    )
