from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Index, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db.base import Base


class Generation(Base):
    """Audit record for a single ``/api/v1/generate`` attempt.

    One row is written per request regardless of outcome (success, cache hit,
    LLM error). Writes are fire-and-forget: failures are logged at WARN and
    swallowed so the user-facing response is never affected. The ``status``
    column is constrained to ``'ok'``, ``'cache_hit'``, ``'bad_shape'``, or
    ``'upstream_err'``. ``questions`` is populated on success and cache-hit
    rows; ``error_summary`` is populated on failure rows.

    Attributes:
        id: Auto-incrementing surrogate primary key.
        created_at: UTC timestamp set by the database at insert time.
        role: The normalised role string submitted by the user.
        model: The litellm model identifier used for the attempt.
        status: Outcome of the attempt; one of the allowed check-constraint values.
        latency_ms: Wall-clock time from service entry to audit write, in
            milliseconds.
        questions: JSONB snapshot of the three questions returned; ``None`` on
            failure rows.
        error_summary: Short description of the exception on failure rows;
            ``None`` on success rows. Truncated to 1000 characters.
    """

    __tablename__ = "generations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ok', 'bad_shape', 'upstream_err')",
            name="status_in_allowed",
        ),
        Index("ix_generations_created_at", text("created_at DESC")),
        Index("ix_generations_status_created_at", "status", text("created_at DESC")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    questions: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
