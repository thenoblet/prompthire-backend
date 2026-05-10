import asyncio
import logging
import time

from app.core.exceptions import (
    BadShapeError,
    DatabaseUnavailableError,
    RequestTimeoutError,
    ServiceAtCapacityError,
    UpstreamError,
)
from app.infrastructure.llm import LLMClient
from app.models.question import Question
from app.repositories.audit_repository import AuditRepository
from app.repositories.cache_repository import CacheRepository, normalize_role
from app.repositories.rate_limit_repository import RateLimitRepository

logger = logging.getLogger(__name__)

_ROUTE_KEY = "/api/v1/generate"


class QuestionService:
    """Orchestrates the full question-generation pipeline for a single request.

    Coordinates the cache, rate-limit, LLM, and audit repositories in a fixed
    sequence: cache lookup → global cap check → LLM call → global counter
    increment → cache write → audit write. Each step is guarded so that
    non-critical failures (audit writes, cache inserts, global counter
    increments) do not abort the request.
    """

    def __init__(
        self,
        llm: LLMClient,
        audit: AuditRepository,
        cache: CacheRepository,
        rate_limit: RateLimitRepository,
        cache_enabled: bool,
        cache_ttl_hours: int,
        global_daily_cap: int,
        request_budget_seconds: int,
    ) -> None:
        """Wire up the service with its dependencies and configuration.

        Args:
            llm: Configured LLM client used to generate questions.
            audit: Repository for writing generation audit rows.
            cache: Repository for reading and writing cached question sets.
            rate_limit: Repository for reading and incrementing rate limit
                counters.
            cache_enabled: Whether the question cache should be consulted and
                populated. When ``False``, every request hits the LLM directly.
            cache_ttl_hours: TTL in hours for newly written cache entries.
            global_daily_cap: Maximum number of LLM calls allowed per day
                service-wide. Cache hits do not count against this cap.
            request_budget_seconds: Wallclock budget for the LLM chain. When
                exceeded the LLM call is cancelled and ``RequestTimeoutError``
                is raised so the user does not wait through the full retry +
                fallback worst case.
        """
        self._llm = llm
        self._audit = audit
        self._cache = cache
        self._rate_limit = rate_limit
        self._cache_enabled = cache_enabled
        self._cache_ttl_hours = cache_ttl_hours
        self._global_daily_cap = global_daily_cap
        self._request_budget_seconds = request_budget_seconds

    async def generate(self, role: str) -> list[Question]:
        """Generate three interview questions for the given role.

        Executes the pipeline: normalise role → cache lookup → global cap
        check → LLM call → global counter increment → cache write → audit
        success write. Cache hits short-circuit the pipeline after step 2.
        The global cap is checked before the LLM call and incremented only
        on success; failed LLM calls do not consume cap quota.

        Args:
            role: The raw role string from the request. Normalised internally
                before cache keying and LLM prompting.

        Returns:
            A list of exactly three ``Question`` objects.

        Raises:
            DatabaseUnavailableError: When the global cap read fails.
            ServiceAtCapacityError: When the global daily cap has been reached.
            RequestTimeoutError: When the LLM chain exceeds
                ``request_budget_seconds`` wallclock; the in-flight call is
                cancelled.
            BadShapeError: When the LLM returns a response that fails schema
                validation (propagated from ``LLMClient``).
            UpstreamError: When the LLM provider is unreachable or fails after
                retries (propagated from ``LLMClient``).
        """
        normalized = normalize_role(role)
        start = time.monotonic()

        # 1. Cache lookup (skipped if disabled).
        if self._cache_enabled:
            cached = await self._cache.lookup(self._llm.model, normalized)
            if cached is not None:
                latency_ms = int((time.monotonic() - start) * 1000)
                await self._audit.record_cache_hit(
                    role=normalized,
                    model=self._llm.model,
                    latency_ms=latency_ms,
                    questions=cached,
                )
                return cached

        # 2. Global daily cap check (only on cache miss / cache disabled).
        try:
            current_count = await self._rate_limit.read_global(_ROUTE_KEY)
        except Exception as e:
            logger.warning("global cap read failed: %s", type(e).__name__)
            raise DatabaseUnavailableError() from e
        if current_count >= self._global_daily_cap:
            logger.info(
                "global daily cap reached count=%s cap=%s",
                current_count,
                self._global_daily_cap,
            )
            raise ServiceAtCapacityError()

        # 3. LLM call, bounded by the request wallclock budget. May fall back
        # to a secondary model — result.model records which one actually
        # answered. asyncio.wait_for cancels the in-flight task on timeout
        # so we don't keep paying for retries the user is no longer waiting on.
        try:
            result = await asyncio.wait_for(
                self._llm.generate(normalized),
                timeout=self._request_budget_seconds,
            )
        except TimeoutError as e:
            logger.warning(
                "request budget exceeded budget=%ss; aborting LLM chain",
                self._request_budget_seconds,
            )
            await self._record_failure(normalized, start, "upstream_err", e)
            raise RequestTimeoutError() from None
        except BadShapeError as e:
            await self._record_failure(normalized, start, "bad_shape", e)
            raise
        except UpstreamError as e:
            await self._record_failure(normalized, start, "upstream_err", e)
            raise

        # 4. Increment global counter (after successful LLM call only).
        try:
            await self._rate_limit.hit_global(_ROUTE_KEY)
        except Exception as e:
            # Non-fatal: counter undercounts by one, request still succeeds.
            logger.warning("global counter increment failed: %s", type(e).__name__)

        # 5. Cache write (skipped if disabled). Non-fatal on failure.
        # Cache key uses the PRIMARY model id so fallbacks share the cache —
        # subsequent identical requests hit cache regardless of which model
        # served the original.
        if self._cache_enabled:
            await self._cache.insert(
                model=self._llm.model,
                normalized_role=normalized,
                questions=result.questions,
                ttl_hours=self._cache_ttl_hours,
            )

        # 6. Audit success — record the model that ACTUALLY answered, which
        # may be a fallback rather than the primary.
        latency_ms = int((time.monotonic() - start) * 1000)
        await self._audit.record_success(
            role=normalized,
            model=result.model,
            latency_ms=latency_ms,
            questions=result.questions,
        )
        return result.questions

    async def _record_failure(
        self,
        role: str,
        start: float,
        status: str,
        error: Exception,
    ) -> None:
        """Write a failure audit row, computing latency from ``start``.

        Extracts the root cause from ``error.__cause__`` if present and formats
        the error summary as ``"TypeName: message"``. Delegates to
        ``AuditRepository.record_failure``, which swallows its own exceptions.

        Args:
            role: The normalised role string for the audit row.
            start: The ``time.monotonic()`` value captured at the start of the
                request, used to compute ``latency_ms``.
            status: Generation status string (``'bad_shape'`` or
                ``'upstream_err'``).
            error: The exception that caused the failure. Its ``__cause__``
                is used as the summary source when available.
        """
        latency_ms = int((time.monotonic() - start) * 1000)
        cause = error.__cause__ or error
        await self._audit.record_failure(
            role=role,
            model=self._llm.model,
            latency_ms=latency_ms,
            status=status,
            error_summary=f"{type(cause).__name__}: {cause}",
        )
