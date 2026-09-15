"""Disk cache for Flex statements, one file per calendar year.

The Flex token is limited to 1 request/second and 10/minute, and the
dashboard polls every 30s. Without a cache, a couple of open browser tabs
would exhaust the quota and start returning errors, so the API reads from
here and only goes to IBKR when an entry goes stale.

Windows are calendar-year aligned, which is what makes merging years safe --
they cannot overlap, so combining them is a plain concatenation. That matters
because these trades carry no stable unique id (no Trade ID / IB Execution ID
in the query), so deduplication would be guesswork.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from pathlib import Path

from .config import Settings, settings
from .models import FlexResult
from .sources import flex

# Serialises every outbound Flex request. Held per fetch rather than for a
# whole multi-year run, so a routine current-year refresh can interleave
# between year downloads instead of waiting the whole batch out.
_lock = asyncio.Lock()

# When did each year last fail, and how many times running?
#
# A failure is deliberately never written to disk -- an error cached as an
# empty year is indistinguishable from a year with genuinely no trades. But
# that means nothing on disk stops the next request from trying again, and
# with the dashboard polling every 30s a year that keeps failing would burn a
# SendRequest per poll.
#
# Against this particular upstream that is worse than waste. IBKR answers a
# burst with "error 1001: try again shortly", and answers persistence with
# "error 1025: too many failed attempts" -- a lockout that repeated attempts
# then keep alive. So the retries actively prevent their own recovery, and the
# backoff doubles rather than staying flat: a token that is locked out needs
# to be left alone, not polled patiently.
_failed_at: dict[int, datetime] = {}
_failures: dict[int, int] = {}
_last_error: dict[int, str] = {}

MAX_BACKOFF_SECONDS = 30 * 60

# IBKR error 1025 ("Too many failed attempts") is a token lockout, not a
# transient hiccup, and it is measured in failed *attempts* -- so every retry
# while it is active resets it. Ordinary doubling still probes far too often
# to let one expire, so a lockout jumps straight to the ceiling.
LOCKOUT_BACKOFF_SECONDS = 60 * 60
_LOCKOUT_MARKERS = ("1025", "too many failed attempts")


def _is_lockout(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in _LOCKOUT_MARKERS)


def _cooldown_seconds(year: int, config: Settings) -> float:
    """Doubling backoff from the configured base, capped -- unless IBKR has
    locked the token out, which needs to be waited out, not probed."""
    if _is_lockout(_last_error.get(year, "")):
        return LOCKOUT_BACKOFF_SECONDS
    strikes = _failures.get(year, 1)
    return min(
        config.flex_failure_cooldown_seconds * (2 ** (strikes - 1)),
        MAX_BACKOFF_SECONDS,
    )


def year_window(year: int, today: date | None = None) -> tuple[date, date]:
    """The fd/td window for a calendar year.

    Dec 31 - Jan 1 is 364 days, so a full year always sits inside Flex's
    365-day ceiling.

    The current year is clamped to today: IBKR rejects a window whose end date
    is in the future with "error 1001: Statement could not be generated at
    this time", which reads like throttling and is not.
    """
    today = today or date.today()
    start = date(year, 1, 1)
    end = date(year, 12, 31)
    return start, min(end, today)


def _cache_path(config: Settings, year: int) -> Path:
    return config.cache_dir / f"flex_{config.flex_query_id or 'unset'}_{year}.json"


def read_cached(year: int, config: Settings | None = None) -> FlexResult | None:
    config = config or settings
    path = _cache_path(config, year)
    if not path.exists():
        return None
    try:
        return FlexResult.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_cache(result: FlexResult, year: int, config: Settings) -> None:
    path = _cache_path(config, year)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Written 0600: a statement carries the account number and full trade history.
    path.write_text(result.model_dump_json(), encoding="utf-8")
    path.chmod(0o600)


def is_immutable(year: int, config: Settings | None = None, today: date | None = None) -> bool:
    """True once a year is closed and settled, and so can never change again.

    The buffer is the point: Flex lags settlement by a day or two, so a year
    fetched on 2 January is missing its final trades. Freezing it then would
    lose them permanently.
    """
    config = config or settings
    today = today or date.today()
    if year >= today.year:
        return False
    closed_on = date(year + 1, 1, 1)
    return (today - closed_on).days >= config.year_immutable_after_days


def _is_fresh(
    result: FlexResult, year: int, config: Settings, today: date | None = None
) -> bool:
    if result.fetched_at is None:
        return False
    # A closed year is downloaded once and never re-fetched.
    if is_immutable(year, config, today):
        return True
    age = datetime.now() - result.fetched_at
    return age < timedelta(seconds=config.flex_cache_ttl_seconds)


async def get_flex(
    year: int,
    *,
    force_refresh: bool = False,
    config: Settings | None = None,
) -> FlexResult:
    """Return one year's statement, fetching only when stale or forced."""
    config = config or settings

    cached = read_cached(year, config)
    if cached is not None and cached.ok and _is_fresh(cached, year, config) and not force_refresh:
        return cached

    if not config.flex_configured:
        return FlexResult(ok=False, error="FLEX_TOKEN and FLEX_QUERY_ID are not set in .env")

    # An explicit download (force_refresh) normally tries regardless, so
    # pressing Download is never silently ignored. The exception is a lockout:
    # IBKR counts failed *attempts*, so trying during one is not merely futile,
    # it extends the very thing being waited out.
    failed_at = _failed_at.get(year)
    if force_refresh and failed_at is not None and _is_lockout(_last_error.get(year, "")):
        since = (datetime.now() - failed_at).total_seconds()
        wait = int(LOCKOUT_BACKOFF_SECONDS - since)
        if wait > 0:
            return FlexResult(
                ok=False,
                error=(
                    f"{_last_error[year]} — IBKR counts failed attempts, so "
                    f"trying again now would extend the lockout. Leave it "
                    f"{wait // 60}m."
                ),
            )

    if not force_refresh:
        failed_at = _failed_at.get(year)
        if failed_at is not None:
            since = (datetime.now() - failed_at).total_seconds()
            cooldown = _cooldown_seconds(year, config)
            if since < cooldown:
                stale = read_cached(year, config)
                # Carry the real reason, not just the countdown. "could not be
                # fetched, retrying in 156s" gives nobody anything to act on;
                # "too many failed attempts" says to stop retrying and wait.
                # No year prefix: get_period() adds one when merging, and
                # callers fetching a single year already know which it is.
                reason = _last_error.get(year, "could not be fetched")
                wait = int(cooldown - since)
                message = (
                    f"{reason} — not retrying for {wait // 60}m {wait % 60}s"
                    if wait >= 60
                    else f"{reason} — not retrying for {wait}s"
                )
                if stale is not None and stale.ok:
                    return stale.model_copy(update={"error": message})
                return FlexResult(ok=False, error=message)

    async with _lock:
        # Another request may have refreshed while we waited for the lock.
        if not force_refresh:
            cached = read_cached(year, config)
            if cached is not None and cached.ok and _is_fresh(cached, year, config):
                return cached

        result = await flex.fetch(config, window=year_window(year))

    # Only a successful fetch is cached. A failed year must stay retryable --
    # freezing an error as an empty year is the difference between "no trades
    # in 2022" and "the fetch broke", and they must not look alike.
    if result.ok:
        _failed_at.pop(year, None)
        _failures.pop(year, None)
        _last_error.pop(year, None)
        _write_cache(result, year, config)
        return result

    _failed_at[year] = datetime.now()
    _failures[year] = _failures.get(year, 0) + 1
    _last_error[year] = result.error

    # Refresh failed. Prefer stale-but-real data over showing nothing, while
    # still surfacing the error so an expired token does not read as a
    # genuine zero.
    stale = read_cached(year, config)
    if stale is not None and stale.ok:
        return stale.model_copy(update={"error": result.error})
    return result


