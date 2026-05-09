class GenerationError(Exception):
    """Base class for errors surfaced by the generation pipeline.

    Subclasses carry their own HTTP status, frontend code, user-facing message,
    severity, and retryable flag. core/error_handlers.py reads these to build
    the response envelope (app.schemas.response.ErrorResponse).
    """

    code: str = "INTERNAL_ERROR"
    http_status: int = 500
    user_message: str = "Internal server error."
    severity: str = "error"
    retryable: bool = False


class BadShapeError(GenerationError):
    code = "BAD_SHAPE"
    http_status = 502
    user_message = "The model returned an unexpected response."
    severity = "error"
    retryable = True


class UpstreamError(GenerationError):
    code = "UPSTREAM_ERROR"
    http_status = 502
    user_message = "The generator service is temporarily unavailable."
    severity = "error"
    retryable = True


class RateLimitedError(GenerationError):
    code = "RATE_LIMITED"
    http_status = 429
    user_message = "Too many requests. Please slow down."
    severity = "warning"
    retryable = True


class DatabaseUnavailableError(GenerationError):
    code = "DB_UNAVAILABLE"
    http_status = 503
    user_message = "Service is temporarily unavailable."
    severity = "error"
    retryable = True


class ConfigError(GenerationError):
    code = "CONFIG_ERROR"
    http_status = 500
    user_message = "Service is misconfigured."
    severity = "error"
    retryable = False
