"""Multi-year history: which years are reachable, when a year may be frozen,
and what happens to "today" when the selected period is a past year."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from ibkr_pnl.aggregate import combine
from ibkr_pnl.cache import is_immutable, year_window
from ibkr_pnl.config import Settings
from ibkr_pnl.models import FlexResult, GatewayState, RealizedTrade


def trade(day: date, amount: str, symbol: str = "AAPL") -> RealizedTrade:
    return RealizedTrade(symbol=symbol, trade_date=day, realized_pnl=Decimal(amount))


class TestYearWindow:
    def test_closed_year_is_the_whole_calendar_year(self):
        assert year_window(2025, today=date(2026, 9, 15)) == (
            date(2025, 1, 1),
            date(2025, 12, 31),
        )

    def test_current_year_is_clamped_to_today(self):
        """IBKR rejects a window ending in the future with "error 1001:
        Statement could not be generated at this time" -- which reads exactly
        like throttling and is not. Asking for Dec 31 in September fails."""
        assert year_window(2026, today=date(2026, 9, 15)) == (
            date(2026, 1, 1),
            date(2026, 9, 15),
        )

    def test_window_stays_inside_flex_365_day_ceiling(self):
        """Flex rejects a range longer than 365 days. Jan 1 to Dec 31 is 364,
        so a calendar year always fits -- including a leap year."""
        for year in (2024, 2025, 2026):
            start, end = year_window(year, today=date(2027, 6, 1))
            assert (end - start).days <= 365


class TestHistoryYears:
    def test_offers_current_year_plus_the_configured_depth(self):
        config = Settings(flex_history_years=4)
        assert config.history_years(today=date(2026, 9, 15)) == [2026, 2025, 2024, 2023, 2022]

    def test_range_is_derived_not_hardcoded(self):
        """It has to roll over on its own at New Year."""
        config = Settings(flex_history_years=2)
        assert config.history_years(today=date(2027, 1, 1)) == [2027, 2026, 2025]


class TestImmutability:
    config = Settings(year_immutable_after_days=7)

    def test_current_year_is_never_immutable(self):
        assert is_immutable(2026, self.config, today=date(2026, 9, 15)) is False

    def test_long_closed_year_is_immutable(self):
        assert is_immutable(2024, self.config, today=date(2026, 9, 15)) is True

    def test_a_just_closed_year_is_not_frozen_yet(self):
        """The trap this buffer exists for: Flex lags settlement by a day or
        two, so a year fetched on 2 January is missing its final trades.
        Freezing it then would lose them permanently."""
        assert is_immutable(2026, self.config, today=date(2027, 1, 2)) is False

    def test_year_becomes_immutable_once_the_buffer_passes(self):
        assert is_immutable(2026, self.config, today=date(2027, 1, 8)) is True


class TestPastYearHasNoToday:
    """Gateway reports P&L realized *now*, which belongs to the current year.
    Adding it to a 2024 total would be contamination."""

    def test_connected_gateway_is_ignored_for_a_past_year(self):
        result = combine(
            FlexResult(ok=True, trades=[trade(date(2024, 6, 3), "500")]),
            GatewayState(connected=True, realized_pnl=Decimal("999")),
            today=date(2026, 9, 15),
            covers_today=False,
        )

        assert result.headline == Decimal("500")
        assert result.today == Decimal("0")
        assert result.today_source == "none"

    def test_series_is_not_stretched_to_today(self):
        """A 2024 view must not gain a point dated now, which would drag its
        chart across two empty years."""
        result = combine(
            FlexResult(ok=True, trades=[trade(date(2024, 6, 3), "500")]),
            GatewayState(connected=True, realized_pnl=Decimal("999")),
            today=date(2026, 9, 15),
            covers_today=False,
        )

        assert [p.date for p in result.series] == [date(2024, 6, 3)]

    def test_current_period_still_merges_gateway(self):
        """The default path is unchanged -- covers_today only gates past years."""
        result = combine(
            FlexResult(ok=True, trades=[trade(date(2026, 9, 14), "500")]),
            GatewayState(connected=True, realized_pnl=Decimal("120")),
            today=date(2026, 9, 15),
            covers_today=True,
        )

        assert result.today == Decimal("120")
        assert result.today_source == "gateway"
        assert result.headline == Decimal("620")


class TestFailureCooldown:
    """A failed year is never written to disk, so nothing on disk stops the
    next request retrying it. With a 30s dashboard poll that means a
    SendRequest per poll against a 10/minute token -- and those retries are
    exactly what keeps IBKR throttling, so they prevent their own recovery."""

    def _config(self, tmp_path):
        return Settings(
            flex_token="t",
            flex_query_id="q",
            cache_dir=tmp_path,
            flex_failure_cooldown_seconds=90,
        )

    def test_a_failed_year_is_not_retried_immediately(self, tmp_path, monkeypatch):
        import asyncio

        from ibkr_pnl import cache as cache_mod

        calls = 0

        async def failing_fetch(config, window=None):
            nonlocal calls
            calls += 1
            return FlexResult(ok=False, error="Flex error 1001: try again shortly")

        monkeypatch.setattr(cache_mod.flex, "fetch", failing_fetch)
        cache_mod._failed_at.clear()
        cache_mod._failures.clear()
        cache_mod._last_error.clear()
        config = self._config(tmp_path)

        first = asyncio.run(cache_mod.get_flex(2024, config=config))
        second = asyncio.run(cache_mod.get_flex(2024, config=config))

        assert first.ok is False
        assert calls == 1, "the second call must be served by the cooldown"
        assert "not retrying" in second.error

    def test_an_explicit_download_ignores_the_cooldown(self, tmp_path, monkeypatch):
        """Pressing Download must never be silently swallowed."""
        import asyncio

        from ibkr_pnl import cache as cache_mod

        calls = 0

        async def failing_fetch(config, window=None):
            nonlocal calls
            calls += 1
            return FlexResult(ok=False, error="nope")

        monkeypatch.setattr(cache_mod.flex, "fetch", failing_fetch)
        cache_mod._failed_at.clear()
        config = self._config(tmp_path)

        asyncio.run(cache_mod.get_flex(2024, config=config))
        asyncio.run(cache_mod.get_flex(2024, force_refresh=True, config=config))

        assert calls == 2

    def test_backoff_doubles_with_consecutive_failures(self, tmp_path, monkeypatch):
        """IBKR answers a burst with "try again shortly" (1001) and answers
        persistence with a lockout (1025) that further attempts keep alive.
        A flat cooldown would poll patiently straight through that, so the
        wait has to grow."""
        import asyncio

        from ibkr_pnl import cache as cache_mod

        # A transient failure, deliberately not a lockout -- 1025 escalates
        # straight to the ceiling and would not exercise the doubling.
        async def failing_fetch(config, window=None):
            return FlexResult(ok=False, error="Flex error 1001: try again shortly")

        monkeypatch.setattr(cache_mod.flex, "fetch", failing_fetch)
        cache_mod._failed_at.clear()
        cache_mod._failures.clear()
        cache_mod._last_error.clear()
        config = self._config(tmp_path)

        waits = []
        for _ in range(4):
            # force_refresh bypasses the cooldown so each call actually fails
            # again, which is what advances the strike count.
            asyncio.run(cache_mod.get_flex(2024, force_refresh=True, config=config))
            waits.append(cache_mod._cooldown_seconds(2024, config))

        assert waits == [90, 180, 360, 720]

    def test_a_lockout_backs_off_far_harder_than_a_normal_failure(
        self, tmp_path, monkeypatch
    ):
        """IBKR error 1025 counts failed *attempts*, so every retry resets it.
        Ordinary doubling still probes far too often to let one expire."""
        import asyncio

        from ibkr_pnl import cache as cache_mod

        async def locked_out(config, window=None):
            return FlexResult(
                ok=False, error="Flex error 1025: Too many failed attempts."
            )

        monkeypatch.setattr(cache_mod.flex, "fetch", locked_out)
        cache_mod._failed_at.clear()
        cache_mod._failures.clear()
        cache_mod._last_error.clear()
        config = self._config(tmp_path)

        asyncio.run(cache_mod.get_flex(2024, force_refresh=True, config=config))

        assert cache_mod._cooldown_seconds(2024, config) == cache_mod.LOCKOUT_BACKOFF_SECONDS

    def test_download_is_refused_during_a_lockout(self, tmp_path, monkeypatch):
        """The one case where "try anyway" is worse than doing nothing."""
        import asyncio

        from ibkr_pnl import cache as cache_mod

        calls = 0

        async def locked_out(config, window=None):
            nonlocal calls
            calls += 1
            return FlexResult(
                ok=False, error="Flex error 1025: Too many failed attempts."
            )

        monkeypatch.setattr(cache_mod.flex, "fetch", locked_out)
        cache_mod._failed_at.clear()
        cache_mod._failures.clear()
        cache_mod._last_error.clear()
        config = self._config(tmp_path)

        asyncio.run(cache_mod.get_flex(2024, force_refresh=True, config=config))
        second = asyncio.run(cache_mod.get_flex(2024, force_refresh=True, config=config))

        assert calls == 1, "an explicit retry must not extend the lockout"
        assert "would extend the lockout" in second.error

    def test_the_real_reason_survives_into_the_backoff_message(
        self, tmp_path, monkeypatch
    ):
        """"could not be fetched, retrying in 156s" gives nobody anything to
        act on; the IBKR message is what says to stop retrying and wait."""
        import asyncio

        from ibkr_pnl import cache as cache_mod

        async def failing(config, window=None):
            return FlexResult(ok=False, error="Flex error 1003: Statement is not available.")

        monkeypatch.setattr(cache_mod.flex, "fetch", failing)
        cache_mod._failed_at.clear()
        cache_mod._failures.clear()
        cache_mod._last_error.clear()
        config = self._config(tmp_path)

        asyncio.run(cache_mod.get_flex(2024, config=config))
        second = asyncio.run(cache_mod.get_flex(2024, config=config))

        assert "1003" in second.error
        assert "not retrying" in second.error

    def test_backoff_is_capped(self, tmp_path, monkeypatch):
        from ibkr_pnl import cache as cache_mod

        config = self._config(tmp_path)
        cache_mod._failures.clear()
        # A stale lockout message would escalate past the cap and mask this.
        cache_mod._last_error.clear()
        cache_mod._failures[2024] = 99
        try:
            assert cache_mod._cooldown_seconds(2024, config) == cache_mod.MAX_BACKOFF_SECONDS
        finally:
            cache_mod._failures.clear()

    def test_success_clears_the_cooldown(self, tmp_path, monkeypatch):
        import asyncio

        from ibkr_pnl import cache as cache_mod

        cache_mod._failed_at.clear()
        config = self._config(tmp_path)

        async def failing_fetch(config, window=None):
            return FlexResult(ok=False, error="nope")

        monkeypatch.setattr(cache_mod.flex, "fetch", failing_fetch)
        asyncio.run(cache_mod.get_flex(2024, config=config))
        assert 2024 in cache_mod._failed_at

        async def ok_fetch(config, window=None):
            return FlexResult(ok=True, trades=[], fetched_at=datetime.now())

        monkeypatch.setattr(cache_mod.flex, "fetch", ok_fetch)
        asyncio.run(cache_mod.get_flex(2024, force_refresh=True, config=config))
        assert 2024 not in cache_mod._failed_at


class TestBackoffSurvivesRestart:
    """A lockout outlasts the process that earned it. Holding it in memory
    alone means a restart forgets it and retries -- and against 1025 that
    retry is itself a failed attempt, resetting IBKR's clock. A server
    restarted a few times can then hold its own token locked out for hours."""

    def _config(self, tmp_path, token="t"):
        return Settings(
            flex_token=token,
            flex_query_id="q",
            cache_dir=tmp_path,
            flex_failure_cooldown_seconds=90,
        )

    def _restart(self, cache_mod):
        """Simulate a fresh process: memory empty, disk untouched."""
        cache_mod._failed_at.clear()
        cache_mod._failures.clear()
        cache_mod._last_error.clear()
        cache_mod._backoff_loaded = False

    def _fail_once(self, cache_mod, config, monkeypatch, error):
        import asyncio

        async def failing(config, window=None):
            return FlexResult(ok=False, error=error)

        monkeypatch.setattr(cache_mod.flex, "fetch", failing)
        asyncio.run(cache_mod.get_flex(2024, force_refresh=True, config=config))

    def test_a_lockout_is_still_in_force_after_a_restart(self, tmp_path, monkeypatch):
        import asyncio

        from ibkr_pnl import cache as cache_mod

        config = self._config(tmp_path)
        self._restart(cache_mod)
        self._fail_once(
            cache_mod, config, monkeypatch, "Flex error 1025: Too many failed attempts."
        )

        self._restart(cache_mod)

        calls = 0

        async def counting(config, window=None):
            nonlocal calls
            calls += 1
            return FlexResult(ok=False, error="should not have been reached")

        monkeypatch.setattr(cache_mod.flex, "fetch", counting)
        result = asyncio.run(cache_mod.get_flex(2024, config=config))

        assert calls == 0, "restart retried into an active lockout"
        assert "1025" in result.error
        assert cache_mod._cooldown_seconds(2024, config) == cache_mod.LOCKOUT_BACKOFF_SECONDS

    def test_a_success_clears_the_stored_backoff(self, tmp_path, monkeypatch):
        import asyncio

        from ibkr_pnl import cache as cache_mod

        config = self._config(tmp_path)
        self._restart(cache_mod)
        # An ordinary failure, not a lockout: a lockout deliberately refuses
        # the very force_refresh this test needs to recover with.
        self._fail_once(cache_mod, config, monkeypatch, "temporarily unavailable")

        async def ok_fetch(config, window=None):
            return FlexResult(ok=True, trades=[], fetched_at=datetime.now())

        monkeypatch.setattr(cache_mod.flex, "fetch", ok_fetch)
        asyncio.run(cache_mod.get_flex(2024, force_refresh=True, config=config))

        self._restart(cache_mod)
        asyncio.run(cache_mod.get_flex(2024, config=config))

        assert 2024 not in cache_mod._failed_at

    def test_rotating_the_token_does_not_bypass_the_lockout(self, tmp_path, monkeypatch):
        """1025 tracks the query/account, not the bearer token: a token
        rotated during a live lockout fails again within minutes, with
        nothing else calling out to explain it. Treating a new token as a
        clean slate bought every rotation one free real attempt against a
        still-locked-out query -- which failed, extending the very lockout
        that prompted the rotation in the first place."""
        import asyncio

        from ibkr_pnl import cache as cache_mod

        self._restart(cache_mod)
        self._fail_once(
            cache_mod,
            self._config(tmp_path, token="old"),
            monkeypatch,
            "Flex error 1025: Too many failed attempts.",
        )

        self._restart(cache_mod)

        calls = 0

        async def counting(config, window=None):
            nonlocal calls
            calls += 1
            return FlexResult(ok=True, trades=[], fetched_at=datetime.now())

        monkeypatch.setattr(cache_mod.flex, "fetch", counting)
        result = asyncio.run(cache_mod.get_flex(2024, config=self._config(tmp_path, token="new")))

        assert calls == 0, "a rotated token bought a free attempt against an active lockout"
        assert "1025" in result.error

    def test_a_lockout_blocks_every_year_not_just_the_one_that_tripped_it(
        self, tmp_path, monkeypatch
    ):
        """1025 attaches to the token. Tracked per year, the History page would
        walk into it one year at a time, each attempt resetting the clock."""
        import asyncio

        from ibkr_pnl import cache as cache_mod

        config = self._config(tmp_path)
        self._restart(cache_mod)
        self._fail_once(
            cache_mod, config, monkeypatch, "Flex error 1025: Too many failed attempts."
        )

        calls = 0

        async def counting(config, window=None):
            nonlocal calls
            calls += 1
            return FlexResult(ok=True, trades=[], fetched_at=datetime.now())

        monkeypatch.setattr(cache_mod.flex, "fetch", counting)
        # A different year, and an explicit download -- the strongest case for
        # going out to IBKR, and still the wrong thing to do during a lockout.
        result = asyncio.run(
            cache_mod.get_flex(2022, force_refresh=True, config=config)
        )

        assert calls == 0, "a download of another year walked into the lockout"
        assert "1025" in result.error

    def test_corrupt_state_does_not_break_the_fetch(self, tmp_path, monkeypatch):
        import asyncio

        from ibkr_pnl import cache as cache_mod

        config = self._config(tmp_path)
        cache_mod._backoff_path(config).write_text("{not json", encoding="utf-8")
        self._restart(cache_mod)

        async def ok_fetch(config, window=None):
            return FlexResult(ok=True, trades=[], fetched_at=datetime.now())

        monkeypatch.setattr(cache_mod.flex, "fetch", ok_fetch)
        result = asyncio.run(cache_mod.get_flex(2024, config=config))

        assert result.ok


class TestCurrentYearUsesTheSavedTemplate:
    """The saved Flex Query is itself a Year to Date template. Overriding it
    with fd/td for the current year would only reproduce, with more ways to
    fail, what asking for nothing already gets for free. A closed year has no
    such template to lean on -- there the override is load-bearing."""

    def _config(self, tmp_path):
        return Settings(flex_token="t", flex_query_id="q", cache_dir=tmp_path)

    def test_the_current_year_is_requested_with_no_window(self, tmp_path, monkeypatch):
        import asyncio

        from ibkr_pnl import cache as cache_mod

        cache_mod._failed_at.clear()
        cache_mod._failures.clear()
        cache_mod._last_error.clear()
        cache_mod._backoff_loaded = False
        config = self._config(tmp_path)

        seen_window = "not called"

        async def capturing(config, window=None):
            nonlocal seen_window
            seen_window = window
            return FlexResult(ok=True, trades=[], fetched_at=datetime.now())

        monkeypatch.setattr(cache_mod.flex, "fetch", capturing)
        current_year = date.today().year
        asyncio.run(cache_mod.get_flex(current_year, config=config))

        assert seen_window is None

    def test_a_past_year_still_gets_an_explicit_window(self, tmp_path, monkeypatch):
        import asyncio

        from ibkr_pnl import cache as cache_mod

        cache_mod._failed_at.clear()
        cache_mod._failures.clear()
        cache_mod._last_error.clear()
        cache_mod._backoff_loaded = False
        config = self._config(tmp_path)

        seen_window = "not called"

        async def capturing(config, window=None):
            nonlocal seen_window
            seen_window = window
            return FlexResult(ok=True, trades=[], fetched_at=datetime.now())

        monkeypatch.setattr(cache_mod.flex, "fetch", capturing)
        past_year = date.today().year - 1
        asyncio.run(cache_mod.get_flex(past_year, config=config))

        assert seen_window == (date(past_year, 1, 1), date(past_year, 12, 31))


class TestWindowValidation:
    def test_rejects_a_window_longer_than_flex_allows(self):
        """Caught locally rather than spending a request to be told no.

        Driven with asyncio.run rather than pytest-asyncio: one coroutine
        does not justify a new test dependency.
        """
        import asyncio

        from ibkr_pnl.sources.flex import FlexError, fetch_statement_xml

        config = Settings(flex_token="t", flex_query_id="q")
        with pytest.raises(FlexError, match="365 days"):
            asyncio.run(
                fetch_statement_xml(config, window=(date(2024, 1, 1), date(2025, 6, 1)))
            )
