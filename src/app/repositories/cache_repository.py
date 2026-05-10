import hashlib
import logging
import re
import unicodedata
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db.question_cache import QuestionCache
from app.models.question import Question

logger = logging.getLogger(__name__)


_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_WHITESPACE = re.compile(r"\s+")


def normalize_role(role: str) -> str:
    """Normalise a role string for cache keying.

    - Unicode NFKC normalisation
    - Strip leading/trailing whitespace
    - Lowercase
    - Collapse internal whitespace runs to a single space
    - Remove control characters
    """
    s = unicodedata.normalize("NFKC", role)
    s = s.strip().lower()
    s = _WHITESPACE.sub(" ", s)
    s = _CONTROL_CHARS.sub("", s)
    return s


def role_hash(model: str, normalized_role: str) -> str:
    """Compute the cache key. Including model means provider switches invalidate naturally."""
    payload = f"{model}:{normalized_role}".encode()
    return hashlib.sha256(payload).hexdigest()


class CacheRepository:
    """Postgres-backed question cache keyed by model and normalised role.

    Stores LLM responses keyed by ``sha256("{model}:{normalized_role}")`` so
    identical roles across users share one entry and model changes naturally
    invalidate stale cache entries. Expired rows are pruned opportunistically
    on lookup rather than by a background job. Insert uses ``ON CONFLICT DO
    NOTHING`` to handle concurrent cache misses safely. All database failures
    are logged at WARN and swallowed — the cache is a performance hedge, never
    a hard dependency.
    """

    _LOOKUP_SQL = text(
        """
        SELECT response, expires_at FROM question_cache
        WHERE role_hash = :role_hash
        """
    )

    _INCREMENT_HIT_SQL = text(
        """
        UPDATE question_cache SET hit_count = hit_count + 1
        WHERE role_hash = :role_hash
        """
    )

    _DELETE_EXPIRED_BY_KEY_SQL = text(
        """
        DELETE FROM question_cache
        WHERE role_hash = :role_hash AND expires_at <= :now
        """
    )

    def __init__(self, session: AsyncSession) -> None:
        """Bind the repository to a request-scoped session.

        Args:
            session: The async session this repository reads and writes through.
                Each method commits inline and is safe to mix with other
                repositories sharing the same session.
        """
        self._session = session

    async def lookup(self, model: str, normalized_role: str) -> list[Question] | None:
        """Look up a cached response by model and normalised role.

        On a fresh hit, increments ``hit_count`` and returns the cached
        questions. On an expired hit, deletes the row opportunistically and
        returns ``None``. On any database error the failure is logged at WARN
        and ``None`` is returned.

        Args:
            model: The litellm model identifier used when the entry was cached.
            normalized_role: The role string after NFKC and whitespace
                normalisation. See ``normalize_role``.

        Returns:
            A list of three ``Question`` objects on a fresh cache hit,
            otherwise ``None``.
        """
        key = role_hash(model, normalized_role)
        try:
            result = await self._session.execute(self._LOOKUP_SQL, {"role_hash": key})
            row = result.first()
            if row is None:
                return None
            response, expires_at = row
            now = datetime.now(UTC)
            if expires_at <= now:
                # Opportunistic prune of the expired row.
                await self._session.execute(
                    self._DELETE_EXPIRED_BY_KEY_SQL,
                    {"role_hash": key, "now": now},
                )
                await self._session.commit()
                return None
            await self._session.execute(self._INCREMENT_HIT_SQL, {"role_hash": key})
            await self._session.commit()
            return [
                Question(
                    category=q["category"],
                    question=q["question"],
                    rationale=q["rationale"],
                )
                for q in response["questions"]
            ]
        except Exception as e:
            logger.warning("cache lookup failed: %s", type(e).__name__)
            await self._session.rollback()
            return None

    async def insert(
        self,
        model: str,
        normalized_role: str,
        questions: list[Question],
        ttl_hours: int,
    ) -> None:
        """Insert a new cache entry; silently skips if the key already exists.

        Uses ``ON CONFLICT DO NOTHING`` on ``role_hash`` to handle concurrent
        cache misses without raising an error. Commits within the call. On any
        database error the failure is logged at WARN and swallowed.

        Args:
            model: The litellm model identifier used for the generation.
            normalized_role: The NFKC-normalised, lowercased role string.
            questions: The three questions to cache, serialised to JSONB.
            ttl_hours: Number of hours from now until the entry expires.
        """
        key = role_hash(model, normalized_role)
        now = datetime.now(UTC)
        expires_at = now + timedelta(hours=ttl_hours)
        response = {
            "questions": [
                {
                    "category": q.category,
                    "question": q.question,
                    "rationale": q.rationale,
                }
                for q in questions
            ]
        }
        try:
            stmt = (
                insert(QuestionCache)
                .values(
                    role_hash=key,
                    model=model,
                    normalized_role=normalized_role,
                    response=response,
                    created_at=now,
                    expires_at=expires_at,
                )
                .on_conflict_do_nothing(index_elements=["role_hash"])
            )
            await self._session.execute(stmt)
            await self._session.commit()
        except Exception as e:
            logger.warning("cache insert failed: %s", type(e).__name__)
            await self._session.rollback()
