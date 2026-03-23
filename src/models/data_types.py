"""Data types shared between data layer and analysis layer.

These are pure data structures with no I/O dependencies.
Relocated from data providers so analysis modules can import them
without violating the architecture dependency rules.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


# ── Macro ────────────────────────────────────────────────────────────

@dataclass
class MacroDataPoint:
    series_id: str
    series_name: str
    value: Decimal
    date: str
    unit: str
    frequency: str


@dataclass
class MacroSnapshot:
    timestamp: datetime
    fed_funds_rate: Decimal | None = None
    treasury_10y: Decimal | None = None
    treasury_2y: Decimal | None = None
    yield_spread_10y2y: Decimal | None = None
    cpi_yoy: Decimal | None = None
    unemployment_rate: Decimal | None = None
    gdp_growth: Decimal | None = None
    vix: Decimal | None = None
    consumer_sentiment: Decimal | None = None
    dollar_index: Decimal | None = None

    @property
    def yield_curve_inverted(self) -> bool:
        if self.treasury_10y is not None and self.treasury_2y is not None:
            return self.treasury_10y < self.treasury_2y
        return False

    @property
    def regime(self) -> str:
        if self.vix and self.vix > 30:
            return "high_volatility"
        if self.yield_curve_inverted:
            return "recession_warning"
        if self.fed_funds_rate and self.fed_funds_rate > Decimal("5"):
            return "tight_monetary"
        if self.unemployment_rate and self.unemployment_rate < Decimal("4"):
            return "strong_labor"
        return "normal"


# ── Level 2 / Microstructure ────────────────────────────────────────

@dataclass
class Level2Quote:
    symbol: str
    bid_price: Decimal
    bid_size: int
    ask_price: Decimal
    ask_size: int
    spread: Decimal
    spread_percent: Decimal
    midpoint: Decimal
    timestamp: str


@dataclass
class OrderBookLevel:
    price: Decimal
    size: int
    exchange: str
    order_count: int = 0


@dataclass
class OrderBook:
    symbol: str
    bids: list[OrderBookLevel] = field(default_factory=list)
    asks: list[OrderBookLevel] = field(default_factory=list)
    timestamp: str = ""

    @property
    def bid_depth(self) -> int:
        return sum(level.size for level in self.bids)

    @property
    def ask_depth(self) -> int:
        return sum(level.size for level in self.asks)

    @property
    def imbalance(self) -> Decimal:
        total = self.bid_depth + self.ask_depth
        if total == 0:
            return Decimal("0")
        return Decimal(str(round((self.bid_depth - self.ask_depth) / total, 4)))


@dataclass
class Tick:
    symbol: str
    price: Decimal
    size: int
    exchange: str
    conditions: list[str]
    timestamp: str
    is_buyer_maker: bool = False


@dataclass
class MicrostructureSummary:
    symbol: str
    avg_spread: Decimal
    avg_spread_percent: Decimal
    avg_bid_depth: int
    avg_ask_depth: int
    order_imbalance: Decimal
    tick_count: int
    vwap: Decimal
    buy_volume: int
    sell_volume: int
    buy_sell_ratio: Decimal
    large_trade_count: int
    liquidity_score: str
    timestamp: str = ""


# ── Options ──────────────────────────────────────────────────────────

@dataclass
class OptionContract:
    symbol: str
    underlying: str
    contract_type: str
    strike: Decimal
    expiration: str
    bid: Decimal
    ask: Decimal
    last_price: Decimal
    volume: int
    open_interest: int
    implied_volatility: Decimal
    delta: Decimal | None = None
    gamma: Decimal | None = None
    theta: Decimal | None = None
    vega: Decimal | None = None
    rho: Decimal | None = None
    in_the_money: bool = False


@dataclass
class OptionsChain:
    underlying: str
    underlying_price: Decimal
    expiration: str
    calls: list[OptionContract] = field(default_factory=list)
    puts: list[OptionContract] = field(default_factory=list)


@dataclass
class UnusualActivity:
    underlying: str
    contract_type: str
    strike: Decimal
    expiration: str
    volume: int
    open_interest: int
    volume_oi_ratio: Decimal
    implied_volatility: Decimal
    premium: Decimal
    sentiment: str
    timestamp: str


@dataclass
class OptionsSummary:
    underlying: str
    underlying_price: Decimal
    put_call_ratio: Decimal
    total_call_volume: int
    total_put_volume: int
    total_call_oi: int
    total_put_oi: int
    avg_iv: Decimal
    iv_rank: Decimal | None = None
    iv_percentile: Decimal | None = None
    max_pain: Decimal | None = None
    unusual_activity: list[UnusualActivity] = field(default_factory=list)
    sentiment: str = ""

    def compute_sentiment(self) -> None:
        if self.put_call_ratio < Decimal("0.7"):
            self.sentiment = "bullish"
        elif self.put_call_ratio > Decimal("1.0"):
            self.sentiment = "bearish"
        else:
            self.sentiment = "neutral"

        if self.unusual_activity:
            bullish = sum(1 for u in self.unusual_activity if u.sentiment == "bullish")
            bearish = sum(1 for u in self.unusual_activity if u.sentiment == "bearish")
            if bullish > bearish * 2:
                self.sentiment = "bullish"
            elif bearish > bullish * 2:
                self.sentiment = "bearish"


# ── SEC EDGAR (Insider + Institutional) ──────────────────────────────

@dataclass
class InsiderTrade:
    filer_name: str
    filer_title: str
    symbol: str
    company: str
    transaction_type: str
    shares: int
    price: Decimal
    total_value: Decimal
    shares_owned_after: int
    transaction_date: str
    filing_date: str
    sec_url: str = ""


@dataclass
class InsiderSummary:
    symbol: str
    period_days: int
    total_trades: int
    total_buys: int
    total_sells: int
    net_shares: int
    buy_value: Decimal
    sell_value: Decimal
    unique_insiders: int
    cluster_buy: bool
    recent_trades: list[InsiderTrade] = field(default_factory=list)
    top_buyers: list[str] = field(default_factory=list)
    top_sellers: list[str] = field(default_factory=list)
    signal: str = ""


@dataclass
class InstitutionalHolding:
    institution: str
    symbol: str
    shares: int
    value: Decimal
    change_shares: int
    change_percent: Decimal
    portfolio_percent: Decimal
    filing_date: str
    report_date: str


@dataclass
class InstitutionalSummary:
    symbol: str
    total_institutions: int
    total_shares_held: int
    institutional_ownership_percent: Decimal
    net_change_shares: int
    new_positions: int
    closed_positions: int
    increased: int
    decreased: int
    top_holders: list[InstitutionalHolding] = field(default_factory=list)
    notable_changes: list[InstitutionalHolding] = field(default_factory=list)


# ── Congressional Trades ─────────────────────────────────────────────

@dataclass
class CongressTrade:
    politician: str
    party: str
    chamber: str
    state: str
    symbol: str
    company: str
    transaction_type: str
    amount_range: str
    amount_low: Decimal
    amount_high: Decimal
    trade_date: str
    filed_date: str
    days_to_file: int
    price_at_trade: Decimal | None = None
    committees: list[str] = field(default_factory=list)


@dataclass
class CongressTradesSummary:
    symbol: str
    total_trades: int
    total_buys: int
    total_sells: int
    unique_politicians: int
    net_sentiment: str
    top_buyers: list[str] = field(default_factory=list)
    top_sellers: list[str] = field(default_factory=list)
    recent_trades: list[CongressTrade] = field(default_factory=list)
    party_breakdown: dict[str, dict[str, int]] = field(default_factory=dict)
