"""Merge the two sources into one answer.

The trap this module exists to avoid: reqPnL's realizedPnL resets to 0 each
trading day, so it is *today's* realized P&L rather than a running total.
Flex covers history but can also pick up part of today. Adding one to the
other double-counts today.

So: take Flex strictly before today, then add today from exactly one source.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from itertools import groupby

from .models import (
    CumulativePoint,
    FlexResult,
    GatewayState,
    PnLResponse,
    RealizedTrade,
    TodaySource,
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
    so we surface a warning rather than inventing an FX conversion."""
    currencies = sorted({t.currency for t in trades if t.currency})
    if not currencies:
        return "USD", ""
    if len(currencies) == 1:
        return currencies[0], ""
    return (
        currencies[0],
        "Statement spans multiple currencies ("
        + ", ".join(currencies)
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

    history_total = sum((t.realized_pnl for t in history), Decimal(0))

    # Today comes from exactly one source. Gateway wins when connected and
    # actually reporting a value -- it is live, where Flex is end-of-day.
    today_source: TodaySource
    if gateway_state.connected and gateway_state.realized_pnl is not None:
        today_total = gateway_state.realized_pnl
        today_source = "gateway"
    elif flex_today:
        today_total = sum((t.realized_pnl for t in flex_today), Decimal(0))
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
        trade_count=len(history) + (len(flex_today) if today_source == "flex" else 0),
        gateway=gateway_state,
        flex_ok=flex_result.ok,
        flex_error=flex_result.error,
        flex_fetched_at=flex_result.fetched_at,
        account_id=flex_result.account_id or gateway_state.account,
        currency_warning=currency_warning,
    )
