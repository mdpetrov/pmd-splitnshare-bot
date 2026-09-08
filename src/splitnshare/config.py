"""Load runtime configuration from environment variables."""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from splitnshare.domain.currencies import normalize_currency
from splitnshare.domain.enums import Language


class Settings(BaseSettings):
    """Validated settings required to connect the bot and database."""
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    bot_token: str = Field(min_length=10)
    database_url: str = "postgresql+asyncpg://splitnshare:splitnshare@localhost:5432/splitnshare"
    default_currency: str = "USD"
    default_language: Language = Language.ENGLISH
    log_level: str = "INFO"

    @field_validator("default_currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        """Normalize and validate the configured default against supported currencies."""
        return normalize_currency(value)


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide cached application settings."""
    return Settings()  # type: ignore[call-arg]
