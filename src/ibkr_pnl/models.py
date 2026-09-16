"""Data model shared by both sources and the API layer.

RealizedTrade carries more fields than v1 renders (commission, symbol,
asset category) so the per-symbol table and gross/net split can be added
without touching the Flex parser.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, computed_field

TodaySource = Literal["gateway", "flex", "none"]


class RealizedTrade(BaseModel):
    """One execution from a Flex Activity statement -- opening or closing.

    An opening trade (one that opened or added to a position) carries
    realized_pnl=0; see is_realizing. Both kinds are kept so the
    transaction ledger can show every execution, matching IBKR's own apps.

    trade_time/trade_price/trade_money/order_type/notes_codes/exchange are
    only populated when the Flex Query includes those fields -- they default
    to blank rather than erroring, so an older or smaller query still works.
    """

    symbol: str
    trade_date: date
    realized_pnl: Decimal  # fifoPnlRealized exactly as Flex reports it -- gross
    commission: Decimal = Decimal(0)
    currency: str = "USD"
    asset_category: str = ""
    quantity: Decimal = Decimal(0)
    buy_sell: str = ""
    trade_time: str = ""  # "HH:MM:SS", local to the statement
    trade_price: Decimal | None = None
    trade_money: Decimal | None = None  # gross amount, price * quantity
    order_type: str = ""
    notes_codes: str = ""  # e.g. "O", "C", "P" -- opening/closing/partial
    exchange: str = ""
    ib_order_id: str = ""  # shared by every execution that filled one order

    @computed_field  # type: ignore[prop-decorator]
    @property
    def net_pnl(self) -> Decimal:
        """realized_pnl (fifoPnlRealized) after commission, for anyone who
        wants a commission-inclusive figure. NOT what the dashboard uses for
        its totals: checked against a real account's whole-statement total,
        gross (realized_pnl) matched Client Portal's own YTD figure to
        within $1.16 (explained by a few trades outside the fetched date
        range) while net was off by $371 -- IBKR's own "Realized P&L" is
        gross, with commission shown as a separate line, not netted in."""
        return self.realized_pnl + self.commission

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_realizing(self) -> bool:
        """False for a trade that only opened or added to a position --
        fifoPnlRealized is exactly 0 for those. The transaction ledger's
        "Realized only" filter is this flag."""
        return self.realized_pnl != 0


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
    realized_pnl: Decimal  # that day's realized P&L (gross -- see net_pnl)
    cumulative: Decimal  # running total through that day


class DayGroup(BaseModel):
    """One day's worth of trades, for the transaction ledger view."""

    date: date
    total_pnl: Decimal  # gross -- see RealizedTrade.net_pnl
    trades: list[RealizedTrade]


class TransactionsResponse(BaseModel):
    """What GET /api/transactions returns."""

    total_realized: Decimal
    trade_count: int
    from_date: date | None
    to_date: date | None
    days: list[DayGroup]  # newest day first
    flex_ok: bool
    flex_error: str = ""
    flex_fetched_at: datetime | None = None
    account_id: str = ""
    period: str = "all"
    years_covered: list[int] = []


class PositionLeg(BaseModel):
    """One order's contribution to a position -- entry (added to it) or exit
    (reduced it). Already collapsed across that order's partial fills, the
    same as the transaction ledger's "Group fills" view. quantity is always
    a positive magnitude; direction lives on the parent Position."""

    trade_date: date
    trade_time: str
    buy_sell: str
    price: Decimal | None
    quantity: Decimal
    fill_count: int
    realized_pnl: Decimal
    commission: Decimal
    # "" when every fill in this leg shares one order, or when the Flex
    # Query omits IB Order ID; a leg only ever spans one order, so this is
    # never ambiguous the way it would be at the Position level.
    ib_order_id: str = ""
    # Share of the position's total size this exit accounts for. Exit legs
    # only -- an entry leg is part of *opening* the size, not closing it.
    pct_of_position: Decimal | None = None


class Position(BaseModel):
    """One round trip: a symbol's net quantity moving away from zero and
    (usually) back. See positions.build_positions for how trades are split
    into these."""

    symbol: str
    asset_category: str
    currency: str
    direction: Literal["long", "short"]
    is_open: bool
    # True when the very first trade we see for this symbol already closes
    # something (realized_pnl != 0) -- the opening trade happened before the
    # fetched date range, so open_date/open_time/entry_price are unknown
    # rather than guessed.
    is_carry_in: bool
    open_date: date | None
    open_time: str
    entry_price: Decimal | None
    quantity: Decimal  # position size -- see positions.py for open/closed semantics
    exit_date: date | None
    exit_count: int
    realized_pnl: Decimal | None  # None while open with nothing realized yet
    commission: Decimal  # summed across every entry and exit leg
    entry_legs: list[PositionLeg]
    exit_legs: list[PositionLeg]


class PositionsResponse(BaseModel):
    """What GET /api/positions returns."""

    positions: list[Position]  # most recent activity first
    flex_ok: bool
    flex_error: str = ""
    flex_fetched_at: datetime | None = None
    account_id: str = ""
    period: str = "all"
    years_covered: list[int] = []


class OHLCVBar(BaseModel):
    """One daily price bar. Plain float, not Decimal -- this is chart display
    data with no accounting precision requirement, and matches the market-data
    service's own numeric type as-is rather than round-tripping through a
    string for no benefit."""

    time: date
    open: float
    high: float
    low: float
    close: float
    volume: int


class MarketDataResult(BaseModel):
    """What GET /api/market-data/ohlcv returns. `ok=False` is the normal
    state for a symbol Yahoo Finance doesn't recognize -- see
    sources/market_data.py."""

    ok: bool
    symbol: str = ""  # the plain ticker actually queried, after CFD-suffix stripping
    bars: list[OHLCVBar] = []
    error: str = ""


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
    # Which calendar years this figure actually covers. "All" only merges the
    # years already downloaded, so the UI must be able to say so rather than
    # present a partial multi-year total as a complete one.
    period: str = "all"
    years_covered: list[int] = []
