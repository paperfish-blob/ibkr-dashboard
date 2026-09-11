"""Disk cache for Flex statements.

The Flex token is limited to 1 request/second and 10/minute, and the
dashboard polls every 30s. Without a cache, a couple of open browser tabs
would exhaust the quota and start returning errors, so /api/pnl reads from
here and only goes to IBKR when the entry goes stale.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path

from .config import Settings, settings
from .models import FlexResult
from .sources import flex

_lock = asyncio.Lock()


def _cache_path(config: Settings) -> Path:
    return config.cache_dir / f"flex_{config.flex_query_id or 'unset'}.json"


def read_cached(config: Settings | None = None) -> FlexResult | None:
    config = config or settings
    path = _cache_path(config)
    if not path.exists():
        return None
    try:
        return FlexResult.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_cache(result: FlexResult, config: Settings) -> None:
    path = _cache_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Written 0600: a statement carries the account number and full trade history.
    path.write_text(result.model_dump_json(), encoding="utf-8")
    path.chmod(0o600)


def _is_fresh(result: FlexResult, config: Settings) -> bool:
    if result.fetched_at is None:
        return False
    age = datetime.now() - result.fetched_at
    return age < timedelta(seconds=config.flex_cache_ttl_seconds)


async def get_flex(
    *, force_refresh: bool = False, config: Settings | None = None
) -> FlexResult:
    """Return Flex data, fetching only when the cache is stale or forced."""
    config = config or settings

    cached = read_cached(config)
    if cached is not None and cached.ok and _is_fresh(cached, config) and not force_refresh:
        return cached

    if not config.flex_configured:
        return FlexResult(ok=False, error="FLEX_TOKEN and FLEX_QUERY_ID are not set in .env")

    async with _lock:
        # Another request may have refreshed while we waited for the lock.
        if not force_refresh:
            cached = read_cached(config)
            if cached is not None and cached.ok and _is_fresh(cached, config):
                return cached

        result = await flex.fetch(config)

    if result.ok:
        _write_cache(result, config)
        return result

    # Refresh failed. Prefer stale-but-real data over showing nothing, while
    # still surfacing the error so an expired token does not read as a
    # genuine zero.
    stale = read_cached(config)
    if stale is not None and stale.ok:
        return stale.model_copy(update={"error": result.error})
    return result
