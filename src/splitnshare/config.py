from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from splitnshare.domain.enums import Language


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    bot_token: str = Field(min_length=10)
    database_url: str = "postgresql+asyncpg://splitnshare:splitnshare@localhost:5432/splitnshare"
    default_currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    default_language: Language = Language.ENGLISH
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
