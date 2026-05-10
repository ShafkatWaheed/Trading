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
        "backtest_signals": ["rsi_oversold", "bb_lower_touch", "vix_high", "news_bearish_spike", "community_bearish"],
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
    "disruption": {
        "name": "Disruption Hunter",
        "icon": "🔗",
        "color": "#06b6d4",
        "tagline": "Find the picks and shovels — infrastructure wins the gold rush",
        "philosophy": (
            "Doesn't chase the obvious disruptors — finds the infrastructure stocks that ENABLE disruption. "
            "When everyone buys NVDA, the Disruption Hunter buys the company making the cooling systems, "
            "the optical fiber, or the memory chips. Maps 1-level dependency chains: AI needs compute → "
            "compute needs memory → memory needs fabs. The picks-and-shovels plays have lower P/E, "
            "steadier revenue, and less downside than the headline stocks."
        ),
        "strengths": ["Finds hidden winners", "Lower valuations than direct plays", "Infrastructure = recurring revenue"],
        "weaknesses": ["Slower upside than direct disruptors", "Theme can fizzle", "Requires accurate chain mapping"],
        "prioritizes": ["Infrastructure/supply chain for active disruption themes", "Revenue tied to megatrend but lower P/E", "Picks-and-shovels over direct plays", "Companies enabling multiple disruptors", "Capacity constraints (who can't build fast enough?)"],
        "avoids": ["Obvious headline disruptors (everyone already owns them)", "Companies with no clear revenue link", "Pure speculation plays"],
        "backtest_signals": ["disruption_tailwind", "volume_spike", "macd_bullish", "golden_cross"],
        "risk_tolerance": "moderate",
        "ideal_market": "Innovation cycles / theme-driven markets",
        "historical_edge": "Best during tech booms (2023-2024 AI infra), worst when themes rotate out",
        "data_focus": "disruption_chain",
    },
    "insider": {
        "name": "Insider Shadow",
        "icon": "🕵️",
        "color": "#ec4899",
        "tagline": "Follow the money — insiders know more than analysts",
        "philosophy": (
            "Tracks what corporate insiders (CEO, CFO, directors), congress members, and hedge funds are "
            "actually BUYING with their own money. Talk is cheap — when a CEO puts $2M of personal wealth "
            "into their own stock, that's the strongest signal. Congress members on relevant committees "
            "have information advantages. Cluster buys (2+ insiders in 7 days) historically win 70%+ of the time. "
            "Priority: Insider trades > Congressional trades > Institutional 13F filings."
        ),
        "strengths": ["Highest conviction signals", "70%+ win rate on cluster buys", "Information edge over public"],
        "weaknesses": ["Low frequency (insiders don't trade daily)", "13F filings are 45 days delayed", "Insiders can be wrong"],
        "prioritizes": ["Cluster buys (2+ insiders within 7 days)", "CEO/CFO personal purchases > $500K", "Bipartisan congressional buying", "Hedge fund accumulation (new positions)", "Convergence: insider + congress + institutional all buying"],
        "avoids": ["Insider sells (often tax/diversification, not bearish)", "Single small purchases", "13F-only signals (too delayed)"],
        "backtest_signals": ["insider_buy", "congress_buy", "institutions_accumulating", "earnings_beat"],
        "risk_tolerance": "moderate",
        "ideal_market": "Any market — insider buying works in all conditions",
        "historical_edge": "Consistent alpha in all market regimes, strongest before earnings catalysts",
        "data_focus": "smart_money",
    },
    "options": {
        "name": "Options Whisperer",
        "icon": "📡",
        "color": "#f97316",
        "tagline": "Big money talks in options — learn to listen",
        "philosophy": (
            "Reads the options market for directional bets that precede stock moves. When someone "
            "spends millions on call options before an announcement, that's not a guess — that's conviction. "
            "Tracks unusual activity (volume 3x+ open interest), extreme put/call ratios, and IV rank spikes. "
            "The options market is where informed money positions BEFORE the stock moves."
        ),
        "strengths": ["Catches moves before they happen", "Quantifiable signals", "Works on any timeframe"],
        "weaknesses": ["Can be hedging (not directional)", "Options expire worthless", "Requires Polygon API"],
        "prioritizes": ["Unusual call volume (volume/OI >= 3x)", "Put/call ratio < 0.5 (very bullish)", "IV rank > 80th percentile (event expected)", "Large premium trades ($500K+)", "Bullish flow + technical confirmation"],
        "avoids": ["Normal hedging activity", "Low volume options", "Put/call ratio in neutral range (0.7-1.0)"],
        "backtest_signals": ["options_bullish", "volume_spike", "support_bounce", "macd_bullish"],
        "risk_tolerance": "aggressive",
        "ideal_market": "Pre-earnings / pre-event periods",
        "historical_edge": "Best before binary events (earnings, FDA, M&A), worst in low-vol grinding markets",
        "data_focus": "options_flow",
    },
    "flow": {
        "name": "Flow Tracker",
        "icon": "💧",
        "color": "#14b8a6",
        "tagline": "See what institutions do, not what they say",
        "philosophy": (
            "Reads Level 2 market microstructure to detect institutional accumulation before it shows up "
            "in price or technicals. Looks for the smart accumulation pattern: buy pressure (buy/sell ratio > 1.5) "
            "+ price near VWAP (institutions buying at fair value) + high liquidity (easy entry). "
            "When dark pool blocks and order book imbalance both point the same direction, institutions "
            "are building positions that will move the stock in days."
        ),
        "strengths": ["Sees institutional flow in real-time", "Leads technicals by hours/days", "Hard to fake"],
        "weaknesses": ["Requires Polygon API", "Short-lived signals", "Free tier data limitations"],
        "prioritizes": ["Buy/sell ratio > 1.5 (buy pressure)", "Price near/below VWAP (quiet accumulation)", "Large trades > 10K shares (institutional blocks)", "High liquidity score (easy entry/exit)", "Order book imbalance favoring buyers"],
        "avoids": ["Low liquidity stocks (unreliable microstructure)", "Balanced order books (no edge)", "Stocks above VWAP with sell pressure"],
        "backtest_signals": ["volume_spike", "support_bounce", "sma50_cross_up", "macd_bullish"],
        "risk_tolerance": "moderate",
        "ideal_market": "Any liquid market — works best in large/mid cap stocks",
        "historical_edge": "Best when institutions rotate (sector shifts, rebalancing), worst in retail-driven manias",
        "data_focus": "microstructure",
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
