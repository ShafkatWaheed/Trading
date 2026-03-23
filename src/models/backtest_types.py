"""Data types for backtesting, portfolio simulation, and trade journal."""

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class BacktestTrade:
    symbol: str
    signal_name: str
    direction: str  # "buy" / "sell"
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    pnl: float
    pnl_percent: float
    hold_days: int
    outcome: str  # "win" / "loss"


@dataclass
class BacktestResult:
    symbol: str
    signal_name: str
    hold_days: int
    lookback_days: int
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    avg_return: float
    total_return: float
    max_gain: float
    max_loss: float
    max_drawdown: float
    sharpe_ratio: float
    trades: list[BacktestTrade] = field(default_factory=list)

    @property
    def expectancy(self) -> float:
        if self.total_trades == 0:
            return 0.0
        avg_win = sum(t.pnl_percent for t in self.trades if t.outcome == "win") / max(self.wins, 1)
        avg_loss = abs(sum(t.pnl_percent for t in self.trades if t.outcome == "loss") / max(self.losses, 1))
        return (self.win_rate * avg_win) - ((1 - self.win_rate) * avg_loss)

    @property
    def grade(self) -> str:
        ev = self.win_rate * self.avg_return
        if ev > 3.0:
            return "A+"
        if ev > 2.0:
            return "A"
        if ev > 1.0:
            return "B+"
        if ev > 0.5:
            return "B"
        if ev > 0:
            return "C"
        return "D"


@dataclass
class PortfolioPosition:
    symbol: str
    shares: int
    entry_price: float
    entry_date: str
    current_price: float = 0.0

    @property
    def pnl(self) -> float:
        return (self.current_price - self.entry_price) * self.shares

    @property
    def pnl_percent(self) -> float:
        if self.entry_price == 0:
            return 0.0
        return ((self.current_price - self.entry_price) / self.entry_price) * 100


@dataclass
class PortfolioSnapshot:
    date: str
    total_value: float
    cash: float
    invested: float
    daily_return: float
    cumulative_return: float
    benchmark_return: float


@dataclass
class PortfolioResult:
    strategy: str
    initial_capital: float
    final_value: float
    total_return: float
    annualized_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    total_trades: int
    alpha: float  # vs benchmark
    best_trade: BacktestTrade | None = None
    worst_trade: BacktestTrade | None = None
    equity_curve: list[PortfolioSnapshot] = field(default_factory=list)
    closed_trades: list[BacktestTrade] = field(default_factory=list)


@dataclass
class JournalTrade:
    id: int
    symbol: str
    direction: str  # "long" / "short"
    entry_date: str
    entry_price: float
    exit_date: str | None
    exit_price: float | None
    shares: int
    pnl: float | None
    pnl_percent: float | None
    report_verdict: str
    thesis: str
    notes: str
    status: str  # "open" / "closed"
    created_at: str


@dataclass
class JournalStats:
    total_trades: int
    open_trades: int
    closed_trades: int
    wins: int
    losses: int
    win_rate: float
    total_pnl: float
    avg_win: float
    avg_loss: float
    expectancy: float
    best_trade: float
    worst_trade: float
    report_accuracy: dict[str, dict] = field(default_factory=dict)
    # e.g. {"Strong Buy": {"trades": 5, "wins": 4, "win_rate": 0.8}, ...}
