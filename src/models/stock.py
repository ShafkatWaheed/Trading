from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class StockQuote(BaseModel):
    symbol: str
    price: Decimal
    open: Decimal
    high: Decimal
    low: Decimal
    volume: int
    previous_close: Decimal
    timestamp: datetime

    @property
    def change(self) -> Decimal:
        return self.price - self.previous_close

    @property
    def change_percent(self) -> Decimal:
        if self.previous_close == 0:
            return Decimal("0")
        return (self.change / self.previous_close) * 100


class StockFundamentals(BaseModel):
    symbol: str
    market_cap: Decimal
    pe_ratio: Decimal | None = None
    peg_ratio: Decimal | None = None
    eps: Decimal | None = None
    eps_growth: Decimal | None = None
    revenue: Decimal | None = None
    revenue_growth: Decimal | None = None
    profit_margin: Decimal | None = None
    roe: Decimal | None = None
    debt_to_equity: Decimal | None = None
    free_cash_flow: Decimal | None = None
    dividend_yield: Decimal | None = None
    beta: Decimal | None = None
    week_52_high: Decimal | None = None
    week_52_low: Decimal | None = None
    avg_volume: int | None = None
    sector: str = ""
    industry: str = ""
    description: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class Stock(BaseModel):
    symbol: str
    name: str
    quote: StockQuote | None = None
    fundamentals: StockFundamentals | None = None
