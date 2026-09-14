"""Merge the two sources into one answer.

The trap this module exists to avoid: reqPnL's realizedPnL resets to 0 each
trading day, so it is *today's* realized P&L rather than a running total.
Flex covers history but can also pick up part of today. Adding one to the
other double-counts today.

So: take Flex strictly before today, then add today from exactly one source.

Everything summed from Flex trades uses RealizedTrade.realized_pnl (gross),
not net_pnl. This was checked against a real account two ways: the
whole-statement gross sum landed within $1.16 of Client Portal's own YTD
total (fully explained by a handful of trades in the few days outside the
fetched range), while the net sum was off by $371 -- IBKR's own "Realized
P&L" is gross; commission is shown as a separate line, not netted in.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from decimal import Decimal
from itertools import groupby

from .models import (
    CumulativePoint,
    DayGroup,
    FlexResult,
    GatewayState,
    PnLResponse,
    RealizedTrade,
    TodaySource,
    TransactionsResponse,
)


def _build_series(trades: list[RealizedTrade]) -> list[CumulativePoint]:
    """Daily buckets, running-summed. Only days with activity get a point."""
    points: list[CumulativePoint] = []
    running = Decimal(0)
    ordered = sorted(trades, key=lambda t: t.trade_date)
    for day, group in groupby(ordered, key=lambda t: t.trade_date):
        daily = sum((t.realized_pnl for t in group), Decimal(0))
        running += daily
        points.append(CumulativePoint(date=day, realized_pnl=daily, cumulative=running))
    return points


def _resolve_currency(trades: list[RealizedTrade]) -> tuple[str, str]:
    """Return (currency, warning). Summing across currencies is meaningless,
    so we surface a warning rather than inventing an FX conversion.

    Only trades that actually carry realized P&L count. An opening trade
    contributes exactly 0, so its currency cannot distort any total -- it must
    not relabel the headline or raise a warning. A real account showed why:
    two SGD opening trades among 698 USD ones were enough to relabel an
    entirely USD figure as SGD and warn about an FX exposure that did not
    exist.

    Among currencies that do contribute, the most common wins rather than the
    alphabetically first -- "SGD" sorting before "USD" is what made the
    mislabel possible.
    """
    counts = Counter(t.currency for t in trades if t.is_realizing and t.currency)
    if not counts:
        return "USD", ""
    currency = counts.most_common(1)[0][0]
    if len(counts) == 1:
        return currency, ""
    return (
        currency,
        "Statement spans multiple currencies ("
        + ", ".join(sorted(counts))
        + "); totals add raw values without FX conversion.",
    )


def combine(
    flex_result: FlexResult,
    gateway_state: GatewayState,
    today: date | None = None,
) -> PnLResponse:
    today = today or date.today()
    trades = flex_result.trades

    history = [t for t in trades if t.trade_date < today]
    flex_today = [t for t in trades if t.trade_date >= today]
    # Opening trades are now kept in flex_result.trades (for the ledger), so
    # "is there Flex data for today" has to mean a realizing trade -- a day
    # of opens-only would otherwise mislabel today_source as "flex" for a
    # figure that's actually just zero the same as "none" would give.
    flex_today_realizing = [t for t in flex_today if t.is_realizing]

    history_total = sum((t.realized_pnl for t in history), Decimal(0))

    # Today comes from exactly one source. Gateway wins when connected and
    # actually reporting a value -- it is live, where Flex is end-of-day.
    today_source: TodaySource
    if gateway_state.connected and gateway_state.realized_pnl is not None:
        today_total = gateway_state.realized_pnl
        today_source = "gateway"
    elif flex_today_realizing:
        today_total = sum((t.realized_pnl for t in flex_today_realizing), Decimal(0))
        today_source = "flex"
    else:
        today_total = Decimal(0)
        today_source = "none"

    series = _build_series(history)
    if today_source != "none" or series:
        running = series[-1].cumulative if series else Decimal(0)
        series.append(
            CumulativePoint(
                date=today,
                realized_pnl=today_total,
                cumulative=running + today_total,
            )
        )

    currency, currency_warning = _resolve_currency(trades)

    return PnLResponse(
        headline=history_total + today_total,
        today=today_total,
        currency=currency,
        today_source=today_source,
        series=series,
        trade_count=len([t for t in history if t.is_realizing])
        + (len(flex_today_realizing) if today_source == "flex" else 0),
        gateway=gateway_state,
        flex_ok=flex_result.ok,
        flex_error=flex_result.error,
        flex_fetched_at=flex_result.fetched_at,
        account_id=flex_result.account_id or gateway_state.account,
        currency_warning=currency_warning,
    )


def group_transactions(flex_result: FlexResult) -> TransactionsResponse:
    """Group Flex trades into a per-day ledger, newest day first.

    Includes every execution -- opens and closes alike -- matching IBKR's
    own apps; the frontend's "Realized only" filter (default: off) hides
    the opens client-side via RealizedTrade.is_realizing. total_realized and
    each day's total_pnl are unaffected by the filter either way, since an
    opening trade's realized_pnl is exactly 0.

    This is a straight transcription of the statement -- there is no
    Gateway/today merge here. Gateway's reqPnL gives aggregate figures only
    (realized/unrealized/daily), never a per-trade ledger, so live trades
    show up here once Flex's next statement includes them.
    """
    trades = flex_result.trades

    by_day: dict = {}
    for trade in trades:
        by_day.setdefault(trade.trade_date, []).append(trade)

    days = [
        DayGroup(
            date=day,
            total_pnl=sum((t.realized_pnl for t in day_trades), Decimal(0)),
            # Newest execution first within the day, matching the reference view.
            trades=sorted(day_trades, key=lambda t: t.trade_time, reverse=True),
        )
        for day, day_trades in sorted(by_day.items(), reverse=True)
    ]

    dates = [t.trade_date for t in trades]

    return TransactionsResponse(
        total_realized=sum((t.realized_pnl for t in trades), Decimal(0)),
        trade_count=len(trades),
        from_date=min(dates) if dates else None,
        to_date=max(dates) if dates else None,
        days=days,
        flex_ok=flex_result.ok,
        flex_error=flex_result.error,
        flex_fetched_at=flex_result.fetched_at,
        account_id=flex_result.account_id,
    )
