"""Reconstruct round-trip positions from the flat execution list.

The transaction ledger shows every execution grouped by day; this groups the
same executions by *position* instead -- a symbol's net quantity moving away
from zero and back, the way a trader thinks about a trade rather than a
statement line.

Two layers:

1. Collapse same-order fills (matching ib_order_id) into one "leg" per
   order, exactly like the ledger's "Group fills" view -- a position's entry
   or exit is usually one order, occasionally several fills of it.
2. Walk each symbol's legs in order, tracking a running signed quantity.
   A leg moving further from zero is an entry; a leg moving toward zero is
   an exit. Reaching zero closes the position; a leg that overshoots past
   zero in one execution (a flip) closes the old position with the portion
   that zeroes it and opens a new one with the remainder.

A position whose very first leg already realizes P&L before we have ever
seen the symbol go net-zero is a carry-in: the opening trade happened before
the fetched date range, so its date/time/price are unknown rather than
guessed -- see Position.is_carry_in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from .models import FlexResult, Position, PositionLeg, RealizedTrade


@dataclass
class _OrderRow:
    """One order's worth of fills for one symbol, already collapsed."""

    symbol: str
    asset_category: str
    currency: str
    trade_date: date
    trade_time: str
    buy_sell: str
    price: Decimal | None
    quantity: Decimal  # positive magnitude
    fill_count: int
    realized_pnl: Decimal
    commission: Decimal
    ib_order_id: str = ""

    @property
    def is_realizing(self) -> bool:
        return self.realized_pnl != 0

    def to_leg(self, *, quantity: Decimal | None = None, realized_pnl: Decimal | None = None) -> PositionLeg:
        return PositionLeg(
            trade_date=self.trade_date,
            trade_time=self.trade_time,
            buy_sell=self.buy_sell,
            price=self.price,
            quantity=self.quantity if quantity is None else quantity,
            fill_count=self.fill_count,
            realized_pnl=self.realized_pnl if realized_pnl is None else realized_pnl,
            commission=self.commission,
            ib_order_id=self.ib_order_id,
        )


def _group_by_order(trades: list[RealizedTrade]) -> list[_OrderRow]:
    """Collapse same-order fills within one symbol into one row each,
    chronological. Trades without an ib_order_id (an older Flex Query that
    doesn't request the field) never group -- each stays its own row."""
    by_order: dict[str, list[RealizedTrade]] = {}
    singles: list[RealizedTrade] = []
    for t in trades:
        if not t.ib_order_id:
            singles.append(t)
            continue
        by_order.setdefault(t.ib_order_id, []).append(t)

    rows: list[_OrderRow] = [
        _OrderRow(
            symbol=t.symbol,
            asset_category=t.asset_category,
            currency=t.currency,
            trade_date=t.trade_date,
            trade_time=t.trade_time,
            buy_sell=t.buy_sell,
            price=t.trade_price,
            quantity=abs(t.quantity),
            fill_count=1,
            realized_pnl=t.realized_pnl,
            commission=t.commission,
        )
        for t in singles
    ]
    for order_id, fills in by_order.items():
        first = fills[0]
        quantity = sum((abs(f.quantity) for f in fills), Decimal(0))
        has_price = all(f.trade_price is not None for f in fills)
        price = (
            sum((f.trade_price * abs(f.quantity) for f in fills), Decimal(0)) / quantity
            if has_price and quantity
            else None
        )
        earliest = min(fills, key=lambda f: f.trade_time)
        rows.append(
            _OrderRow(
                symbol=first.symbol,
                asset_category=first.asset_category,
                currency=first.currency,
                trade_date=earliest.trade_date,
                trade_time=earliest.trade_time,
                buy_sell=first.buy_sell,
                price=price,
                quantity=quantity,
                fill_count=len(fills),
                realized_pnl=sum((f.realized_pnl for f in fills), Decimal(0)),
                commission=sum((f.commission for f in fills), Decimal(0)),
                ib_order_id=order_id,
            )
        )

    rows.sort(key=lambda r: (r.trade_date, r.trade_time))
    return rows


