"""Sector/industry classification, sourced from Finviz via finvizfinance.

Yahoo Finance's own `Ticker.info` has this too, but a slower, much larger
payload than `fast_info`/`.history()` -- Finviz's fundament page is a small,
purpose-built table, and this is the only place in the app that needs
classification data rather than prices.
"""

from __future__ import annotations

import asyncio
from typing import Callable

from finvizfinance.quote import finvizfinance

from ..models import CompanyInfoResult
from .market_data import plain_ticker

InfoFetcher = Callable[[str], tuple[str, str]]

# Finviz's fundament page is a real scrape (~1s round trip) and a company's
# sector/industry essentially never changes -- caching by plain ticker avoids
# re-scraping on every position-detail page load or manual refresh click for
# a symbol already looked up this process's lifetime.
_cache: dict[str, tuple[str, str]] = {}


def _fetch_info(ticker: str) -> tuple[str, str]:
    """Runs in a worker thread -- finvizfinance does blocking HTTP under the hood."""
    info = finvizfinance(ticker).ticker_fundament()
    return info.get("Sector", ""), info.get("Industry", "")


async def fetch_company_info(
    symbol: str,
    *,
    info_fetcher: InfoFetcher | None = None,
) -> CompanyInfoResult:
    """Sector and industry for one symbol. `info_fetcher` exists only so
    tests can substitute a fake instead of hitting Finviz."""
    ticker = plain_ticker(symbol)
    fetcher = info_fetcher or _fetch_info

    cached = _cache.get(ticker)
    if cached is not None:
        sector, industry = cached
        return CompanyInfoResult(ok=True, symbol=ticker, sector=sector, industry=industry)

    try:
        sector, industry = await asyncio.to_thread(fetcher, ticker)
    except Exception as exc:
        return CompanyInfoResult(ok=False, symbol=ticker, error=f"Finviz lookup failed: {exc}")
    if not sector and not industry:
        return CompanyInfoResult(ok=False, symbol=ticker, error=f"No sector/industry found for {ticker}")

    _cache[ticker] = (sector, industry)
    return CompanyInfoResult(ok=True, symbol=ticker, sector=sector, industry=industry)
