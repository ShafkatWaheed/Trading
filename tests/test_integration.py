"""Integration test: end-to-end stock analysis with live APIs.

Run with: pytest tests/test_integration.py -v -m integration
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.mark.integration
def test_analyze_stock_aapl():
    from src.orchestrator import analyze_stock

    report = analyze_stock("AAPL", export=False)

    assert report.symbol == "AAPL"
    assert report.verdict is not None
    assert report.confidence in ("High", "Medium", "Low")
    assert report.risk_rating is not None
    assert report.current_price > 0
    assert len(report.sections) >= 3
    assert report.DISCLAIMER != ""

    section_titles = [s.title for s in report.sections]
    assert "Company Overview" in section_titles
    assert "News Sentiment" in section_titles


@pytest.mark.integration
def test_analyze_stock_unknown_ticker():
    from src.orchestrator import analyze_stock

    report = analyze_stock("XYZNOTREAL", export=False)
    # Should still produce a report (with defaults), not crash
    assert report.symbol == "XYZNOTREAL"


@pytest.mark.integration
def test_gateway_quote():
    from src.data.gateway import DataGateway

    gw = DataGateway()
    stock = gw.get_stock("MSFT")
    assert stock.symbol == "MSFT"
    # At least quote or fundamentals should work
    assert stock.quote is not None or stock.fundamentals is not None


@pytest.mark.integration
def test_gateway_historical():
    from src.data.gateway import DataGateway

    gw = DataGateway()
    df = gw.get_historical("AAPL", period_days=30)
    assert df is not None
    assert len(df) > 0
    assert "close" in df.columns


@pytest.mark.integration
def test_gateway_news():
    from src.data.gateway import DataGateway

    gw = DataGateway()
    articles = gw.get_stock_news("TSLA")
    assert isinstance(articles, list)
    # Should get at least some articles
    assert len(articles) > 0
