"""Historical OHLCV bars, sourced directly from Yahoo Finance via yfinance.

No API key or separate service required. yfinance's own network calls are
blocking, so they're run off the event loop in a thread; a bad symbol or a
Yahoo hiccup comes back as a normal ok=False result rather than an error
page, matching how the rest of the app treats optional data.
"""

from __future__ import annotations

import asyncio
import math
import time
from datetime import date, timedelta
from typing import Callable

import yfinance as yf

from ..models import MarketDataResult, OHLCVBar, SplitsResult, StockSplit

HistoryFetcher = Callable[[str, int], list[OHLCVBar]]
SplitsFetcher = Callable[[str], list[StockSplit]]

# Every browser tab polling Open Positions hits this endpoint independently --
# with no cache, N tabs times M symbols is N*M real Yahoo requests on the same
# poll tick, well past what an unofficial, undocumented API can be trusted to
# absorb without a 429 or a temporary IP block. A short in-memory TTL cache
# means the actual Yahoo request rate stops scaling with how many tabs/users
# are open. Keyed on (ticker, lookback_days) since that's the full input to
# _fetch_history; only applies to real Yahoo calls (history_fetcher is None)
# so tests substituting a fake fetcher -- which all of them do -- always get
# a fresh, deterministic call rather than a stale cached result.
_CACHE_TTL_SECONDS = 60
_cache: dict[tuple[str, int], tuple[float, MarketDataResult]] = {}


# A handful of IBKR CFD tickers, once the CFD suffix is stripped, still
# don't match what Yahoo Finance actually lists -- not a suffix to strip,
# just a different spelling. Checked one at a time as they turn up rather
# than guessed at with a general rule (e.g. "drop the last letter and
# retry" would just as easily mangle a real short ticker on an unrelated
# Yahoo hiccup). Known so far: SanDisk's CFD carries an extra "V" -- likely
# left over from its 2025 spin-off out of Western Digital, before it
# settled back onto the plain "SNDK" ticker -- that Yahoo has never
# recognized.
_TICKER_OVERRIDES = {"SNDKV": "SNDK"}


def plain_ticker(symbol: str) -> str:
    """IBKR appends a lowercase "n" to CFD tickers (e.g. "ARMn" for the ARM
    CFD) -- real ticker symbols are always uppercase, so a trailing lowercase
    letter is unambiguous and safe to strip. Checked against a real account's
    283 distinct symbols: every STK/CASH ticker is plain, and of 205 CFD
    tickers only 6 (ETF CFDs like SPY, XLF) don't carry the suffix -- for
    those this is a no-op, which is exactly what's wanted."""
    ticker = symbol[:-1] if symbol.endswith("n") else symbol
    return _TICKER_OVERRIDES.get(ticker, ticker)


def _patch_todays_bar(t: yf.Ticker, bar: OHLCVBar) -> OHLCVBar:
    """`.history()`'s row for today comes back all-NaN while the session is
    still open -- Yahoo hasn't settled a daily close yet, only ticked a live
    quote. `fast_info` is a separate, lighter-weight endpoint that does have
    live values mid-session (today's open, high/low so far, last trade,
    volume so far), so it fills in that one row instead of leaving it NaN --
    which callers already have to skip past for their day-by-day math (see
    the frontend's own `typeof bar.close !== "number"` guard), and which
    otherwise means a position's current price and today's Unrealized P&L
    just come back blank until Yahoo backfills the real close overnight.
    Falls back to the NaN bar unchanged if `fast_info` itself has nothing --
    an unrecognized or delisted ticker, or Yahoo hiccuping on that call too.
    """
    try:
        fi = t.fast_info
        return OHLCVBar(
            time=bar.time,
            open=float(fi.open),
            high=float(fi.day_high),
            low=float(fi.day_low),
            close=float(fi.last_price),
            volume=int(fi.last_volume),
        )
    except Exception:
        return bar


def _fetch_history(ticker: str, lookback_days: int) -> list[OHLCVBar]:
    """Runs in a worker thread -- yfinance does blocking HTTP under the hood."""
    end = date.today() + timedelta(days=1)  # yfinance's `end` is exclusive
    start = end - timedelta(days=lookback_days)
    t = yf.Ticker(ticker)
    history = t.history(start=start, end=end, interval="1d")
    bars = [
        OHLCVBar(
            time=idx.date(),
            open=float(row["Open"]),
            high=float(row["High"]),
            low=float(row["Low"]),
            close=float(row["Close"]),
            volume=int(row["Volume"]),
        )
        for idx, row in history.iterrows()
    ]
    if bars and math.isnan(bars[-1].close):
        bars[-1] = _patch_todays_bar(t, bars[-1])
    return bars


async def fetch_ohlcv(
    symbol: str,
    *,
    lookback_days: int = 270,
    history_fetcher: HistoryFetcher | None = None,
) -> MarketDataResult:
    """Daily bars for one symbol, ascending by date. `history_fetcher` exists
    only so tests can substitute a fake instead of hitting Yahoo Finance --
    passing one also opts out of the cache below, so tests always see their
    own fetcher run."""
    ticker = plain_ticker(symbol)
    use_cache = history_fetcher is None
    cache_key = (ticker, lookback_days)
    if use_cache:
        cached = _cache.get(cache_key)
        if cached is not None and time.monotonic() - cached[0] < _CACHE_TTL_SECONDS:
            return cached[1]
    fetcher = history_fetcher or _fetch_history
    try:
        bars = await asyncio.to_thread(fetcher, ticker, lookback_days)
    except Exception as exc:
        return MarketDataResult(ok=False, symbol=ticker, error=f"Yahoo Finance lookup failed: {exc}")
    if not bars:
        return MarketDataResult(ok=False, symbol=ticker, error=f"No price history found for {ticker}")
    result = MarketDataResult(ok=True, symbol=ticker, bars=bars)
    if use_cache:
        _cache[cache_key] = (time.monotonic(), result)
    return result


def _fetch_splits(ticker: str) -> list[StockSplit]:
    """Runs in a worker thread -- yfinance does blocking HTTP under the hood."""
    return [StockSplit(date=idx.date(), ratio=float(ratio)) for idx, ratio in yf.Ticker(ticker).splits.items()]


async def fetch_splits(
    symbol: str,
    *,
    splits_fetcher: SplitsFetcher | None = None,
) -> SplitsResult:
    """A symbol's whole split history, ascending by date -- an empty list is
    the normal, successful result for a symbol that's never split. Positions
    reaches for this to convert an old, nominal fill price onto the
    split-adjusted scale `.history()`'s bars are already on (see the
    frontend's splitAdjustedPrice). `splits_fetcher` exists only so tests can
    substitute a fake instead of hitting Yahoo Finance."""
    ticker = plain_ticker(symbol)
    fetcher = splits_fetcher or _fetch_splits
    try:
        splits = await asyncio.to_thread(fetcher, ticker)
    except Exception as exc:
        return SplitsResult(ok=False, symbol=ticker, error=f"Yahoo Finance lookup failed: {exc}")
    return SplitsResult(ok=True, symbol=ticker, splits=splits)
