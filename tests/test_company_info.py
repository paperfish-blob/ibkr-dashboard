"""fetch_company_info's error handling and caching -- the two things that
would otherwise send the wrong ticker to Finviz or hammer it on every
position-detail page load."""

import asyncio

import ibkr_pnl.sources.company_info as company_info_mod
from ibkr_pnl.sources.company_info import fetch_company_info


def setup_function():
    company_info_mod._cache.clear()


def test_fetch_company_info_strips_the_cfd_suffix_before_querying():
    def fetcher(ticker: str) -> tuple[str, str]:
        assert ticker == "ARM"
        return "Technology", "Semiconductors"

    result = asyncio.run(fetch_company_info("ARMn", info_fetcher=fetcher))
    assert result.ok is True
    assert result.symbol == "ARM"
    assert result.sector == "Technology"
    assert result.industry == "Semiconductors"


def test_fetch_company_info_reports_a_clear_error_when_the_lookup_raises():
    def failing_fetcher(ticker: str) -> tuple[str, str]:
        raise RuntimeError("boom")

    result = asyncio.run(fetch_company_info("ARMn", info_fetcher=failing_fetcher))
    assert result.ok is False
    assert result.symbol == "ARM"
    assert result.error


def test_fetch_company_info_caches_by_plain_ticker():
    calls = []

    def fetcher(ticker: str) -> tuple[str, str]:
        calls.append(ticker)
        return "Technology", "Semiconductors"

    asyncio.run(fetch_company_info("ARMn", info_fetcher=fetcher))
    asyncio.run(fetch_company_info("ARMn", info_fetcher=fetcher))
    asyncio.run(fetch_company_info("ARM", info_fetcher=fetcher))

    assert calls == ["ARM"]


def test_fetch_company_info_does_not_cache_a_failed_lookup():
    calls = []

    def failing_fetcher(ticker: str) -> tuple[str, str]:
        calls.append(ticker)
        raise RuntimeError("boom")

    asyncio.run(fetch_company_info("ARMn", info_fetcher=failing_fetcher))
    asyncio.run(fetch_company_info("ARMn", info_fetcher=failing_fetcher))

    assert calls == ["ARM", "ARM"]
