"""FIFO round-trip matching: pair each closing execution against the
specific opening lot(s) queued ahead of it, the same way IBKR's own
fifoPnlRealized is computed internally.

A position that opens, partially closes, adds again, and only later closes
out completely can therefore produce more than one round trip -- exactly
where IBKR's own P&L attribution would draw the line, even though a trader
would describe it as one continuous position. Concretely:

    09:56 BUY 217          (opens)
    10:02 SELL 100         (closes 100 of the 217 lot)
    11:15 BUY 50           (adds a second, later lot)
    14:30 SELL 167         (closes the 117 left of the first lot, then the
                            50 from the second)

produces three round trips, not one: (100 @ 09:56->10:02), (117 @
09:56->14:30), (50 @ 11:15->14:30). The alternative -- one row per
flat-to-flat position, blending multiple entry/exit prices into an average
-- was considered and rejected: this account trades the same symbol several
times a day, and FIFO matching is what actually determines each closing
trade's reported P&L, so it is what a trade-by-trade page should show.

Money is never recomputed. A closing execution's realized_pnl, and both
legs' commission, are Flex's own figures; when a close draws from more than
one lot, or a lot is closed by more than one later execution, this only
reapportions those already-correct totals by quantity share. Total
realized_pnl across every RoundTrip for a period reconciles exactly with
Transactions and Overview -- it can only be nonzero on a close, and every
close's realized_pnl is fully claimed by the round trip(s) it produces, so
none is ever left stranded. Commission does not reconcile in one specific
case: a position still open at the end of the fetched window has paid
commission on its opening executions but has not closed anything yet, so it
has no round trip to attach that commission to until a later statement
shows it closing. See the tests for both invariants.

CASH rows are excluded entirely -- see match() -- and don't figure into
either invariant.

Known limitation: matching starts from the first execution in whatever
years are downloaded, so a position already open when that window begins
has no visible opening lot. This is detected, not silently guessed at: Flex
marks such a trade with a nonzero realized_pnl (RealizedTrade.is_realizing)
regardless of whether anything is queued for it here, so an empty queue
with a realizing trade means the position was carried in rather than opened
fresh. That trade is emitted as a whole RoundTrip with opened_date=None
rather than treated as a fresh open, which would silently invent an entry
that never happened. For an account with years of history downloaded back
past any live position's true entry, this never arises.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from decimal import Decimal

from .models import FlexResult, RealizedTrade, RoundTrip


@dataclass
class _Lot:
    """A still-open slice of one opening execution, shrinking as later
    closes draw from it. commission_remaining shrinks in step, so each draw
    gets a fair share and the draw that empties the lot gets whatever
    precision remainder is left -- see _share.

    Always backed by a real trade: a lot with no visible opening is never
    queued at all (see match()), so there is nothing to draw down for it --
    it is emitted whole, once, the moment it is recognised."""

    trade: RealizedTrade
    remaining: Decimal
    commission_remaining: Decimal


def _share(remaining_total: Decimal, remaining_qty: Decimal, matched: Decimal) -> Decimal:
    """The fair slice of `remaining_total` (P&L or commission still
    unallocated) for a draw of `matched` out of `remaining_qty` outstanding.

    Exact by construction: a draw that exhausts what's left (matched ==
    remaining_qty) takes all of remaining_total rather than a computed
    fraction, so no per-share rounding remainder is ever stranded after the
    last draw. Every other draw takes a proportional share, quantized so a
    repeating fraction (say, 37/91) can't carry Decimal's full 28-digit
    precision into every downstream subtraction; whatever that rounding
    costs a given draw is still recovered exactly by the final one, since it
    always takes what's actually left rather than its own computed share.
    """
    if matched == remaining_qty:
        return remaining_total
    return (remaining_total * (matched / remaining_qty)).quantize(Decimal("0.000001"))


def _close_against(
    queue: deque[_Lot], closing: RealizedTrade, to_close: Decimal
) -> list[RoundTrip]:
    """Draw `to_close` units off the front of `queue`, FIFO, emitting one
    RoundTrip per lot it draws from.

    `to_close` must already be capped at what `queue` can actually supply
    (see match()) -- closing.realized_pnl and closing.commission are shared
    out over exactly `to_close`, so a `to_close` larger than the queue can
    fill would leave the closing lots underpaid and hand the shortfall to
    whatever leftover match() opens on the other side, which never
    genuinely closed anything and should carry none of it.
    """
    round_trips: list[RoundTrip] = []
    remaining_realized = closing.realized_pnl
    remaining_commission = closing.commission
    remaining_to_close = to_close

    while remaining_to_close > 0:
        lot = queue[0]
        matched = min(lot.remaining, remaining_to_close)

        pnl_share = _share(remaining_realized, remaining_to_close, matched)
        close_comm_share = _share(remaining_commission, remaining_to_close, matched)
        open_comm_share = _share(lot.commission_remaining, lot.remaining, matched)

        remaining_realized -= pnl_share
        remaining_commission -= close_comm_share
        remaining_to_close -= matched
        lot.remaining -= matched
        lot.commission_remaining -= open_comm_share

        round_trips.append(
            RoundTrip(
                symbol=closing.symbol,
                currency=closing.currency,
                asset_category=closing.asset_category,
                side="long" if lot.trade.quantity > 0 else "short",
                quantity=matched,
                opened_date=lot.trade.trade_date,
                opened_time=lot.trade.trade_time,
                open_price=lot.trade.trade_price,
                closed_date=closing.trade_date,
                closed_time=closing.trade_time,
                close_price=closing.trade_price,
                realized_pnl=pnl_share,
                commission=open_comm_share + close_comm_share,
                opening_trade=lot.trade,
                closing_trade=closing,
            )
        )

        if lot.remaining == 0:
            queue.popleft()

    return round_trips


def match(flex_result: FlexResult) -> list[RoundTrip]:
    """Every completed round trip across all symbols, newest closed first.

    CASH rows are excluded. Verified against a real account: a pair of
    USD.SGD "BUY" executions with asset_category CASH turned out to be IBKR
    funding the account's margin currency, not a trade -- and it was still
    open at the end of the fetched window, which is what a still-open
    position looks like here (its opening commission sits unclaimed in a
    lot nothing has closed yet). Nothing a user would call a "trade" belongs
    in this list with asset_category CASH, so it never enters matching.
    """
    trades = sorted(
        (t for t in flex_result.trades if t.asset_category != "CASH"),
        key=lambda t: (t.trade_date, t.trade_time),
    )

    queues: dict[str, deque[_Lot]] = {}
    sides: dict[str, str] = {}
    round_trips: list[RoundTrip] = []

    for trade in trades:
        qty = trade.quantity  # signed by Flex already: BUY positive, SELL negative
        if qty == 0:
            continue

        symbol = trade.symbol
        queue = queues.setdefault(symbol, deque())
        this_side = "long" if qty > 0 else "short"

        if queue and sides.get(symbol) == this_side:
            # Adding to a position already running the same direction:
            # nothing ahead of it to close against.
            queue.append(_Lot(trade=trade, remaining=abs(qty), commission_remaining=trade.commission))
            continue

        if not queue:
            if trade.is_realizing:
                # Flex itself says this closed something (realized_pnl != 0
                # is only possible for a close), yet nothing is on record
                # opening it -- the position was already running when this
                # data's window began. Emitted whole: there is no lot to
                # draw down further, and no entry to report.
                round_trips.append(
                    RoundTrip(
                        symbol=symbol,
                        currency=trade.currency,
                        asset_category=trade.asset_category,
                        # A BUY that closes something closed a short; a SELL
                        # that closes something closed a long.
                        side="short" if qty > 0 else "long",
                        quantity=abs(qty),
                        closed_date=trade.trade_date,
                        closed_time=trade.trade_time,
                        close_price=trade.trade_price,
                        realized_pnl=trade.realized_pnl,
                        commission=trade.commission,
                        closing_trade=trade,
                    )
                )
                continue
            # A genuine fresh open: realized_pnl is 0, so there is nothing
            # this could be closing.
            queue.append(_Lot(trade=trade, remaining=abs(qty), commission_remaining=trade.commission))
            sides[symbol] = this_side
            continue

        # Queue holds the opposite side: this execution closes it, FIFO.
        # to_close is capped at what the queue can actually supply -- see
        # _close_against's docstring for why realized_pnl/commission would
        # otherwise be shared out over more quantity than genuinely closed.
        available = sum((lot.remaining for lot in queue), Decimal(0))
        to_close = min(abs(qty), available)
        round_trips.extend(_close_against(queue, trade, to_close))

        leftover = abs(qty) - to_close
        if leftover > 0:
            # The execution's magnitude exceeded everything queued for the
            # opposite side -- a reversal in one execution. Flex is
            # documented (RealizedTrade.notes_codes: "O"/"C"/"P") to
            # sometimes split a reversal into separate rows instead, in
            # which case this branch is not reached for it; this is the
            # defensive path for whatever export does not split. The
            # leftover opens a fresh lot with 0 realized P&L, like any
            # opening slice -- the closing round trips above already took
            # the whole execution's realized_pnl and commission, since only
            # `to_close` units of it actually closed anything.
            queue.append(_Lot(trade=trade, remaining=leftover, commission_remaining=Decimal(0)))
            sides[symbol] = this_side
        elif not queue:
            sides.pop(symbol, None)

    return sorted(round_trips, key=lambda r: (r.closed_date, r.closed_time), reverse=True)
