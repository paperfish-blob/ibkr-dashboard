"""The merge rule. reqPnL's realizedPnL resets daily, so it is today's figure
only; Flex covers history but can also pick up today. These tests pin down
that the two never get added together for the same day."""

from datetime import date
from decimal import Decimal

from ibkr_pnl.aggregate import combine, group_transactions
from ibkr_pnl.models import FlexResult, GatewayState, RealizedTrade

TODAY = date(2026, 9, 11)


def trade(
    day: date,
    amount: str,
    symbol: str = "AAPL",
    currency: str = "USD",
    time: str = "",
    commission: str = "0",
) -> RealizedTrade:
    return RealizedTrade(
        symbol=symbol,
        trade_date=day,
        trade_time=time,
        realized_pnl=Decimal(amount),
        commission=Decimal(commission),
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


def test_opening_trades_today_do_not_masquerade_as_flex_data():
    """flex_result.trades now includes opens (kept for the ledger). A day
    that only opened positions must still read as today_source="none", not
    "flex" -- both give today=$0, but "flex" would misleadingly claim Flex
    had a realized figure for today when it only had opens."""
    result = combine(
        flex(
            trade(date(2026, 9, 10), "1000"),
            trade(TODAY, "0", symbol="B"),  # opened today, nothing realized
        ),
        GatewayState(connected=False),
        today=TODAY,
    )

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


class TestGroupTransactions:
    """The per-trade ledger view: newest day first, newest trade within a
    day first, each day carrying its own subtotal."""

    def test_opening_trades_are_included_by_default(self):
        """The ledger's default view is every execution, opens included --
        the "Realized only" filter that hides them lives client-side."""
        result = group_transactions(
            flex(
                trade(date(2026, 9, 10), "0", symbol="OPEN"),  # opened, no P&L yet
                trade(date(2026, 9, 10), "250", symbol="CLOSE"),
            )
        )

        assert result.trade_count == 2
        symbols = {t.symbol for t in result.days[0].trades}
        assert symbols == {"OPEN", "CLOSE"}
        by_symbol = {t.symbol: t for t in result.days[0].trades}
        assert by_symbol["OPEN"].is_realizing is False
        assert by_symbol["CLOSE"].is_realizing is True
        # The open contributes nothing to the total either way.
        assert result.days[0].total_pnl == Decimal("250")
        assert result.total_realized == Decimal("250")

    def test_groups_by_day_newest_first(self):
        result = group_transactions(
            flex(
                trade(date(2026, 9, 8), "100"),
                trade(date(2026, 9, 10), "-40"),
                trade(date(2026, 9, 10), "10"),
            )
        )

        assert [d.date for d in result.days] == [date(2026, 9, 10), date(2026, 9, 8)]
        assert result.days[0].total_pnl == Decimal("-30")
        assert result.days[1].total_pnl == Decimal("100")
        assert result.trade_count == 3
        assert result.total_realized == Decimal("70")
        assert result.from_date == date(2026, 9, 8)
        assert result.to_date == date(2026, 9, 10)

    def test_trades_within_a_day_are_newest_time_first(self):
        result = group_transactions(
            flex(
                trade(date(2026, 9, 10), "10", symbol="A", time="09:00:00"),
                trade(date(2026, 9, 10), "20", symbol="B", time="15:30:00"),
            )
        )

        assert [t.symbol for t in result.days[0].trades] == ["B", "A"]

    def test_no_gateway_merge_here_it_is_a_straight_transcription(self):
        """Unlike combine(), the ledger has no "today" concept to reconcile
        -- Gateway never supplies per-trade data, so there is nothing to
        double-count against."""
        result = group_transactions(flex(trade(TODAY, "500")))

        assert result.total_realized == Decimal("500")
        assert result.days[0].date == TODAY

    def test_empty_statement(self):
        result = group_transactions(flex())

        assert result.days == []
        assert result.trade_count == 0
        assert result.from_date is None
        assert result.to_date is None

    def test_carries_flex_failure_through(self):
        result = group_transactions(FlexResult(ok=False, error="Flex error 1012: Token has expired."))

        assert result.flex_ok is False
        assert "1012" in result.flex_error
        assert result.days == []

    def test_totals_are_gross_and_ignore_commission(self):
        """fifoPnlRealized is gross. Checked against a real account: the
        whole-statement gross sum matched Client Portal's own YTD total to
        within a few dollars (explained by trades outside the fetched date
        range), while netting out commission was off by hundreds -- IBKR's
        own figure is gross, with commission shown as a separate line."""
        result = group_transactions(
            flex(
                trade(date(2026, 9, 10), "250.00", commission="-1.00"),
                trade(date(2026, 9, 10), "-75.50", symbol="B", commission="-1.00"),
            )
        )

        assert result.days[0].total_pnl == Decimal("174.50")  # 250 + (-75.5), commission ignored
        assert result.total_realized == Decimal("174.50")


class TestCombineIsAlsoGrossAndIgnoresCommission:
    def test_history_and_today_totals_ignore_commission(self):
        result = combine(
            flex(
                trade(date(2026, 9, 10), "1000", commission="-2.00"),
                trade(TODAY, "300", commission="-1.00"),
            ),
            GatewayState(connected=False),
            today=TODAY,
        )

        assert result.headline == Decimal("1300")  # 1000 + 300, commission ignored
        assert result.today == Decimal("300")
