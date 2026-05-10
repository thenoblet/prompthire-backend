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
    """Raised when the LLM response cannot be coerced into the expected schema.

    Surfaced to the client as HTTP 502 with code ``BAD_SHAPE``. Marked
    retryable because the model occasionally produces malformed output and
    a fresh attempt often succeeds.
    """

    code = "BAD_SHAPE"
    http_status = 502
    user_message = "The model returned an unexpected response."
    severity = "error"
    retryable = True


class UpstreamError(GenerationError):
    """Raised when the LLM provider is unreachable or fails after retries.

    Surfaced as HTTP 502 with code ``UPSTREAM_ERROR``. Covers rate-limit
    responses from the provider, connection timeouts, and any other transient
    provider-side failure that survives tenacity's backoff.
    """

    code = "UPSTREAM_ERROR"
    http_status = 502
    user_message = "The generator service is temporarily unavailable."
    severity = "error"
    retryable = True


class RateLimitedError(GenerationError):
    """Raised when a per-IP rate limit (per-minute or per-day) is exceeded.

    Surfaced as HTTP 429 with code ``RATE_LIMITED``. Marked retryable so the
    frontend can instruct the user to wait and try again.
    """

    code = "RATE_LIMITED"
    http_status = 429
    user_message = "Too many requests. Please slow down."
    severity = "warning"
    retryable = True


class DatabaseUnavailableError(GenerationError):
    """Raised when a critical database call fails and the request cannot proceed.

    Surfaced as HTTP 503 with code ``DB_UNAVAILABLE``. Non-critical database
    calls (audit writes, cache inserts) swallow their own exceptions and do
    not raise this error.
    """

    code = "DB_UNAVAILABLE"
    http_status = 503
    user_message = "Service is temporarily unavailable."
    severity = "error"
    retryable = True


class ConfigError(GenerationError):
    """Raised when required application configuration is missing or invalid.

    Surfaced as HTTP 500 with code ``CONFIG_ERROR``. Not retryable because
    the condition can only be resolved by fixing the deployment configuration.
    """

    code = "CONFIG_ERROR"
    http_status = 500
    user_message = "Service is misconfigured."
    severity = "error"
    retryable = False


class ServiceAtCapacityError(GenerationError):
    """Raised when the global daily LLM call cap has been reached.

    Surfaced as HTTP 503 with code ``SERVICE_AT_CAPACITY``. Not retryable
    within the same calendar day; the cap resets at midnight UTC.
    """

    code = "SERVICE_AT_CAPACITY"
    http_status = 503
    user_message = "Service has reached today's capacity. Please try again tomorrow."
    severity = "warning"
    retryable = False


class RequestTimeoutError(GenerationError):
    """Raised when a request exceeds the wallclock budget for the LLM chain.

    Distinct from ``UpstreamError`` because the cause is local — the service
    decided to give up after ``REQUEST_BUDGET_SECONDS`` rather than continue
    retrying or rolling over to further fallbacks. Surfaced as HTTP 504
    with code ``REQUEST_TIMEOUT``; the frontend can offer a retry.
    """

    code = "REQUEST_TIMEOUT"
    http_status = 504
    user_message = "The request took too long. Please try again."
    severity = "warning"
    retryable = True
