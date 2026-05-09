from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    litellm_model: str = Field(..., alias="LITELLM_MODEL")
    database_url: str = Field(..., alias="DATABASE_URL")
    cors_origins: str = Field(default="", alias="CORS_ORIGINS")
    rate_limit_per_min: int = Field(default=30, alias="RATE_LIMIT_PER_MIN")
    litellm_timeout_seconds: int = Field(default=30, alias="LITELLM_TIMEOUT_SECONDS")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    trust_forwarded_for: bool = Field(default=False, alias="TRUST_FORWARDED_FOR")

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
