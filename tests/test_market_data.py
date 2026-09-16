"""The CFD-suffix mapping and fetch_ohlcv's error handling -- the two things
that would otherwise fail silently or send the wrong ticker to Yahoo
Finance."""

import asyncio
from datetime import date

from ibkr_pnl.models import OHLCVBar
from ibkr_pnl.sources.market_data import fetch_ohlcv, plain_ticker


def test_plain_ticker_strips_the_cfd_suffix():
    assert plain_ticker("ARMn") == "ARM"
    assert plain_ticker("AAPLn") == "AAPL"
    assert plain_ticker("AMZNn") == "AMZN"


def test_plain_ticker_leaves_non_cfd_symbols_alone():
    assert plain_ticker("AAPL") == "AAPL"
    assert plain_ticker("ARM") == "ARM"


def test_plain_ticker_is_a_noop_for_the_etf_cfds_that_break_the_pattern():
    """A handful of real CFD tickers (ETFs) don't carry the suffix at all --
    checked against a real account's data. Stripping only a trailing lower-
    case "n" is naturally a no-op for these, which is exactly right."""
    assert plain_ticker("SPY") == "SPY"
    assert plain_ticker("XLF") == "XLF"


def test_fetch_ohlcv_reports_a_clear_error_when_the_lookup_raises():
    def failing_fetcher(ticker: str, lookback_days: int) -> list[OHLCVBar]:
        raise RuntimeError("boom")

    result = asyncio.run(fetch_ohlcv("ARMn", history_fetcher=failing_fetcher))
    assert result.ok is False
    assert result.symbol == "ARM"
    assert result.error


def test_fetch_ohlcv_parses_a_successful_response():
    def fetcher(ticker: str, lookback_days: int) -> list[OHLCVBar]:
        assert ticker == "ARM"
        return [
            OHLCVBar(time=date(2026, 9, 15), open=240.0, high=245.0, low=238.0, close=244.0, volume=1_000_000),
            OHLCVBar(time=date(2026, 9, 16), open=244.0, high=250.0, low=243.0, close=247.4, volume=1_200_000),
        ]

    result = asyncio.run(fetch_ohlcv("ARMn", history_fetcher=fetcher))
    assert result.ok is True
    assert result.symbol == "ARM"
    assert len(result.bars) == 2
    assert result.bars[-1].close == 247.4


def test_fetch_ohlcv_treats_an_empty_series_as_not_ok():
    """A symbol Yahoo Finance doesn't recognize comes back as an empty list,
    not an error -- that still has to read as "no chart" rather than
    silently rendering a blank one."""

    def empty_fetcher(ticker: str, lookback_days: int) -> list[OHLCVBar]:
        return []

    result = asyncio.run(fetch_ohlcv("NOSUCHTICKERn", history_fetcher=empty_fetcher))
    assert result.ok is False
    assert result.error
