from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    environment: str = "dev"
    database_url: str = "postgresql+asyncpg://cairn:cairn@127.0.0.1:5433/cairn"
    redis_url: str = "redis://localhost:6379/0"
    cairn_secret_key: str = "dev-insecure-change-me"
    jwt_secret: str = "dev-jwt-insecure-change-me"
    jwt_refresh_ttl_days: int = 7
    jwt_access_ttl_minutes: int = 120
    cors_origins: list[str] = ["http://127.0.0.1:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
