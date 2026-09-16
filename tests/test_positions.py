"""Position reconstruction: trades split into round trips rather than days.

The RKTn scenario in test_rktn_matches_the_worked_example is a real account's
data, worked out by hand first -- it's the ground truth these numbers were
checked against, not derived from the code under test.
"""

from datetime import date
from decimal import Decimal

from ibkr_pnl.models import FlexResult, RealizedTrade
from ibkr_pnl.positions import build_positions


def trade(
    day: str,
    time: str,
    buy_sell: str,
    quantity: str,
    price: str,
    pnl: str = "0",
    symbol: str = "AAPL",
    order_id: str = "",
    commission: str = "0",
) -> RealizedTrade:
    y, m, d = (int(p) for p in day.split("-"))
    return RealizedTrade(
        symbol=symbol,
        trade_date=date(y, m, d),
        trade_time=time,
        buy_sell=buy_sell,
        quantity=Decimal(quantity),
        trade_price=Decimal(price),
        realized_pnl=Decimal(pnl),
        commission=Decimal(commission),
        ib_order_id=order_id,
    )


def flex(*trades: RealizedTrade) -> FlexResult:
    return FlexResult(ok=True, trades=list(trades), account_id="U1")


def test_simple_long_round_trip():
    positions = build_positions(
        flex(
            trade("2026-01-05", "09:30:00", "BUY", "100", "10.00"),
            trade("2026-01-06", "09:30:00", "SELL", "100", "11.00", pnl="100"),
        )
    )

    assert len(positions) == 1
    p = positions[0]
    assert p.direction == "long"
    assert p.is_open is False
    assert p.is_carry_in is False
    assert p.open_date == date(2026, 1, 5)
    assert p.entry_price == Decimal("10.00")
    assert p.quantity == Decimal("100")
    assert p.exit_date == date(2026, 1, 6)
    assert p.exit_count == 1
    assert p.realized_pnl == Decimal("100")
    assert p.exit_legs[0].pct_of_position == Decimal("100")


def test_simple_short_round_trip():
    positions = build_positions(
        flex(
            trade("2026-01-05", "09:30:00", "SELL", "50", "20.00"),
            trade("2026-01-06", "09:30:00", "BUY", "50", "19.00", pnl="50"),
        )
    )

    assert len(positions) == 1
    p = positions[0]
    assert p.direction == "short"
    assert p.is_open is False
    assert p.is_carry_in is False
    assert p.realized_pnl == Decimal("50")


def test_carry_in_position_has_no_known_entry():
    """First trade for the symbol already realizes P&L: the opening trade
    happened before the fetched range. With nothing after it to prove the
    old lot is exhausted, it's honestly "still open" rather than a guess."""
    positions = build_positions(
        flex(
            trade("2026-01-05", "09:30:00", "SELL", "40", "22.00", pnl="80"),
        )
    )

    assert len(positions) == 1
    p = positions[0]
    assert p.is_carry_in is True
    assert p.direction == "long"  # a realizing sell must have been closing a long
    assert p.open_date is None
    assert p.open_time == ""
    assert p.entry_price is None
    assert p.quantity == Decimal("40")
    assert p.is_open is True
    assert p.realized_pnl == Decimal("80")


def test_carry_in_closes_only_once_a_fresh_open_proves_it():
    """Two consecutive realizing sells both close the same carry-in long;
    the fresh non-realizing buy afterwards proves the old lot is gone and
    starts a brand new position."""
    positions = build_positions(
        flex(
            trade("2026-01-05", "09:30:00", "SELL", "20", "22.00", pnl="40"),
            trade("2026-01-06", "09:30:00", "SELL", "20", "22.50", pnl="50"),
            trade("2026-01-07", "09:30:00", "BUY", "10", "23.00"),
        )
    )

    assert len(positions) == 2
    fresh_open = next(p for p in positions if not p.is_carry_in)
    carry_in = next(p for p in positions if p.is_carry_in)

    assert carry_in.exit_count == 2
    assert carry_in.quantity == Decimal("40")
    assert carry_in.realized_pnl == Decimal("90")
    assert carry_in.is_open is False

    assert fresh_open.direction == "long"
    assert fresh_open.is_open is True
    assert fresh_open.open_date == date(2026, 1, 7)
    assert fresh_open.quantity == Decimal("10")


def test_still_open_position_has_no_exits_yet():
    positions = build_positions(
        flex(
            trade("2026-01-05", "09:30:00", "BUY", "60", "228.31"),
        )
    )

    assert len(positions) == 1
    p = positions[0]
    assert p.is_open is True
    assert p.exit_count == 0
    assert p.exit_date is None
    assert p.realized_pnl is None
    assert p.quantity == Decimal("60")


def test_same_order_fills_collapse_into_one_leg():
    positions = build_positions(
        flex(
            trade("2026-01-05", "09:30:00", "BUY", "100", "10.00", order_id="X1"),
            trade("2026-01-05", "09:30:00", "BUY", "4", "10.00", order_id="X1"),
            trade("2026-01-06", "09:30:00", "SELL", "104", "11.00", pnl="104"),
        )
    )

    assert len(positions) == 1
    p = positions[0]
    assert len(p.entry_legs) == 1
    assert p.entry_legs[0].fill_count == 2
    assert p.entry_legs[0].quantity == Decimal("104")
    assert p.quantity == Decimal("104")


