"""Trading Agent Personalities — defines how each agent thinks and trades.

Each personality has:
- A trading philosophy (what they prioritize)
- Preferred indicators (what signals they trust)
- Backtest signals (which signals to validate their picks)
- Risk tolerance (how aggressive they are)
"""

AGENT_PERSONALITIES = {
    "momentum": {
        "name": "Momentum Trader",
        "icon": "🚀",
        "color": "#22c55e",
        "tagline": "Ride the wave — buy strength, sell weakness",
        "philosophy": (
            "Believes stocks in motion stay in motion. Buys stocks making new highs "
            "with accelerating volume. Loves disruption themes and doesn't care about "
            "P/E ratios — expensive stocks going up are the best trades."
        ),
        "strengths": ["Catches big moves early", "Thrives in bull markets", "Finds disruption winners"],
        "weaknesses": ["Gets crushed in reversals", "Overpays for growth", "Late to exit"],
        "prioritizes": ["Technical momentum (RSI 50-80)", "Disruption themes", "Volume acceleration", "Breakouts above resistance", "Relative strength vs S&P"],
        "avoids": ["Low P/E value traps", "Dividend stocks", "Stocks below SMA50"],
        "backtest_signals": ["rsi_oversold", "macd_bullish", "golden_cross", "volume_spike", "sma50_cross_up"],
        "risk_tolerance": "aggressive",
        "ideal_market": "Bull market / trending",
        "historical_edge": "Best in 2023-2024 (AI boom), worst in 2022 (bear market)",
    },
    "value": {
        "name": "Value Investor",
        "icon": "📊",
        "color": "#3b82f6",
        "tagline": "Buy quality at a discount — patience pays",
        "philosophy": (
            "Follows Warren Buffett's principles. Only buys stocks trading below intrinsic value "
            "with strong cash flow and competitive moats. Willing to wait months for the right price. "
            "Believes the market overreacts to short-term news, creating opportunities."
        ),
        "strengths": ["Highest win rate", "Steady compounding", "Survives crashes better"],
        "weaknesses": ["Misses momentum rockets", "Slow returns", "Can buy 'cheap' stocks that get cheaper"],
        "prioritizes": ["Low P/E relative to growth (PEG < 1.5)", "Strong free cash flow", "Insider buying", "Analyst targets 20%+ above price", "Dividend yield > 2%"],
        "avoids": ["P/E > 30 stocks", "Unprofitable companies", "Hype-driven stocks"],
        "backtest_signals": ["earnings_beat", "insider_buy", "analyst_upgrade_momentum", "support_bounce"],
        "risk_tolerance": "conservative",
        "ideal_market": "Any market / recovery phases",
        "historical_edge": "Best in 2022 (bear market), consistent in all markets",
    },
    "contrarian": {
        "name": "Contrarian",
        "icon": "🔄",
        "color": "#f59e0b",
        "tagline": "Buy fear, sell greed — the crowd is usually wrong",
        "philosophy": (
            "Goes against the consensus. When everyone is selling in panic, the contrarian buys. "
            "When everyone is euphoric, the contrarian sells. Tracks short interest, bearish sentiment, "
            "and extreme RSI readings as entry signals."
        ),
        "strengths": ["Catches bottoms", "Huge gains on reversals", "Short squeeze plays"],
        "weaknesses": ["Often early (catching falling knives)", "Low win rate", "Emotionally difficult"],
        "prioritizes": ["High short interest (>15%)", "Bearish community sentiment", "RSI < 25 extreme oversold", "Stocks down 30%+ with intact fundamentals", "Fear & Greed index at extreme fear"],
        "avoids": ["Consensus trades", "Stocks everyone agrees on", "Following the crowd"],
        "backtest_signals": ["rsi_oversold", "bb_lower_touch", "vix_high"],
        "risk_tolerance": "aggressive",
        "ideal_market": "Bear market bottoms / panic selloffs",
        "historical_edge": "Best at market bottoms (Mar 2020, Oct 2022), worst in steady uptrends",
    },
    "macro": {
        "name": "Macro Strategist",
        "icon": "🌍",
        "color": "#a855f7",
        "tagline": "Trade the big picture — sectors first, stocks second",
        "philosophy": (
            "Believes individual stock fundamentals are secondary to macro forces. "
            "Picks the right SECTOR first based on rates, flows, geopolitics, and disruption themes, "
            "then finds the best stock within that sector. Rotates between offensive and defensive "
            "positions based on the economic cycle."
        ),
        "strengths": ["Sector rotation timing", "Adapts to market regime", "Geopolitical awareness"],
        "weaknesses": ["Can miss stock-specific catalysts", "Slower to react", "Sometimes too top-down"],
        "prioritizes": ["Sector money flow direction", "Interest rate beneficiaries", "Geopolitical winners", "Disruption theme leaders", "Cross-asset ratios (Gold/SPY, Copper/Gold)"],
        "avoids": ["Stocks in outflowing sectors", "Individual stories against macro trend"],
        "backtest_signals": ["vix_low", "vix_high", "sector_rotation"],
        "risk_tolerance": "moderate",
        "ideal_market": "Transitional / rotation periods",
        "historical_edge": "Best during regime changes (rate hikes, geopolitical shifts)",
    },
}

RISK_MANAGER = {
    "name": "Risk Manager",
    "icon": "🛡",
    "color": "#ef4444",
    "tagline": "Protect capital first — profits follow",
    "philosophy": (
        "The final gatekeeper. Doesn't pick stocks — evaluates what the other agents picked. "
        "Checks sector concentration, position sizing, correlation, and overall portfolio risk. "
        "Has VETO power to reject or reduce any pick. Ensures the portfolio survives any scenario."
    ),
    "checks": [
        "Sector concentration (max configurable %)",
        "Position sizing (risk per trade limit)",
        "Score threshold (min score to accept)",
        "Backtest threshold (min win rate to accept)",
        "Duplicate sector handling (skip/half/allow)",
        "Cash reserve maintenance (min 20%)",
        "Correlation check (don't hold stocks that move together)",
    ],
}


def get_personality_names() -> list[str]:
    return list(AGENT_PERSONALITIES.keys())


def get_personality(name: str) -> dict:
    return AGENT_PERSONALITIES.get(name, {})


def get_all_personalities() -> dict:
    return AGENT_PERSONALITIES
