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


class RoundTrip(BaseModel):
    """One completed FIFO-matched position: a slice of an opening execution
    closed against a slice of a later closing execution.

    A single flat-to-flat position (0 -> ... -> 0) can produce more than one
    of these. A close that draws on more than one still-open lot -- a
    partial close followed later by a full close, say -- splits into one
    RoundTrip per lot it draws from, the same way IBKR's own FIFO accounting
    would; see round_trips.match for the mechanics.

    realized_pnl and commission are never invented: they are Flex's own
    figures for the closing (and, for commission, opening) execution,
    apportioned across however many RoundTrips that execution's quantity
    ends up split into, by quantity share. Summed across every RoundTrip
    for a period, both reconcile exactly with Transactions and Overview --
    this only redraws the lines between trades, it never moves money.
    """

    symbol: str
    currency: str
    asset_category: str
    side: Literal["long", "short"]
    quantity: Decimal  # positive: the size of this matched slice

    # None when the opening lot was never observed -- it predates the
    # earliest year in this period's downloaded data, so this position was
    # already open when the window began. Its true entry is unknown; what's
    # shown is only the close.
    opened_date: date | None = None
    opened_time: str = ""
    open_price: Decimal | None = None

    closed_date: date
    closed_time: str = ""
    close_price: Decimal | None = None

    realized_pnl: Decimal
    commission: Decimal = Decimal(0)

    # The full executions this round trip was matched from -- not sliced
    # down to this round trip's own quantity. An opening execution split
    # across several round trips (a partial close followed by a later full
    # close, say) carries its whole original quantity/commission/etc. on
    # each one; RoundTrip.quantity is what actually belongs to this slice.
    # opening_trade is None exactly when opened_date is: no execution was
    # ever observed opening this position.
    opening_trade: RealizedTrade | None = None
    closing_trade: RealizedTrade

    @computed_field  # type: ignore[prop-decorator]
    @property
    def net_pnl(self) -> Decimal:
        return self.realized_pnl + self.commission


class RoundTripsResponse(BaseModel):
    """What GET /api/round-trips returns."""

    round_trips: list[RoundTrip]  # newest closed first
    total_realized: Decimal
    total_commission: Decimal
    trade_count: int  # number of round trips, not executions
    from_date: date | None
    to_date: date | None
    flex_ok: bool
    flex_error: str = ""
    flex_fetched_at: datetime | None = None
    account_id: str = ""
    period: str = "all"
    years_covered: list[int] = []


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
