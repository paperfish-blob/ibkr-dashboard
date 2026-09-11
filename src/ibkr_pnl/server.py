"""FastAPI app: serves the dashboard and the /api/pnl payload."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import aggregate, cache
from .config import settings
from .models import PnLResponse
from .sources.gateway import monitor

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    monitor.start()
    try:
        yield
    finally:
        await monitor.stop()


app = FastAPI(title="IBKR Realized P&L", lifespan=lifespan)


@app.get("/api/pnl", response_model=PnLResponse)
async def get_pnl(refresh: bool = Query(False, description="Bypass the Flex cache")):
    """Realized P&L. Never fails because IB Gateway is down -- a missing
    Gateway just means today's figure falls back to Flex."""
    flex_result = await cache.get_flex(force_refresh=refresh)
    return aggregate.combine(flex_result, monitor.state)


@app.get("/api/health")
async def health():
    cached = cache.read_cached()
    return {
        "gateway_connected": monitor.state.connected,
        "flex_configured": settings.flex_configured,
        "flex_cached_at": cached.fetched_at if cached else None,
    }


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
