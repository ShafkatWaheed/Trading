"""Tests for signal confluence detection module."""

from src.analysis.confluence import ConfluenceResult, SignalInput, analyze


def test_strong_agreement() -> None:
    """All signals pointing the same direction should produce strong_agreement."""
    signals = [
        SignalInput(name="technical", score=2, max_score=2, label="bullish"),
        SignalInput(name="fundamental", score=1, max_score=2, label="bullish"),
        SignalInput(name="smart_money", score=1, max_score=2, label="bullish"),
        SignalInput(name="sentiment", score=1, max_score=1, label="bullish"),
    ]

    result = analyze(signals)

    assert isinstance(result, ConfluenceResult)
    assert result.alignment == "strong_agreement"
    assert result.confidence_adjustment == 1
    assert len(result.agreements) > 0


def test_divergence() -> None:
    """Technical bullish but fundamental bearish at max scores should be divergent."""
    signals = [
        SignalInput(name="technical", score=2, max_score=2, label="bullish"),
        SignalInput(name="fundamental", score=-2, max_score=2, label="bearish"),
    ]

    result = analyze(signals)

    assert result.alignment == "divergent"
    assert result.confidence_adjustment == -1
    assert any("conflict" in w.lower() for w in result.warnings)


def test_mixed_signals() -> None:
    """A mix of bullish, bearish, and neutral should be mixed or moderate."""
    signals = [
        SignalInput(name="technical", score=1, max_score=2, label="bullish"),
        SignalInput(name="fundamental", score=-1, max_score=2, label="bearish"),
        SignalInput(name="smart_money", score=1, max_score=2, label="bullish"),
        SignalInput(name="sentiment", score=-1, max_score=1, label="bearish"),
    ]

    result = analyze(signals)

    # 2 bullish, 2 bearish => 50/50 split => mixed
    assert result.alignment in ("mixed", "divergent")
    assert len(result.divergences) > 0


def test_single_signal() -> None:
    """Only one signal should result in agreement by default."""
    signals = [
        SignalInput(name="technical", score=1, max_score=2, label="bullish"),
    ]

    result = analyze(signals)

    # 1 bullish out of 1 directional => 100% => strong_agreement
    assert result.alignment == "strong_agreement"
    assert result.confidence_adjustment == 1
