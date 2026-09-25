"""The CFD-suffix mapping and fetch_ohlcv's error handling -- the two things
that would otherwise fail silently or send the wrong ticker to Yahoo
Finance."""

import asyncio
import math
from datetime import date
from types import SimpleNamespace

from ibkr_pnl.models import OHLCVBar, StockSplit
from ibkr_pnl.sources.market_data import _patch_todays_bar, fetch_ohlcv, fetch_splits, plain_ticker


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


def _nan_bar(day: date) -> OHLCVBar:
    return OHLCVBar(time=day, open=math.nan, high=math.nan, low=math.nan, close=math.nan, volume=0)


def test_patch_todays_bar_fills_in_from_fast_info_when_close_is_nan():
    """`.history()`'s row for a session still in progress comes back all-NaN
    -- `fast_info` is the live-quote fallback that has real numbers mid-day."""
    fake_ticker = SimpleNamespace(
        fast_info=SimpleNamespace(open=176.09, day_high=176.09, day_low=170.24, last_price=174.26, last_volume=4_113_380)
    )
    patched = _patch_todays_bar(fake_ticker, _nan_bar(date(2026, 9, 22)))
    assert patched.time == date(2026, 9, 22)
    assert patched.open == 176.09
    assert patched.high == 176.09
    assert patched.low == 170.24
    assert patched.close == 174.26
    assert patched.volume == 4_113_380


def test_patch_todays_bar_falls_back_to_the_nan_bar_when_fast_info_has_nothing():
    """An unrecognized ticker, or Yahoo hiccuping on this call too, must not
    raise -- the caller already treats a NaN close as "no data for today"."""

    class BrokenFastInfo:
        @property
        def fast_info(self):
            raise RuntimeError("no data")

    nan_bar = _nan_bar(date(2026, 9, 22))
    patched = _patch_todays_bar(BrokenFastInfo(), nan_bar)
    assert patched is nan_bar


def test_fetch_ohlcv_treats_an_empty_series_as_not_ok():
    """A symbol Yahoo Finance doesn't recognize comes back as an empty list,
    not an error -- that still has to read as "no chart" rather than
    silently rendering a blank one."""

    def empty_fetcher(ticker: str, lookback_days: int) -> list[OHLCVBar]:
        return []

    result = asyncio.run(fetch_ohlcv("NOSUCHTICKERn", history_fetcher=empty_fetcher))
    assert result.ok is False
    assert result.error


def test_fetch_splits_strips_the_cfd_suffix_and_parses_a_successful_response():
    def fetcher(ticker: str) -> list[StockSplit]:
        assert ticker == "TSLA"
        return [StockSplit(date=date(2020, 8, 31), ratio=5.0), StockSplit(date=date(2022, 8, 25), ratio=3.0)]

    result = asyncio.run(fetch_splits("TSLAn", splits_fetcher=fetcher))
    assert result.ok is True
    assert result.symbol == "TSLA"
    assert len(result.splits) == 2
    assert result.splits[-1].ratio == 3.0


def test_fetch_splits_treats_a_never_split_symbol_as_ok_with_an_empty_list():
    """No splits is the normal case for most symbols, not an error."""

    def fetcher(ticker: str) -> list[StockSplit]:
        return []

    result = asyncio.run(fetch_splits("ARMn", splits_fetcher=fetcher))
    assert result.ok is True
    assert result.splits == []


def test_fetch_splits_reports_a_clear_error_when_the_lookup_raises():
    def failing_fetcher(ticker: str) -> list[StockSplit]:
        raise RuntimeError("boom")

    result = asyncio.run(fetch_splits("TSLAn", splits_fetcher=failing_fetcher))
    assert result.ok is False
    assert result.symbol == "TSLA"
    assert result.error
