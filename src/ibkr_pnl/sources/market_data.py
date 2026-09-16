"""Historical OHLCV bars, sourced directly from Yahoo Finance via yfinance.

No API key or separate service required. yfinance's own network calls are
blocking, so they're run off the event loop in a thread; a bad symbol or a
Yahoo hiccup comes back as a normal ok=False result rather than an error
page, matching how the rest of the app treats optional data.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Callable

import yfinance as yf

from ..models import MarketDataResult, OHLCVBar

HistoryFetcher = Callable[[str, int], list[OHLCVBar]]


def plain_ticker(symbol: str) -> str:
    """IBKR appends a lowercase "n" to CFD tickers (e.g. "ARMn" for the ARM
    CFD) -- real ticker symbols are always uppercase, so a trailing lowercase
    letter is unambiguous and safe to strip. Checked against a real account's
    283 distinct symbols: every STK/CASH ticker is plain, and of 205 CFD
    tickers only 6 (ETF CFDs like SPY, XLF) don't carry the suffix -- for
    those this is a no-op, which is exactly what's wanted."""
    return symbol[:-1] if symbol.endswith("n") else symbol


def _fetch_history(ticker: str, lookback_days: int) -> list[OHLCVBar]:
    """Runs in a worker thread -- yfinance does blocking HTTP under the hood."""
    end = date.today() + timedelta(days=1)  # yfinance's `end` is exclusive
    start = end - timedelta(days=lookback_days)
    history = yf.Ticker(ticker).history(start=start, end=end, interval="1d")
    return [
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


async def fetch_ohlcv(
    symbol: str,
    *,
    lookback_days: int = 270,
    history_fetcher: HistoryFetcher | None = None,
) -> MarketDataResult:
    """Daily bars for one symbol, ascending by date. `history_fetcher` exists
    only so tests can substitute a fake instead of hitting Yahoo Finance."""
    ticker = plain_ticker(symbol)
    fetcher = history_fetcher or _fetch_history
    try:
        bars = await asyncio.to_thread(fetcher, ticker, lookback_days)
    except Exception as exc:
        return MarketDataResult(ok=False, symbol=ticker, error=f"Yahoo Finance lookup failed: {exc}")
    if not bars:
        return MarketDataResult(ok=False, symbol=ticker, error=f"No price history found for {ticker}")
    return MarketDataResult(ok=True, symbol=ticker, bars=bars)