@dataclass
class _Accumulator:
    symbol: str
    asset_category: str
    currency: str
    direction: str  # "long" | "short"
    is_carry_in: bool
    entry_legs: list[PositionLeg] = field(default_factory=list)
    exit_legs: list[PositionLeg] = field(default_factory=list)

    def finalize(self, *, is_open: bool) -> Position:
        entry_total = sum((leg.quantity for leg in self.entry_legs), Decimal(0))
        exit_total = sum((leg.quantity for leg in self.exit_legs), Decimal(0))
        # The size legs' percentages are relative to -- the best-known
        # original size, regardless of whether the position ended up open,
        # closed, or is a still-open carry-in.
        known_total = entry_total if entry_total else exit_total
        exit_legs = [
            leg.model_copy(
                update={
                    "pct_of_position": (
                        (leg.quantity / known_total * 100) if known_total else None
                    )
                }
            )
            for leg in self.exit_legs
        ]

        if is_open:
            quantity = (
                entry_total + exit_total  # best-known activity; true size unknown
                if self.is_carry_in
                else entry_total - exit_total  # currently remaining open
            )
        else:
            # Exact and correct either way once flat: for a carry-in it's
            # the only number we ever had; for a normal position it equals
            # entry_total too.
            quantity = exit_total

        first_entry = self.entry_legs[0] if self.entry_legs and not self.is_carry_in else None
        last_exit = self.exit_legs[-1] if self.exit_legs else None

        return Position(
            symbol=self.symbol,
            asset_category=self.asset_category,
            currency=self.currency,
            direction=self.direction,  # type: ignore[arg-type]
            is_open=is_open,
            is_carry_in=self.is_carry_in,
            open_date=first_entry.trade_date if first_entry else None,
            open_time=first_entry.trade_time if first_entry else "",
            entry_price=(
                None
                if self.is_carry_in or not self.entry_legs
                else _weighted_price(self.entry_legs)
            ),
            quantity=quantity,
            exit_date=last_exit.trade_date if last_exit else None,
            exit_count=len(self.exit_legs),
            realized_pnl=(
                sum((leg.realized_pnl for leg in self.exit_legs), Decimal(0))
                if self.exit_legs
                else None
            ),
            commission=sum(
                (leg.commission for leg in (*self.entry_legs, *self.exit_legs)), Decimal(0)
            ),
            entry_legs=self.entry_legs,
            exit_legs=exit_legs,
        )


def _weighted_price(legs: list[PositionLeg]) -> Decimal | None:
    if any(leg.price is None for leg in legs):
        return None
    total_qty = sum((leg.quantity for leg in legs), Decimal(0))
    if not total_qty:
        return None
    return sum((leg.price * leg.quantity for leg in legs), Decimal(0)) / total_qty


def _last_activity(position: Position) -> tuple[date, str]:
    """Sort key: most recently touched position first, open or closed."""
    candidates = [(leg.trade_date, leg.trade_time) for leg in (*position.entry_legs, *position.exit_legs)]
    return max(candidates)


def _positions_for_symbol(rows: list[_OrderRow]) -> list[Position]:
    positions: list[Position] = []
    qty = Decimal(0)
    current: _Accumulator | None = None

    for row in rows:
        delta = row.quantity if row.buy_sell.upper() == "BUY" else -row.quantity

        # A carry-in's true original size is unknown, so signed-quantity
        # tracking can never tell us when it's back to flat -- our own
        # running total never touches the real number. The only fact we can
        # trust is IBKR's own is_realizing flag: an opening trade never
        # realizes P&L, so the first non-realizing trade after a carry-in
        # proves the old lot is exhausted and something new has begun.
        # Consecutive realizing trades, however many, all still close it.
        if current is not None and current.is_carry_in:
            if row.is_realizing:
                current.exit_legs.append(row.to_leg())
                continue
            positions.append(current.finalize(is_open=False))
            current = None
            qty = Decimal(0)

        if current is None:
            is_carry_in = row.is_realizing
            direction = ("long" if delta < 0 else "short") if is_carry_in else ("long" if delta > 0 else "short")
            current = _Accumulator(row.symbol, row.asset_category, row.currency, direction, is_carry_in)
            if is_carry_in:
                current.exit_legs.append(row.to_leg())
            else:
                current.entry_legs.append(row.to_leg())
                qty += delta
            continue

        is_entry = (delta > 0) == (current.direction == "long")
        if is_entry:
            current.entry_legs.append(row.to_leg())
            qty += delta
            continue

        qty_before = qty
        qty_after = qty + delta
        flips = (qty_before > 0 and qty_after < 0) or (qty_before < 0 and qty_after > 0)
        if not flips:
            current.exit_legs.append(row.to_leg())
            qty = qty_after
            if qty == 0:
                positions.append(current.finalize(is_open=False))
                current = None
            continue

        # This single execution both closes the open position and opens a
        # new one on the other side. IBKR's reported realized_pnl covers
        # only the closing portion (the newly opened shares have no P&L
        # yet), so the whole figure goes to the closing leg; the opening
        # remainder starts the next position at zero P&L, same as any
        # other fresh open.
        closing_qty = abs(qty_before)
        leftover_qty = row.quantity - closing_qty
        current.exit_legs.append(row.to_leg(quantity=closing_qty))
        positions.append(current.finalize(is_open=False))

        new_direction = "short" if current.direction == "long" else "long"
        current = _Accumulator(row.symbol, row.asset_category, row.currency, new_direction, is_carry_in=False)
        current.entry_legs.append(row.to_leg(quantity=leftover_qty, realized_pnl=Decimal(0)))
        qty = qty_after

    if current is not None:
        positions.append(current.finalize(is_open=True))

    return positions


def build_positions(flex_result: FlexResult) -> list[Position]:
    """Every trade turned into round-trip positions, most recent activity
    first. Each symbol is walked independently and in isolation -- a
    position never spans two symbols."""
    by_symbol: dict[str, list[RealizedTrade]] = {}
    for t in flex_result.trades:
        by_symbol.setdefault(t.symbol, []).append(t)

    positions: list[Position] = []
    for trades in by_symbol.values():
        rows = _group_by_order(trades)
        positions.extend(_positions_for_symbol(rows))

    positions.sort(key=_last_activity, reverse=True)
    return positions
