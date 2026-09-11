from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from ibkr_pnl.sources.flex import FlexError, parse_statement

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parses_realizing_trades():
    result = parse_statement(load("flex_sample.xml"))

    assert result.ok
    assert result.account_id == "U0000000"
    # The MSFT opening trade has fifoPnlRealized=0 and is dropped as noise.
    assert len(result.trades) == 3
    assert [t.symbol for t in result.trades] == ["AAPL", "NVDA", "TSLA"]

    total = sum(t.realized_pnl for t in result.trades)
    assert total == Decimal("584.75")


def test_parses_fields_and_dates():
    trade = parse_statement(load("flex_sample.xml")).trades[0]

    assert trade.symbol == "AAPL"
    assert trade.trade_date == date(2026, 1, 5)
    assert trade.realized_pnl == Decimal("250.00")
    assert trade.commission == Decimal("-1.00")
    assert trade.currency == "USD"
    assert trade.asset_category == "STK"
    assert trade.buy_sell == "SELL"


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
