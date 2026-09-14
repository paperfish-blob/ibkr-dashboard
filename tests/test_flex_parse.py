from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from ibkr_pnl.sources.flex import FlexError, parse_statement

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parses_all_trades_opens_included():
    """Opening trades (fifoPnlRealized=0, e.g. MSFT) are kept, not dropped --
    the transaction ledger shows every execution by default, same as IBKR's
    own apps. is_realizing is how the "Realized only" filter distinguishes
    them; totals are unaffected either way since an open contributes 0."""
    result = parse_statement(load("flex_sample.xml"))

    assert result.ok
    assert result.account_id == "U0000000"
    assert len(result.trades) == 4
    # AAPL and NVDA share a trade_date; only AAPL's fixture row carries a
    # time, so their relative order is incidental -- TSLA's date is later
    # and its position is the one guarantee worth pinning here.
    assert {t.symbol for t in result.trades} == {"AAPL", "NVDA", "MSFT", "TSLA"}
    assert result.trades[-1].symbol == "TSLA"

    by_symbol = {t.symbol: t for t in result.trades}
    assert by_symbol["MSFT"].is_realizing is False
    assert by_symbol["MSFT"].realized_pnl == Decimal("0")
    assert by_symbol["AAPL"].is_realizing is True

    total = sum(t.realized_pnl for t in result.trades)
    assert total == Decimal("584.75")  # MSFT's 0 doesn't move this


def test_parses_fields_and_dates():
    trades = {t.symbol: t for t in parse_statement(load("flex_sample.xml")).trades}
    trade = trades["AAPL"]

    assert trade.symbol == "AAPL"
    assert trade.trade_date == date(2026, 1, 5)
    assert trade.realized_pnl == Decimal("250.00")
    assert trade.commission == Decimal("-1.00")
    assert trade.currency == "USD"
    assert trade.asset_category == "STK"
    assert trade.buy_sell == "SELL"


def test_net_pnl_is_realized_pnl_plus_commission():
    """net_pnl is available as a commission-inclusive figure, but it is not
    what the dashboard displays: checked against a real account, gross
    (realized_pnl) matched Client Portal's own total; net did not. This
    just pins down the arithmetic of the field itself."""
    trades = {t.symbol: t for t in parse_statement(load("flex_sample.xml")).trades}
    aapl = trades["AAPL"]
    assert aapl.realized_pnl == Decimal("250.00")
    assert aapl.commission == Decimal("-1.00")
    assert aapl.net_pnl == Decimal("249.00")


def test_parses_the_ledger_fields_when_the_query_includes_them():
    """symbol/date/realized P&L/commission are always present; price, time,
    amount, order type and codes are optional -- only AAPL's fixture row
    carries them, to also exercise the "field not requested" path."""
    trades = {t.symbol: t for t in parse_statement(load("flex_sample.xml")).trades}

    aapl = trades["AAPL"]
    assert aapl.trade_time == "09:30:15"
    assert aapl.trade_price == Decimal("227.50")
    assert aapl.trade_money == Decimal("22750.00")
    assert aapl.order_type == "LMT"
    assert aapl.notes_codes == "C"
    assert aapl.exchange == "SMART"

    nvda = trades["NVDA"]
    assert nvda.trade_time == ""
    assert nvda.trade_price is None
    assert nvda.trade_money is None
    assert nvda.order_type == ""


def test_trades_come_back_in_date_order():
    dates = [t.trade_date for t in parse_statement(load("flex_sample.xml")).trades]
    assert dates == sorted(dates)


def test_failure_envelope_raises_rather_than_reading_as_zero():
    """An expired token arrives as HTTP 200 with Status=Fail. If we parsed it
    as an empty statement the dashboard would show a confident $0.00."""
    xml = """<FlexStatementResponse timestamp='11 September, 2026 12:00 PM EDT'>
    <Status>Fail</Status>
    <ErrorCode>1012</ErrorCode>
    <ErrorMessage>Token has expired.</ErrorMessage>
    </FlexStatementResponse>"""

    with pytest.raises(FlexError) as excinfo:
        parse_statement(xml)

    assert "1012" in str(excinfo.value)
    assert "expired" in str(excinfo.value).lower()


def test_multiple_levels_of_detail_are_not_double_counted():
    """A query configured with several levels emits one row per fill per
    level. Summing all of them multiplies realized P&L."""
    xml = """<FlexQueryResponse queryName="q" type="AF">
    <FlexStatements count="1"><FlexStatement accountId="U1">
    <Trades>
    <Trade symbol="AAPL" tradeDate="20260105" currency="USD"
           fifoPnlRealized="100.00" levelOfDetail="EXECUTION" />
    <Trade symbol="AAPL" tradeDate="20260105" currency="USD"
           fifoPnlRealized="100.00" levelOfDetail="ORDER" />
    <Trade symbol="AAPL" tradeDate="20260105" currency="USD"
           fifoPnlRealized="100.00" levelOfDetail="CLOSED_LOT" />
    </Trades>
    </FlexStatement></FlexStatements></FlexQueryResponse>"""

    result = parse_statement(xml)

    assert len(result.trades) == 1
    assert sum(t.realized_pnl for t in result.trades) == Decimal("100.00")


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("20260105", date(2026, 1, 5)),
        ("2026-01-05", date(2026, 1, 5)),
        ("20260105;093000", date(2026, 1, 5)),
    ],
)
def test_accepts_the_date_formats_flex_queries_emit(raw, expected):
    xml = f"""<FlexQueryResponse><FlexStatements><FlexStatement accountId="U1">
    <Trades><Trade symbol="X" tradeDate="{raw}" currency="USD"
    fifoPnlRealized="5" /></Trades>
    </FlexStatement></FlexStatements></FlexQueryResponse>"""

    assert parse_statement(xml).trades[0].trade_date == expected
