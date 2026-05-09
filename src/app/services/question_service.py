import logging
import time

from app.core.exceptions import BadShapeError, UpstreamError
from app.infrastructure.llm import LLMClient
from app.models.question import Question
from app.repositories.audit_repository import AuditRepository

logger = logging.getLogger(__name__)


class QuestionService:
    def __init__(self, llm: LLMClient, audit: AuditRepository) -> None:
        self._llm = llm
        self._audit = audit

    async def generate(self, role: str) -> list[Question]:
        start = time.monotonic()
        try:
            questions = await self._llm.generate(role)
        except BadShapeError as e:
            await self._record_failure(role, start, "bad_shape", e)
            raise
        except UpstreamError as e:
            await self._record_failure(role, start, "upstream_err", e)
            raise

        latency_ms = int((time.monotonic() - start) * 1000)
        await self._audit.record_success(
            role=role,
            model=self._llm.model,
            latency_ms=latency_ms,
            questions=questions,
        )
        return questions

    async def _record_failure(
        self,
        role: str,
        start: float,
        status: str,
        error: Exception,
    ) -> None:
        latency_ms = int((time.monotonic() - start) * 1000)
        cause = error.__cause__ or error
        await self._audit.record_failure(
            role=role,
            model=self._llm.model,
            latency_ms=latency_ms,
            status=status,
            error_summary=f"{type(cause).__name__}: {cause}",
        )