def cached_years(config: Settings | None = None) -> list[int]:
    """Years already on disk, newest first."""
    config = config or settings
    return sorted(
        (
            year
            for year in config.history_years()
            if (cached := read_cached(year, config)) is not None and cached.ok
        ),
        reverse=True,
    )


async def get_period(
    period: str,
    *,
    config: Settings | None = None,
) -> tuple[FlexResult, list[int]]:
    """Resolve a period selector to trades, plus the years actually covered.

    `period` is "all" or a four-digit year. "all" merges only the years
    already downloaded -- it never triggers a multi-year fetch, because that
    would be minutes of rate-limited work behind an innocent page load. The
    returned year list is what lets the UI say which years it is showing
    rather than presenting a partial total as a complete one.
    """
    config = config or settings
    current = date.today().year

    if period != "all":
        try:
            year = int(period)
        except ValueError:
            return FlexResult(ok=False, error=f"Unknown period {period!r}"), []
        return await get_flex(year, config=config), [year]

    years = cached_years(config)
    # The current year is always live, even before its first explicit download.
    if current not in years:
        years = [current] + years

    merged: list = []
    errors: list[str] = []
    account_id = ""
    fetched_at: datetime | None = None
    covered: list[int] = []

    for year in sorted(years, reverse=True):
        # Closed years come straight off disk; only the current year can go
        # out to IBKR here, so "all" stays cheap.
        result = (
            await get_flex(year, config=config)
            if year == current
            else read_cached(year, config)
        )
        if result is None or not result.ok:
            if result is not None and result.error:
                errors.append(f"{year}: {result.error}")
            continue
        merged.extend(result.trades)
        covered.append(year)
        account_id = account_id or result.account_id
        if result.fetched_at and (fetched_at is None or result.fetched_at > fetched_at):
            fetched_at = result.fetched_at

    merged.sort(key=lambda t: (t.trade_date, t.trade_time))
    return (
        FlexResult(
            ok=True,
            trades=merged,
            fetched_at=fetched_at,
            account_id=account_id,
            error="; ".join(errors),
        ),
        sorted(covered, reverse=True),
    )
