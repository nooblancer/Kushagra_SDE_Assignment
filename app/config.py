from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Portal Credentials & Upstream
    PORTAL_BASE_URL: str = "https://urja-ops.flockenergy.tech"
    PORTAL_USERNAME: str = "operator@urja.local"
    PORTAL_PASSWORD: str = "urja-ops-2026"

    # API Configuration
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False
    REQUEST_TIMEOUT_SECONDS: float = 15.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()

