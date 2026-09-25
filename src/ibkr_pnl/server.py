"""FastAPI app: serves the dashboard and the /api/pnl payload."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import aggregate, cache, positions as posmod
from .config import PROJECT_ROOT, settings
from .history import HistoryStatus, manager
from .models import (
    CompanyInfoResult,
    FlexResult,
    MarketDataResult,
    PnLResponse,
    PositionsResponse,
    SplitsResult,
    TransactionsResponse,
)
from .sources import company_info, market_data
from .sources.gateway import monitor

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

STATIC_DIR = Path(__file__).parent / "static"
FRONTEND_BUILD = PROJECT_ROOT / "frontend" / "build"


@asynccontextmanager
async def lifespan(app: FastAPI):
    monitor.start()
    try:
        yield
    finally:
        await monitor.stop()
        await manager.stop()


app = FastAPI(title="IBKR Realized P&L", lifespan=lifespan)


PERIOD_QUERY = Query(
    "all", description='"all" for every downloaded year, or a year like "2025"'
)


@app.get("/api/pnl", response_model=PnLResponse)
async def get_pnl(period: str = PERIOD_QUERY):
    """Realized P&L for a period. Never fails because IB Gateway is down -- a
    missing Gateway just means today's figure falls back to Flex."""
    flex_result, years = await cache.get_period(period)
    # Gateway reports P&L realized right now, which belongs to the current
    # year. Merging it into a past year would be contamination.
    covers_today = period == "all" or period == str(date.today().year)
    response = aggregate.combine(flex_result, monitor.state, covers_today=covers_today)
    return response.model_copy(update={"period": period, "years_covered": years})


@app.get("/api/transactions", response_model=TransactionsResponse)
async def get_transactions(period: str = PERIOD_QUERY):
    """Per-trade ledger, newest day first. Sourced from Flex alone -- see
    aggregate.group_transactions for why Gateway has nothing to add here."""
    flex_result, years = await cache.get_period(period)
    response = aggregate.group_transactions(flex_result)
    return response.model_copy(update={"period": period, "years_covered": years})


@app.get("/api/positions", response_model=PositionsResponse)
async def get_positions(period: str = PERIOD_QUERY):
    """Trades reconstructed into round-trip positions -- see positions.py."""
    flex_result, years = await cache.get_period(period)
    return PositionsResponse(
        positions=posmod.build_positions(flex_result),
        flex_ok=flex_result.ok,
        flex_error=flex_result.error,
        flex_fetched_at=flex_result.fetched_at,
        account_id=flex_result.account_id,
        period=period,
        years_covered=years,
    )


@app.get("/api/market-data/ohlcv", response_model=MarketDataResult)
async def get_market_data_ohlcv(symbol: str, lookback_days: int = Query(270, ge=1, le=3650)):
    """Daily bars for the Positions detail page's chart, via yfinance."""
    return await market_data.fetch_ohlcv(symbol, lookback_days=lookback_days)


@app.get("/api/market-data/company-info", response_model=CompanyInfoResult)
async def get_market_data_company_info(symbol: str):
    """Sector/industry for the Positions detail page's header, via Finviz."""
    return await company_info.fetch_company_info(symbol)


@app.get("/api/market-data/splits", response_model=SplitsResult)
async def get_market_data_splits(symbol: str):
    """A symbol's split history, so the Positions detail page's chart can
    put an old fill's price line on the same split-adjusted scale as its
    OHLCV bars, via yfinance."""
    return await market_data.fetch_splits(symbol)


@app.get("/api/history", response_model=HistoryStatus)
async def get_history():
    """Per-year download state for the History page."""
    return manager.status()


@app.post("/api/history/{year}")
async def download_year(year: int):
    """Start downloading one year's statement.

    Returns immediately: a statement takes 10-40s to generate, too long to
    hold an HTTP request open for. The page polls /api/history meanwhile.
    """
    started, message = manager.start(year)
    return {"started": started, "message": message}


@app.get("/api/history/{year}/raw", response_model=FlexResult)
async def get_history_raw(
    year: int,
    limit: int | None = Query(
        None,
        ge=1,
        description="Return only the first N trades -- a hover preview, not a page size",
    ),
):
    """The exact statement stored for one year, straight off disk.

    Read-only, and deliberately just the cache file as-is rather than routed
    through get_flex -- viewing a year must never be what triggers a fetch or
    disturbs its backoff state. 404 (not an empty FlexResult) for a year with
    nothing on disk, so "never downloaded" reads differently from "downloaded
    and turned out empty".

    `limit` exists for the History page's hover tooltip: that preview needs
    two or three trades, not all 700+, and fetching the whole statement on
    every hover would make hovering feel heavy. Leaving it unset -- what
    "View JSON" itself opens -- returns everything.
    """
    result = cache.read_cached(year)
    if result is None:
        raise HTTPException(status_code=404, detail=f"{year} has not been downloaded")
    if limit is not None:
        result = result.model_copy(update={"trades": result.trades[:limit]})
    return result


@app.get("/api/health")
async def health():
    current = cache.read_cached(date.today().year)
    return {
        "gateway_connected": monitor.state.connected,
        "flex_configured": settings.flex_configured,
        "flex_cached_at": current.fetched_at if current else None,
        "years_downloaded": cache.cached_years(),
    }


# ── Frontend ──────────────────────────────────────────────────────────────────
#
# Serve the SvelteKit build when it exists, else the original single-file
# dashboard. The fallback is what lets `uv run uvicorn` alone work on a fresh
# clone that has never run `npm install`.
#
# Everything below is registered after the /api routes above, so the catch-all
# cannot shadow them -- FastAPI matches routes in registration order.

if FRONTEND_BUILD.is_dir():

    def _resolve_frontend(path: str) -> Path | None:
        """Map a URL path to a file in the build, or None.

        adapter-static writes prerendered pages as `<route>.html`, which no
        static file server resolves from `/<route>` on its own -- hence the
        explicit suffix attempt rather than a plain StaticFiles mount.
        """
        relative = path.strip("/") or "index"
        candidates = (
            FRONTEND_BUILD / f"{relative}.html",  # prerendered page
            FRONTEND_BUILD / relative / "index.html",  # directory-style page
            FRONTEND_BUILD / relative,  # asset (JS, CSS, favicon…)
        )
        for candidate in candidates:
            # resolve() before the containment check: a path of "../.." would
            # otherwise escape the build directory.
            resolved = candidate.resolve()
            if not resolved.is_relative_to(FRONTEND_BUILD.resolve()):
                continue
            if resolved.is_file():
                return resolved
        return None

    @app.get("/{path:path}", include_in_schema=False)
    async def frontend(path: str):
        page = _resolve_frontend(path)
        if page is None:
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(page)

else:

    @app.get("/")
    async def index():
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
