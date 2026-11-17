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

    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"
    volcengine_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    volcengine_model: str = "doubao-seed-2-1-lite"
    hunyuan_base_url: str = "https://tokenhub.tencentcloudapi.com/v1"
    hunyuan_model: str = "hunyuan-hy4"

    deepseek_api_key: str | None = None
    volcengine_api_key: str | None = None
    hunyuan_api_key: str | None = None
    openai_compat_api_key: str | None = None
    openai_compat_base_url: str | None = None
    openai_compat_model: str | None = None

    gateway_qps: int = 5
    gateway_concurrency: int = 20
    gateway_connect_timeout: float = 5.0
    gateway_read_timeout_extract: float = 60.0
    gateway_read_timeout_review: float = 180.0
    gateway_retry_max: int = 3
    gateway_circuit_fail_max: int = 10
    gateway_circuit_reset_seconds: int = 30
    gateway_probe_cache_hours: int = 24
    gateway_cost_input_per_million_cny: float = 1.0
    gateway_cost_output_per_million_cny: float = 2.0
    credential_confirm_header: str = "X-Confirm-Action"


@lru_cache
def get_settings() -> Settings:
    return Settings()
