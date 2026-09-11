"""Data model shared by both sources and the API layer.

RealizedTrade carries more fields than v1 renders (commission, symbol,
asset category) so the per-symbol table and gross/net split can be added
without touching the Flex parser.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

TodaySource = Literal["gateway", "flex", "none"]


class RealizedTrade(BaseModel):
    """One closing execution from a Flex Activity statement."""

    symbol: str
    trade_date: date
    realized_pnl: Decimal
    commission: Decimal = Decimal(0)
    currency: str = "USD"
    asset_category: str = ""
    quantity: Decimal = Decimal(0)
    buy_sell: str = ""


class FlexResult(BaseModel):
    """Outcome of a Flex fetch. `ok` false means we have a real error to show
    rather than a silently-zero P&L (an expired token is the common case)."""

    ok: bool
    trades: list[RealizedTrade] = []
    fetched_at: datetime | None = None
    account_id: str = ""
    error: str = ""


class GatewayState(BaseModel):
    """Latest values from the reqPnL subscription, or a reason we have none."""

    connected: bool = False
    realized_pnl: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    daily_pnl: Decimal | None = None
    account: str = ""
    updated_at: datetime | None = None
    error: str = ""


class CumulativePoint(BaseModel):
    date: date
    realized_pnl: Decimal  # that day's realized P&L
    cumulative: Decimal  # running total through that day


class PnLResponse(BaseModel):
    """What GET /api/pnl returns."""

    headline: Decimal
    today: Decimal
    currency: str
    today_source: TodaySource
    series: list[CumulativePoint]
    trade_count: int
    gateway: GatewayState
    flex_ok: bool
    flex_error: str = ""
    flex_fetched_at: datetime | None = None
    account_id: str = ""
    # Set when the statement spans more than one currency; summing across
    # currencies would be meaningless, so we say so instead of guessing at FX.
    currency_warning: str = ""
