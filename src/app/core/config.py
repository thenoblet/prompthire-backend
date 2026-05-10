from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or a ``.env`` file.

    All fields are aliased to their uppercase environment variable names so the
    application can be configured without code changes across environments. The
    singleton is retrieved via ``get_settings()`` which caches the instance with
    ``lru_cache`` to avoid repeated disk reads.

    Attributes:
        litellm_model: The primary litellm model identifier
            (e.g. ``"gemini/gemini-2.5-flash"``). Tried first on every request.
        litellm_fallback_models: Optional comma-separated list of fallback
            model identifiers tried in order if the primary exhausts retries.
            Each fallback gets its own tenacity retry budget. Empty disables
            fallback (primary-only).
        database_url: SQLAlchemy async-compatible connection string
            (e.g. ``"postgresql+asyncpg://..."``).
        cors_origins: Comma-separated list of allowed CORS origins. Defaults
            to the production frontend domain plus the Vite dev server so a
            fresh deploy and a fresh dev environment both work without the
            operator setting the env var. An empty string disables CORS.
            Parsed into a list via ``cors_origins_list``.
        rate_limit_per_min: Maximum requests a single IP may make per minute
            on the generate route.
        rate_limit_per_day: Maximum requests a single IP may make per day
            on the generate route.
        global_daily_cap: Maximum total LLM calls accepted globally per day
            before ``ServiceAtCapacityError`` is raised. Cache hits do not
            count against this cap.
        cache_enabled: Whether the Postgres question cache is active. When
            ``False``, every request hits the LLM directly.
        cache_ttl_hours: How long a cache entry is considered fresh before
            it is pruned on next lookup.
        litellm_timeout_seconds: Per-call timeout forwarded to litellm. Bounds
            a single LLM API call.
        request_budget_seconds: Wallclock budget for the entire LLM chain
            (primary + fallbacks + retries). When exceeded the service raises
            ``RequestTimeoutError`` and returns 504. Set this larger than
            ``litellm_timeout_seconds`` but small enough to bound user wait.
        log_level: Python logging level string (e.g. ``"INFO"``).
        trust_forwarded_for: When ``True``, the ``X-Forwarded-For`` header is
            used to determine the client IP for rate limiting. Enable only
            behind a trusted reverse proxy.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    litellm_model: str = Field(..., alias="LITELLM_MODEL")
    litellm_fallback_models: str = Field(default="", alias="LITELLM_FALLBACK_MODELS")
    database_url: str = Field(..., alias="DATABASE_URL")
    cors_origins: str = Field(
        default="https://prompthire.noblet.tech,http://localhost:5173",
        alias="CORS_ORIGINS",
    )
    rate_limit_per_min: int = Field(default=5, alias="RATE_LIMIT_PER_MIN")
    rate_limit_per_day: int = Field(default=20, alias="RATE_LIMIT_PER_DAY")
    global_daily_cap: int = Field(default=200, alias="GLOBAL_DAILY_CAP")
    cache_enabled: bool = Field(default=True, alias="CACHE_ENABLED")
    cache_ttl_hours: int = Field(default=24, alias="CACHE_TTL_HOURS")
    litellm_timeout_seconds: int = Field(default=30, alias="LITELLM_TIMEOUT_SECONDS")
    request_budget_seconds: int = Field(default=45, alias="REQUEST_BUDGET_SECONDS")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    trust_forwarded_for: bool = Field(default=False, alias="TRUST_FORWARDED_FOR")

    @property
    def cors_origins_list(self) -> list[str]:
        """Return ``cors_origins`` split and stripped into a list of origin strings."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def litellm_fallback_models_list(self) -> list[str]:
        """Return ``litellm_fallback_models`` parsed into a list of model identifiers."""
        return [m.strip() for m in self.litellm_fallback_models.split(",") if m.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
