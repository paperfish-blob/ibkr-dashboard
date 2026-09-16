"""Settings, loaded from .env."""

from datetime import date
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Flex Web Service (historical realized P&L) ---
    flex_token: str = ""
    flex_query_id: str = ""

    # Flex statements are generated on demand and the token is rate limited to
    # 1 request/second and 10/minute, so we serve from a disk cache and only
    # refresh when it goes stale.
    flex_cache_ttl_seconds: int = 900
    cache_dir: Path = PROJECT_ROOT / ".cache"

    # Calendar years of history offered on the History page, in addition to the
    # current one. IBKR is documented to keep the four previous calendar years
    # plus the current, so a year past that is expected to come back empty or
    # with an error like the one 2022 already gets (Flex error 1003) -- that's
    # IBKR's own retention limit, not a bug here. Override via .env
    # (FLEX_HISTORY_YEARS) if a given account turns out to keep more.
    flex_history_years: int = 5

    # A year that has only just closed is not safe to treat as immutable: Flex
    # lags settlement by a day or two, so its final trades may not have landed
    # yet. Freezing it then would lose them permanently.
    year_immutable_after_days: int = 7

    # How long to leave a failed year alone before trying it again. Failures
    # are never cached to disk, so without this the 30s dashboard poll would
    # retry a broken year forever -- and against a 10/minute token, those
    # retries are what keep IBKR throttling. Explicit downloads ignore it.
    flex_failure_cooldown_seconds: int = 90

    # --- IB Gateway (today's live realized P&L) ---
    ib_host: str = "127.0.0.1"
    ib_port: int = 4001  # 4001 live, 4002 paper
    ib_client_id: int = 17
    # Leave blank to use the first account IB Gateway reports.
    ib_account: str = ""
    # How often the background task retries while Gateway is down.
    ib_reconnect_seconds: int = 30

    @property
    def flex_configured(self) -> bool:
        return bool(self.flex_token and self.flex_query_id)

    def history_years(self, today: date | None = None) -> list[int]:
        """Reachable calendar years, newest first. Derived from the current
        year rather than hardcoded, so this keeps working next January."""
        current = (today or date.today()).year
        return [current - offset for offset in range(self.flex_history_years + 1)]


settings = Settings()
