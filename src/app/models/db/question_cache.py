from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db.base import Base


class QuestionCache(Base):
    """Postgres-backed cache of LLM-generated question sets.

    The primary key ``role_hash`` is the SHA-256 of ``"{model}:{normalized_role}"``
    so cache hits are shared across users who submit the same role string and so
    model switches naturally invalidate stale entries. Expired rows are not
    deleted by a background job; instead they are pruned opportunistically by
    ``CacheRepository.lookup`` on the next request for that key. An index on
    ``expires_at`` supports future batch-prune queries.

    Attributes:
        role_hash: SHA-256 hex digest of the cache key; serves as the primary key.
        model: The litellm model identifier used to generate the response.
        normalized_role: The NFKC-normalised, lowercased role string used as
            the human-readable part of the cache key.
        response: JSONB snapshot of the three questions, stored in the same
            shape as the ``Generation.questions`` column.
        created_at: UTC timestamp set by the database at insert time.
        expires_at: UTC timestamp after which the entry is considered stale
            and will be pruned on next lookup.
        hit_count: Running total of cache hits for this entry; incremented
            atomically on every fresh hit.
    """

    __tablename__ = "question_cache"
    __table_args__ = (Index("ix_question_cache_expires_at", "expires_at"),)

    role_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_role: Mapped[str] = mapped_column(Text, nullable=False)
    response: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
