"""FIFO round-trip matching. The core invariant every test comes back to:
realized_pnl and commission are never invented, only reapportioned -- so
the totals across every RoundTrip must reconcile exactly with the totals
across the trades that produced them."""

from datetime import date
from decimal import Decimal

from ibkr_pnl.models import FlexResult, RealizedTrade
from ibkr_pnl.round_trips import match

DAY = date(2026, 1, 1)


def execution(
    time: str,
    buy_sell: str,
    quantity: str,
    price: str,
    realized_pnl: str = "0",
    commission: str = "0",
    symbol: str = "TEST",
    day: date = DAY,
) -> RealizedTrade:
    """`quantity` is given unsigned; the sign is derived from buy_sell, the
    same way Flex reports it (BUY positive, SELL negative)."""
    signed = Decimal(quantity) if buy_sell == "BUY" else -Decimal(quantity)
    return RealizedTrade(
        symbol=symbol,
        trade_date=day,
        trade_time=time,
        buy_sell=buy_sell,
        quantity=signed,
        trade_price=Decimal(price),
        realized_pnl=Decimal(realized_pnl),
        commission=Decimal(commission),
    )


def flex(*trades: RealizedTrade) -> FlexResult:
    return FlexResult(ok=True, trades=list(trades), account_id="U1")


def totals_reconcile(trades: list[RealizedTrade], round_trips) -> None:
    assert sum((r.realized_pnl for r in round_trips), Decimal(0)) == sum(
        (t.realized_pnl for t in trades), Decimal(0)
    )
    assert sum((r.commission for r in round_trips), Decimal(0)) == sum(
        (t.commission for t in trades), Decimal(0)
    )


class TestSimpleRoundTrip:
    def test_one_buy_one_matching_sell(self):
        trades = [
            execution("09:00:00", "BUY", "100", "10.00", commission="-1.00"),
            execution("10:00:00", "SELL", "100", "11.00", realized_pnl="100.00", commission="-1.00"),
        ]
        [rt] = match(flex(*trades))

        assert rt.side == "long"
        assert rt.quantity == 100
        assert rt.opened_date == DAY
        assert rt.opened_time == "09:00:00"
        assert rt.open_price == Decimal("10.00")
        assert rt.closed_time == "10:00:00"
        assert rt.close_price == Decimal("11.00")
        assert rt.realized_pnl == Decimal("100.00")
        assert rt.commission == Decimal("-2.00")  # both legs, nothing split
        assert rt.opening_trade == trades[0]
        assert rt.closing_trade == trades[1]
        totals_reconcile(trades, [rt])

    def test_short_side(self):
        """SELL first, BUY to cover -- the mirror image, and side must read
        "short", not "long"."""
        trades = [
            execution("09:00:00", "SELL", "50", "20.00", commission="-1.00"),
            execution("10:00:00", "BUY", "50", "18.00", realized_pnl="100.00", commission="-1.00"),
        ]
        [rt] = match(flex(*trades))

        assert rt.side == "short"
        assert rt.open_price == Decimal("20.00")
        assert rt.close_price == Decimal("18.00")
        totals_reconcile(trades, [rt])


class TestFragmentsIntoSeveralRoundTrips:
    def test_partial_close_then_reentry_then_full_close(self):
        """The example from the design discussion: a partial close followed
        by a re-entry means the final close draws from two different lots,
        producing three round trips for what a trader would call one
        continuous position."""
        trades = [
            execution("09:00:00", "BUY", "200", "10.00", commission="-2.00"),
            execution("10:00:00", "SELL", "80", "11.00", realized_pnl="80.00", commission="-1.00"),
            execution("11:00:00", "BUY", "40", "10.50", commission="-0.50"),
            execution("12:00:00", "SELL", "160", "12.00", realized_pnl="270.00", commission="-2.00"),
        ]
        round_trips = match(flex(*trades))

        assert len(round_trips) == 3
        by_qty = {rt.quantity: rt for rt in round_trips}

        first_close = by_qty[Decimal("80")]
        assert first_close.opened_time == "09:00:00"
        assert first_close.closed_time == "10:00:00"
        assert first_close.realized_pnl == Decimal("80.00")
        assert first_close.commission == Decimal("-1.80")  # -2.00*(80/200) + -1.00

        rest_of_first_lot = by_qty[Decimal("120")]
        assert rest_of_first_lot.opened_time == "09:00:00"  # same lot as above
        assert rest_of_first_lot.closed_time == "12:00:00"
        assert rest_of_first_lot.realized_pnl == Decimal("202.50")  # 270*(120/160)
        assert rest_of_first_lot.commission == Decimal("-2.70")

        second_lot = by_qty[Decimal("40")]
        assert second_lot.opened_time == "11:00:00"
        assert second_lot.closed_time == "12:00:00"
        assert second_lot.realized_pnl == Decimal("67.50")  # remainder, exact
        assert second_lot.commission == Decimal("-1.00")

        # Both round trips drawing on the 09:00 lot carry the SAME opening
        # execution -- its full original 200-share quantity, not sliced down
        # to what each round trip actually used of it.
        assert first_close.opening_trade == rest_of_first_lot.opening_trade == trades[0]
        assert first_close.opening_trade.quantity == 200
        # Both closing trades are the full 12:00 SELL 160, not the 117/50
        # split -- closing_trade.quantity stays -160, RoundTrip.quantity is
        # what to read for this slice's own share of it.
        assert rest_of_first_lot.closing_trade == second_lot.closing_trade == trades[3]

        totals_reconcile(trades, round_trips)

    def test_newest_closed_first(self):
        trades = [
            execution("09:00:00", "BUY", "10", "1.00"),
            execution("09:01:00", "SELL", "10", "2.00", realized_pnl="10.00", day=date(2026, 1, 1)),
            execution("09:00:00", "BUY", "10", "1.00", day=date(2026, 1, 2), symbol="B"),
            execution(
                "09:01:00", "SELL", "10", "2.00", realized_pnl="10.00", day=date(2026, 1, 2), symbol="B"
            ),
        ]
        round_trips = match(flex(*trades))
        assert [rt.closed_date for rt in round_trips] == [date(2026, 1, 2), date(2026, 1, 1)]