def test_flip_splits_into_two_positions():
    """Long 100, then one execution sells 150 -- closes the long and opens a
    50-share short in the same row."""
    positions = build_positions(
        flex(
            trade("2026-01-05", "09:30:00", "BUY", "100", "10.00"),
            trade("2026-01-06", "09:30:00", "SELL", "150", "11.00", pnl="100"),
        )
    )

    assert len(positions) == 2
    new_short = next(p for p in positions if p.direction == "short")
    closed_long = next(p for p in positions if p.direction == "long")

    assert closed_long.direction == "long"
    assert closed_long.is_open is False
    assert closed_long.quantity == Decimal("100")
    assert closed_long.realized_pnl == Decimal("100")

    assert new_short.direction == "short"
    assert new_short.is_open is True
    assert new_short.is_carry_in is False
    assert new_short.quantity == Decimal("50")
    assert new_short.entry_legs[0].quantity == Decimal("50")
    assert new_short.entry_legs[0].realized_pnl == Decimal("0")


def test_positions_are_scoped_per_symbol():
    positions = build_positions(
        flex(
            trade("2026-01-05", "09:30:00", "BUY", "10", "5.00", symbol="AAA"),
            trade("2026-01-05", "09:31:00", "SELL", "10", "5.50", pnl="5", symbol="AAA"),
            trade("2026-01-05", "09:32:00", "BUY", "20", "3.00", symbol="BBB"),
        )
    )

    symbols = {p.symbol for p in positions}
    assert symbols == {"AAA", "BBB"}
    bbb = next(p for p in positions if p.symbol == "BBB")
    assert bbb.is_open is True


def test_rktn_matches_the_worked_example():
    """The exact account data behind this feature, worked out by hand:

    Position 1 -- long, carry-in, closed over 5 sells Jan 9-21: +$335.22
    Position 2 -- long, opened & closed same day Jan 23: -$13.06
    Position 3 -- short, opened Jan 23, covered over 2 buys Jan 26: +$60.75
    """
    trades = flex(
        # Position 1: pre-existing long, closed piecemeal.
        trade("2026-01-09", "11:36:57", "SELL", "39", "22.64", pnl="136.50", symbol="RKTn", order_id="P1"),
        trade("2026-01-20", "09:54:57", "SELL", "19", "22.30", pnl="60.04", symbol="RKTn", order_id="P2"),
        trade("2026-01-21", "09:30:04", "SELL", "30", "21.75", pnl="78.30", symbol="RKTn", order_id="P3"),
        trade("2026-01-21", "12:34:32", "SELL", "15", "21.17", pnl="30.45", symbol="RKTn", order_id="P4"),
        trade("2026-01-21", "13:04:00", "SELL", "15", "21.135", pnl="29.93", symbol="RKTn", order_id="P5"),
        # Position 2: same-day round trip, exit split across 3 fills of one order.
        trade("2026-01-23", "11:17:55", "BUY", "268", "21.67", symbol="RKTn", order_id="O1"),
        trade("2026-01-23", "11:32:26", "SELL", "100", "21.62", pnl="-4.87", symbol="RKTn", order_id="O2"),
        trade("2026-01-23", "11:32:26", "SELL", "100", "21.62", pnl="-4.87", symbol="RKTn", order_id="O2"),
        trade("2026-01-23", "11:32:26", "SELL", "68", "21.6213", pnl="-3.32", symbol="RKTn", order_id="O2"),
        # Position 3: short, opened same day as position 2 closed, covered over two orders.
        trade("2026-01-23", "14:24:27", "SELL", "268", "21.215", symbol="RKTn", order_id="O3"),
        trade("2026-01-26", "04:03:15", "BUY", "65", "20.9846", pnl="14.975", symbol="RKTn", order_id="O4"),
        trade("2026-01-26", "04:03:15", "BUY", "65", "20.9846", pnl="14.975", symbol="RKTn", order_id="O4"),
        trade("2026-01-26", "04:17:11", "BUY", "27.6", "20.9918", pnl="6.16", symbol="RKTn", order_id="O5"),
        trade("2026-01-26", "04:17:11", "BUY", "27.6", "20.9918", pnl="6.16", symbol="RKTn", order_id="O5"),
        trade("2026-01-26", "04:17:11", "BUY", "27.6", "20.9918", pnl="6.16", symbol="RKTn", order_id="O5"),
        trade("2026-01-26", "04:17:11", "BUY", "27.6", "20.9918", pnl="6.16", symbol="RKTn", order_id="O5"),
        trade("2026-01-26", "04:17:11", "BUY", "27.6", "20.9918", pnl="6.16", symbol="RKTn", order_id="O5"),
    )

    positions = build_positions(trades)
    assert len(positions) == 3

    # Most recent activity first.
    pos3, pos2, pos1 = positions

    assert pos1.direction == "long"
    assert pos1.is_carry_in is True
    assert pos1.open_date is None
    assert pos1.entry_price is None
    assert pos1.quantity == Decimal("118")
    assert pos1.exit_date == date(2026, 1, 21)
    assert pos1.exit_count == 5
    assert pos1.realized_pnl == Decimal("335.22")

    assert pos2.direction == "long"
    assert pos2.is_carry_in is False
    assert pos2.open_date == date(2026, 1, 23)
    assert pos2.entry_price == Decimal("21.67")
    assert pos2.quantity == Decimal("268")
    assert pos2.exit_count == 1  # 3 fills of one order, one leg
    assert pos2.exit_legs[0].fill_count == 3
    assert round(pos2.realized_pnl, 2) == Decimal("-13.06")

    assert pos3.direction == "short"
    assert pos3.is_carry_in is False
    assert pos3.open_date == date(2026, 1, 23)
    assert pos3.entry_price == Decimal("21.215")
    assert pos3.quantity == Decimal("268")
    assert pos3.exit_count == 2
    assert pos3.exit_legs[0].quantity == Decimal("130")
    assert pos3.exit_legs[0].fill_count == 2
    assert pos3.exit_legs[1].quantity == Decimal("138")
    assert pos3.exit_legs[1].fill_count == 5
    assert round(pos3.realized_pnl, 2) == Decimal("60.75")
