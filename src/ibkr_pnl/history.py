"""Per-year statement downloads for the History page.

One download runs at a time. A year costs 1 SendRequest plus up to 5
GetStatement polls against a token limited to 1 request/second and 10/minute,
and takes 10-40s, so downloads are strictly serialised. A second request while
one is running is refused outright (`started: False`) rather than queued --
a refusal the page can explain beats a queue nobody can see.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from . import cache
from .config import Settings, settings

logger = logging.getLogger(__name__)

YearState = Literal["missing", "downloading", "stored", "error"]


class YearStatus(BaseModel):
    year: int
    state: YearState
    trade_count: int = 0
    realizing_count: int = 0
    realized_pnl: Decimal = Decimal(0)
    currency: str = "USD"
    downloaded_at: datetime | None = None
    error: str = ""
    is_current: bool = False
    # A closed, settled year never needs downloading again.
    immutable: bool = False
    started_at: datetime | None = None


class HistoryStatus(BaseModel):
    years: list[YearStatus]
    downloading: int | None = None


class HistoryManager:
    """Tracks per-year download state and runs one download at a time."""

    def __init__(self, config: Settings | None = None) -> None:
        self._config = config or settings
        self._downloading: int | None = None
        self._started_at: datetime | None = None
        self._errors: dict[int, str] = {}
        self._task: asyncio.Task | None = None

    # ── status ────────────────────────────────────────────────────────────

    def status(self) -> HistoryStatus:
        config = self._config
        current = date.today().year
        years: list[YearStatus] = []

        for year in config.history_years():
            if year == self._downloading:
                years.append(
                    YearStatus(
                        year=year,
                        state="downloading",
                        is_current=year == current,
                        started_at=self._started_at,
                    )
                )
                continue

            cached = cache.read_cached(year, config)
            if cached is not None and cached.ok:
                realizing = [t for t in cached.trades if t.is_realizing]
                currencies = {t.currency for t in realizing if t.currency}
                years.append(
                    YearStatus(
                        year=year,
                        state="stored",
                        trade_count=len(cached.trades),
                        realizing_count=len(realizing),
                        realized_pnl=sum((t.realized_pnl for t in realizing), Decimal(0)),
                        currency=next(iter(currencies), "USD") if currencies else "USD",
                        downloaded_at=cached.fetched_at,
                        is_current=year == current,
                        immutable=cache.is_immutable(year, config),
                        error=cached.error,
                    )
                )
                continue

            error = self._errors.get(year, "")
            years.append(
                YearStatus(
                    year=year,
                    state="error" if error else "missing",
                    error=error,
                    is_current=year == current,
                )
            )

        return HistoryStatus(years=years, downloading=self._downloading)

    # ── downloading ───────────────────────────────────────────────────────

    def start(self, year: int) -> tuple[bool, str]:
        """Begin a download. Returns (started, message)."""
        if year not in self._config.history_years():
            return False, f"{year} is outside the range IBKR serves."
        if self._downloading is not None:
            return False, f"A download is already running ({self._downloading})."
        if not self._config.flex_configured:
            return False, "FLEX_TOKEN and FLEX_QUERY_ID are not set in .env."

        self._downloading = year
        self._started_at = datetime.now()
        self._errors.pop(year, None)
        self._task = asyncio.create_task(self._run(year), name=f"flex-download-{year}")
        return True, f"Downloading {year}…"

    async def _run(self, year: int) -> None:
        try:
            logger.info("downloading Flex statement for %s", year)
            result = await cache.get_flex(year, force_refresh=True, config=self._config)
            if result.ok:
                # An empty year is a real answer, not a failure -- the account
                # did not exist yet. It is cached like any other.
                logger.info(
                    "%s stored: %d trades (%d realizing)",
                    year,
                    len(result.trades),
                    sum(1 for t in result.trades if t.is_realizing),
                )
            else:
                self._errors[year] = result.error
                logger.warning("%s failed: %s", year, result.error)
        except Exception as exc:  # noqa: BLE001 - a failed year must not kill the worker
            self._errors[year] = str(exc) or exc.__class__.__name__
            logger.warning("%s failed: %s", year, exc, exc_info=True)
        finally:
            self._downloading = None
            self._started_at = None

    async def stop(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 - teardown
                pass
        self._task = None
        self._downloading = None


manager = HistoryManager()
