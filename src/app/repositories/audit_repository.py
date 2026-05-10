import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db.generation import Generation
from app.models.question import Question

logger = logging.getLogger(__name__)

_ERROR_SUMMARY_MAX = 1000


class AuditRepository:
    """Writes one row per ``/generate`` attempt to the ``generations`` table.

    Fronts the ``Generation`` ORM model. All three public methods commit
    inline; on any database error the exception is logged at WARN and swallowed
    so that audit failures never affect the user-facing response. Audit writes
    are observability, not gating.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Bind the repository to a request-scoped session.

        Args:
            session: The async session this repository reads and writes through.
        """
        self._session = session

    async def record_success(
        self,
        role: str,
        model: str,
        latency_ms: int,
        questions: list[Question],
    ) -> None:
        """Write a ``status='ok'`` generation row with the returned questions.

        Commits within the call. Failures are logged at WARN and silently
        swallowed — callers do not need to handle exceptions from this method.

        Args:
            role: The normalised role string submitted by the user.
            model: The litellm model identifier used for the generation.
            latency_ms: End-to-end request latency in milliseconds.
            questions: The three questions returned by the LLM, serialised into
                the JSONB ``questions`` column.
        """
        try:
            self._session.add(
                Generation(
                    role=role,
                    model=model,
                    status="ok",
                    latency_ms=latency_ms,
                    questions={
                        "questions": [
                            {
                                "category": q.category,
                                "question": q.question,
                                "rationale": q.rationale,
                            }
                            for q in questions
                        ]
                    },
                )
            )
            await self._session.commit()
        except Exception as e:
            logger.warning("audit write failed (success path): %s", type(e).__name__)
            await self._session.rollback()

    async def record_failure(
        self,
        role: str,
        model: str,
        latency_ms: int,
        status: str,
        error_summary: str,
    ) -> None:
        """Write a failure generation row with an error summary.

        Commits within the call. Failures are logged at WARN and silently
        swallowed. The ``error_summary`` is truncated to 1000 characters before
        persisting.

        Args:
            role: The normalised role string submitted by the user.
            model: The litellm model identifier used for the attempt.
            latency_ms: End-to-end request latency in milliseconds.
            status: Generation status string; one of ``'bad_shape'`` or
                ``'upstream_err'``.
            error_summary: Short description of the exception, including its
                type and message.
        """
        try:
            self._session.add(
                Generation(
                    role=role,
                    model=model,
                    status=status,
                    latency_ms=latency_ms,
                    error_summary=error_summary[:_ERROR_SUMMARY_MAX],
                )
            )
            await self._session.commit()
        except Exception as e:
            logger.warning("audit write failed (failure path): %s", type(e).__name__)
            await self._session.rollback()

    async def record_cache_hit(
        self,
        role: str,
        model: str,
        latency_ms: int,
        questions: list[Question],
    ) -> None:
        """Write a ``status='cache_hit'`` generation row with the cached questions.

        Commits within the call. Failures are logged at WARN and silently
        swallowed.

        Args:
            role: The normalised role string submitted by the user.
            model: The litellm model identifier associated with the cache entry.
            latency_ms: End-to-end request latency in milliseconds (typically
                very small for cache hits).
            questions: The three questions returned from cache, serialised into
                the JSONB ``questions`` column.
        """
        try:
            self._session.add(
                Generation(
                    role=role,
                    model=model,
                    status="cache_hit",
                    latency_ms=latency_ms,
                    questions={
                        "questions": [
                            {
                                "category": q.category,
                                "question": q.question,
                                "rationale": q.rationale,
                            }
                            for q in questions
                        ]
                    },
                )
            )
            await self._session.commit()
        except Exception as e:
            logger.warning("audit write failed (cache_hit path): %s", type(e).__name__)
            await self._session.rollback()
