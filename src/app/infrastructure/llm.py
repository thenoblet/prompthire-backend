"""LLM client wrapping litellm + instructor with tenacity retries and a fallback chain.

The only place the litellm/instructor libraries are imported. Returns a
``LLMResult`` with the domain ``Question`` objects and the model id that
actually answered. Callers never see the Pydantic shape used to coerce the
model output.
"""

import logging
from dataclasses import dataclass

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


@dataclass(frozen=True, slots=True)
class LLMResult:
    """Outcome of a successful generation.

    Attributes:
        questions: The three interview questions produced by the LLM, in the
            domain shape (frozen ``Question`` dataclass).
        model: The litellm model identifier that actually answered the request.
            Differs from the primary model when a fallback was used.
    """

    questions: list[Question]
    model: str


def _litellm():
    # Imported lazily to avoid heavy import-time cost (litellm pulls in many providers).
    import litellm  # noqa: PLC0415

    litellm.drop_params = True
    return litellm


def _root_cause(exc: BaseException) -> BaseException:
    """Walk the __cause__/__context__ chain and return the deepest exception.

    instructor wraps provider errors in ``InstructorRetryException``, sometimes
    via ``__cause__`` and sometimes via ``__context__``. Single-level inspection
    misses the actual root error (e.g. ``litellm.RateLimitError``), so we walk
    the full chain to classify accurately.
    """
    seen: set[int] = set()
    current: BaseException = exc
    while id(current) not in seen:
        seen.add(id(current))
        nxt = current.__cause__ or current.__context__
        if nxt is None:
            return current
        current = nxt
    return current


def _is_provider_error(exc: BaseException) -> bool:
    """Return True if the exception originated from litellm or an underlying provider SDK.

    Used to distinguish "the upstream API itself failed" (auth, rate limit,
    connection, server error) from "the model returned the wrong shape"
    (a Pydantic ``ValidationError`` produced by instructor).
    """
    module = type(exc).__module__ or ""
    return module.startswith(("litellm", "openai", "httpx", "anthropic", "google"))


class LLMClient:
    """Generates three role-specific interview questions via litellm + instructor.

    Two layers of resilience:

    1. **Per-model tenacity retries** for transient provider errors
       (rate-limit, timeout, connection) up to ``MAX_RETRY_ATTEMPTS``.
    2. **Outer model fallback chain** — when a model exhausts its retry
       budget OR returns malformed output OR auth-fails, the next model in
       ``fallback_models`` is tried. Schema-validation failures and unknown
       errors also trigger fallback (the next model might do better).

    Only when ALL models have failed is ``UpstreamError`` (or, if the last
    failure was schema-shaped, ``BadShapeError``) raised. litellm is imported
    lazily to avoid heavy import-time cost.
    """

    def __init__(
        self,
        model: str,
        timeout_seconds: int = 30,
        fallback_models: list[str] | None = None,
    ) -> None:
        """Configure the primary model and an optional fallback chain.

        Args:
            model: The primary litellm model identifier
                (e.g. ``"gemini/gemini-2.5-flash"``).
            timeout_seconds: Per-call timeout forwarded to litellm. Defaults
                to 30 seconds.
            fallback_models: Optional ordered list of fallback model
                identifiers tried if the primary exhausts its retries
                (e.g. ``["openrouter/poolside/laguna-m.1:free"]``). Each
                fallback gets its own retry budget.
        """
        self._timeout = timeout_seconds
        self._models: list[str] = [model, *(fallback_models or [])]

    @property
    def model(self) -> str:
        """Return the primary (first) model in the fallback chain."""
        return self._models[0]

    @property
    def models(self) -> list[str]:
        """Return the full ordered model chain (primary + fallbacks)."""
        return list(self._models)

    async def generate(self, role: str) -> LLMResult:
        """Try each model in the chain until one succeeds; raise if all fail.

        For each model, runs the tenacity-wrapped instructor + litellm call.
        If the model fails (any classified or unknown error), logs at WARN
        and tries the next. If all fail, raises ``BadShapeError`` when the
        last failure was schema-related, otherwise ``UpstreamError``.

        Args:
            role: The normalised job-role string used to build the user prompt.

        Returns:
            An ``LLMResult`` containing exactly three ``Question`` objects and
            the model id that produced them.

        Raises:
            BadShapeError: When every model in the chain produced output that
                failed Pydantic validation.
            UpstreamError: When every model failed for transient or unknown
                reasons (rate-limits, timeouts, auth, connection errors).
        """
        last_error: BadShapeError | UpstreamError | None = None
        for model_id in self._models:
            try:
                questions = await self._generate_with_model(model_id, role)
                if last_error is not None:
                    logger.info("recovered via fallback model=%s", model_id)
                return LLMResult(questions=questions, model=model_id)
            except (BadShapeError, UpstreamError) as e:
                logger.warning(
                    "model failed model=%s code=%s; trying next in chain",
                    model_id,
                    e.code,
                )
                last_error = e
                continue

        # All models exhausted.
        if last_error is not None:
            raise last_error
        raise UpstreamError()

    async def _generate_with_model(self, model: str, role: str) -> list[Question]:
        """Call a single model with tenacity retries and instructor validation.

        Internal helper used by ``generate`` to attempt one entry in the
        fallback chain. Same retry/classification semantics as the original
        single-model implementation.

        Args:
            model: The litellm model identifier to call.
            role: The normalised role string.

        Returns:
            A list of three domain ``Question`` objects.

        Raises:
            BadShapeError: On Pydantic validation failure or instructor
                retry-exhaustion that wasn't caused by a transient API error.
            UpstreamError: On exhausted transient retries or any other error.
        """
        litellm = _litellm()
        client = instructor.from_litellm(litellm.acompletion)

        retry_exceptions = (
            litellm.RateLimitError,
            litellm.Timeout,
            litellm.APIConnectionError,
        )

        result: LLMQuestions | None = None
        try:
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
                        model=model,
                        response_model=LLMQuestions,
                        messages=[
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": user_prompt(role)},
                        ],
                        timeout=self._timeout,
                        max_retries=1,
                    )
        except ValidationError as e:
            logger.warning("schema validation failed model=%s: %s", model, type(e).__name__)
            raise BadShapeError() from e
        except InstructorRetryException as e:
            root = _root_cause(e)
            if isinstance(root, retry_exceptions) or _is_provider_error(root):
                logger.warning(
                    "upstream LLM call failed model=%s root=%s msg=%s",
                    model,
                    type(root).__name__,
                    str(root)[:200],
                )
                raise UpstreamError() from e
            logger.warning(
                "instructor exhausted retries model=%s root=%s",
                model,
                type(root).__name__,
            )
            raise BadShapeError() from e
        except retry_exceptions as e:
            logger.warning(
                "upstream LLM call failed after retries model=%s: %s", model, type(e).__name__
            )
            raise UpstreamError() from e
        except Exception as e:
            logger.warning("upstream LLM call failed model=%s: %s", model, type(e).__name__)
            raise UpstreamError() from e

        if result is None:
            raise UpstreamError()

        return [
            Question(category=q.category, question=q.question, rationale=q.rationale)
            for q in result.questions
        ]
