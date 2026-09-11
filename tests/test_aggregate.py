"""The merge rule. reqPnL's realizedPnL resets daily, so it is today's figure
only; Flex covers history but can also pick up today. These tests pin down
that the two never get added together for the same day."""

from datetime import date
from decimal import Decimal

from ibkr_pnl.aggregate import combine
from ibkr_pnl.models import FlexResult, GatewayState, RealizedTrade

TODAY = date(2026, 9, 11)


def trade(day: date, amount: str, symbol: str = "AAPL", currency: str = "USD") -> RealizedTrade:
    return RealizedTrade(
        symbol=symbol,
        trade_date=day,
        realized_pnl=Decimal(amount),
        currency=currency,
    )


def flex(*trades: RealizedTrade) -> FlexResult:
    return FlexResult(ok=True, trades=list(trades), account_id="U1")


def test_gateway_replaces_rather_than_adds_to_flex_today():
    """The core trap: Flex has already picked up today's trades AND Gateway
    reports today's realized P&L. Naively summing gives 1000 + 300 + 300."""
    result = combine(
        flex(
            trade(date(2026, 9, 10), "1000"),
            trade(TODAY, "300"),
        ),
        GatewayState(connected=True, realized_pnl=Decimal("300")),
        today=TODAY,
    )

    assert result.headline == Decimal("1300")
    assert result.today == Decimal("300")
    assert result.today_source == "gateway"


def test_gateway_value_wins_when_it_disagrees_with_flex():
    """Gateway is live and Flex is end-of-day, so a mid-session disagreement
    should resolve to Gateway -- not to a sum, and not to the stale figure."""
    result = combine(
        flex(trade(date(2026, 9, 10), "1000"), trade(TODAY, "100")),
        GatewayState(connected=True, realized_pnl=Decimal("450")),
        today=TODAY,
    )

    assert result.headline == Decimal("1450")
    assert result.today == Decimal("450")


def test_falls_back_to_flex_when_gateway_is_down():
    result = combine(
        flex(trade(date(2026, 9, 10), "1000"), trade(TODAY, "300")),
        GatewayState(connected=False),
        today=TODAY,
    )

    assert result.headline == Decimal("1300")
    assert result.today == Decimal("300")
    assert result.today_source == "flex"


def test_connected_gateway_with_no_value_yet_falls_back_to_flex():
    """reqPnL returns an object with unset fields before the first pnlEvent
    lands, which must not be read as a real zero for today."""
    result = combine(
        flex(trade(date(2026, 9, 10), "1000"), trade(TODAY, "300")),
        GatewayState(connected=True, realized_pnl=None),
        today=TODAY,
    )

    assert result.today == Decimal("300")
    assert result.today_source == "flex"


def test_no_activity_today():
    result = combine(
        flex(trade(date(2026, 9, 10), "1000")),
        GatewayState(connected=False),
        today=TODAY,
    )

    assert result.headline == Decimal("1000")
    assert result.today == Decimal("0")
    assert result.today_source == "none"


def test_cumulative_series_runs_and_ends_at_the_headline():
    result = combine(
        flex(
            trade(date(2026, 9, 8), "100"),
            trade(date(2026, 9, 9), "-40"),
            trade(date(2026, 9, 9), "10"),
            trade(date(2026, 9, 10), "30"),
        ),
        GatewayState(connected=True, realized_pnl=Decimal("5")),
        today=TODAY,
    )

    assert [(p.date, p.cumulative) for p in result.series] == [
        (date(2026, 9, 8), Decimal("100")),
        (date(2026, 9, 9), Decimal("70")),  # same-day trades net together
        (date(2026, 9, 10), Decimal("100")),
        (TODAY, Decimal("105")),
    ]
    assert result.series[-1].cumulative == result.headline


def test_multi_currency_statement_is_flagged_not_silently_summed():
    result = combine(
        flex(
            trade(date(2026, 9, 10), "1000", currency="USD"),
            trade(date(2026, 9, 10), "500", currency="EUR"),
        ),
        GatewayState(connected=False),
        today=TODAY,
    )

    assert "multiple currencies" in result.currency_warning
    assert "EUR" in result.currency_warning and "USD" in result.currency_warning


def test_flex_failure_is_carried_through_to_the_response():
    result = combine(
        FlexResult(ok=False, error="Flex error 1012: Token has expired."),
        GatewayState(connected=False),
        today=TODAY,
    )

    assert result.flex_ok is False
    assert "1012" in result.flex_error
    assert result.series == []
