"""FastAPI app: serves the dashboard and the /api/pnl payload."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import aggregate, cache
from .config import PROJECT_ROOT, settings
from .models import PnLResponse, TransactionsResponse
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


app = FastAPI(title="IBKR Realized P&L", lifespan=lifespan)


@app.get("/api/pnl", response_model=PnLResponse)
async def get_pnl(refresh: bool = Query(False, description="Bypass the Flex cache")):
    """Realized P&L. Never fails because IB Gateway is down -- a missing
    Gateway just means today's figure falls back to Flex."""
    flex_result = await cache.get_flex(force_refresh=refresh)
    return aggregate.combine(flex_result, monitor.state)


@app.get("/api/transactions", response_model=TransactionsResponse)
async def get_transactions(refresh: bool = Query(False, description="Bypass the Flex cache")):
    """Per-trade ledger, newest day first. Sourced from Flex alone -- see
    aggregate.group_transactions for why Gateway has nothing to add here."""
    flex_result = await cache.get_flex(force_refresh=refresh)
    return aggregate.group_transactions(flex_result)


@app.get("/api/health")
async def health():
    cached = cache.read_cached()
    return {
        "gateway_connected": monitor.state.connected,
        "flex_configured": settings.flex_configured,
        "flex_cached_at": cached.fetched_at if cached else None,
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
