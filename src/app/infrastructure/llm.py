"""LLM client wrapping litellm + instructor with tenacity retries.

The only place the litellm/instructor libraries are imported. Returns domain
`Question` objects; callers never see the Pydantic shape used to coerce the
model output.
"""

from __future__ import annotations

import logging

import instructor
from instructor.exceptions import InstructorRetryException
from pydantic import ValidationError
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.exceptions import BadShapeError, UpstreamError
from app.infrastructure.prompts import SYSTEM_PROMPT, user_prompt
from app.models.question import Question
from app.schemas.llm import LLMQuestions

logger = logging.getLogger(__name__)


MAX_RETRY_ATTEMPTS = 3
RETRY_BACKOFF_MULTIPLIER = 1
RETRY_MIN_WAIT_SECONDS = 2
RETRY_MAX_WAIT_SECONDS = 10


def _litellm():
    # Imported lazily to avoid heavy import-time cost (litellm pulls in many providers).
    import litellm  # noqa: PLC0415

    litellm.drop_params = True
    return litellm


class LLMClient:
    """Generates exactly three role-specific interview questions via litellm + instructor.

    Transient provider errors (rate limit, timeout, connection) are retried with
    exponential backoff. Schema-validation failures from instructor are surfaced
    as `BadShapeError`; everything else as `UpstreamError`.
    """

    def __init__(self, model: str, timeout_seconds: int = 30) -> None:
        self._model = model
        self._timeout = timeout_seconds

    @property
    def model(self) -> str:
        return self._model

    async def generate(self, role: str) -> list[Question]:
        litellm = _litellm()
        client = instructor.from_litellm(litellm.acompletion)

        retry_exceptions = (
            litellm.RateLimitError,
            litellm.Timeout,
            litellm.APIConnectionError,
        )

        try:
            result: LLMQuestions | None = None
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(MAX_RETRY_ATTEMPTS),
                wait=wait_exponential(
                    multiplier=RETRY_BACKOFF_MULTIPLIER,
                    min=RETRY_MIN_WAIT_SECONDS,
                    max=RETRY_MAX_WAIT_SECONDS,
                ),
                retry=retry_if_exception_type(retry_exceptions),
                reraise=True,
            ):
                with attempt:
                    result = await client.chat.completions.create(
                        model=self._model,
                        response_model=LLMQuestions,
                        messages=[
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": user_prompt(role)},
                        ],
                        timeout=self._timeout,
                        max_retries=1,
                    )
        except ValidationError as e:
            logger.warning("schema validation failed: %s", type(e).__name__)
            raise BadShapeError() from e
        except InstructorRetryException as e:
            cause = e.__cause__ or e.__context__
            if isinstance(cause, retry_exceptions):
                logger.warning("upstream LLM call failed: %s", type(cause).__name__)
                raise UpstreamError() from e
            logger.warning("instructor exhausted retries: %s", type(e).__name__)
            raise BadShapeError() from e
        except retry_exceptions as e:
            logger.warning("upstream LLM call failed after retries: %s", type(e).__name__)
            raise UpstreamError() from e
        except Exception as e:
            logger.warning("upstream LLM call failed: %s", type(e).__name__)
            raise UpstreamError() from e

        if result is None:
            raise UpstreamError()

        return [
            Question(category=q.category, question=q.question, rationale=q.rationale)
            for q in result.questions
        ]