class TestOpenedBeforeWindow:
    def test_a_close_with_no_visible_opening_lot_is_not_invented_as_fresh(self):
        """A single SELL with nonzero realized_pnl and nothing queued ahead
        of it can only mean the position was already open when this data's
        window began -- Flex marks it realizing, which a fresh open never
        is. It must not be read as a brand-new short."""
        trades = [
            execution("10:00:00", "SELL", "50", "18.00", realized_pnl="60.00", commission="-1.00"),
        ]
        [rt] = match(flex(*trades))

        assert rt.opened_date is None
        assert rt.opened_time == ""
        assert rt.open_price is None
        assert rt.side == "long"  # a SELL that closed something closed a long
        assert rt.quantity == 50
        assert rt.realized_pnl == Decimal("60.00")
        assert rt.commission == Decimal("-1.00")
        totals_reconcile(trades, [rt])

    def test_a_fresh_open_with_no_prior_history_is_not_misread_as_one(self):
        """The mirror case: a genuine fresh open (realized_pnl exactly 0)
        must not be flagged as opened-before-window just because nothing
        happens to be queued yet."""
        trades = [
            execution("09:00:00", "BUY", "50", "10.00"),
            execution("10:00:00", "SELL", "50", "11.00", realized_pnl="50.00"),
        ]
        [rt] = match(flex(*trades))
        assert rt.opened_date == DAY


class TestReversalInOneExecution:
    def test_an_execution_larger_than_the_open_position_flips_and_opens_a_new_lot(self):
        """A single SELL for more than the open long closes the long
        entirely and opens a fresh short with the leftover -- realized P&L
        belongs only to the closing portion, the leftover opens at 0."""
        trades = [
            execution("09:00:00", "BUY", "100", "10.00", commission="-1.00"),
            execution(
                "10:00:00", "SELL", "150", "11.00", realized_pnl="100.00", commission="-1.50"
            ),
            execution(
                "11:00:00", "BUY", "50", "10.50", realized_pnl="25.00", commission="-0.50"
            ),
        ]
        round_trips = match(flex(*trades))

        assert len(round_trips) == 2
        closed_the_long = next(rt for rt in round_trips if rt.side == "long")
        assert closed_the_long.quantity == 100
        assert closed_the_long.realized_pnl == Decimal("100.00")

        closed_the_short = next(rt for rt in round_trips if rt.side == "short")
        assert closed_the_short.quantity == 50
        assert closed_the_short.open_price == Decimal("11.00")  # priced at the reversal
        assert closed_the_short.realized_pnl == Decimal("25.00")

        totals_reconcile(trades, round_trips)


class TestCashRowsExcluded:
    def test_a_cash_row_never_becomes_a_round_trip(self):
        """USD.SGD-style CASH rows are IBKR funding the account's margin
        currency, not a trade -- verified against a real account where one
        showed up as a still-open BUY with realized_pnl=0 and no matching
        SELL anywhere in the fetched window."""
        trades = [
            RealizedTrade(
                symbol="USD.SGD",
                trade_date=DAY,
                asset_category="CASH",
                buy_sell="BUY",
                quantity=Decimal("4722.42"),
                realized_pnl=Decimal("0"),
            ),
            execution("09:00:00", "BUY", "10", "1.00"),
            execution("10:00:00", "SELL", "10", "2.00", realized_pnl="10.00"),
        ]
        round_trips = match(flex(*trades))
        assert len(round_trips) == 1
        assert round_trips[0].symbol == "TEST"


class TestStillOpenAtPeriodEnd:
    def test_an_unclosed_position_s_commission_is_not_yet_attributable(self):
        """A position still open when the fetched window ends has paid
        commission on its opening execution but hasn't closed anything, so
        there is no round trip yet for that commission to belong to --
        distinct from the other invariant (realized_pnl), which always
        reconciles exactly since only a close ever carries any."""
        trades = [
            execution("09:00:00", "BUY", "100", "10.00", commission="-1.00"),
            # never closed within this data
        ]
        round_trips = match(flex(*trades))
        assert round_trips == []  # nothing has closed, so nothing to show
        # The $1.00 commission is real and paid, just not yet attributable
        # to a completed trade -- this is the one place totals diverge from
        # Transactions/Overview, and it is documented, not a bug.


class TestMultipleSymbolsIndependent:
    def test_two_symbols_do_not_interfere(self):
        trades = [
            execution("09:00:00", "BUY", "10", "1.00", symbol="AAA"),
            execution("09:00:00", "SELL", "5", "2.00", realized_pnl="20.00", symbol="BBB"),
            execution("10:00:00", "SELL", "10", "2.00", realized_pnl="10.00", symbol="AAA"),
        ]
        round_trips = match(flex(*trades))

        assert len(round_trips) == 2
        aaa = next(rt for rt in round_trips if rt.symbol == "AAA")
        bbb = next(rt for rt in round_trips if rt.symbol == "BBB")
        assert aaa.opened_date == DAY
        assert bbb.opened_date is None  # BBB's SELL had no visible opening lot
        totals_reconcile(trades, round_trips)
