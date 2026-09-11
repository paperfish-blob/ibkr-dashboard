"""Settings, loaded from .env."""

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


settings = Settings()
