import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db.generation import Generation
from app.models.question import Question

logger = logging.getLogger(__name__)

_ERROR_SUMMARY_MAX = 1000


class AuditRepository:
    """Writes one row per /generate attempt to the generations table.

    Audit writes are observability, not gating. Failures here are logged at
    WARN and swallowed so the request still returns its real outcome.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record_success(
        self,
        role: str,
        model: str,
        latency_ms: int,
        questions: list[Question],
    ) -> None:
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
