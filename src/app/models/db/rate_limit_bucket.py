from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db.base import Base


class RateLimitBucket(Base):
    """Per-IP fixed-window minute-level rate limit counter.

    Composite primary key ``(ip, route, window_start)`` where ``window_start``
    is the current minute truncated to zero seconds. Each unique combination
    maps to one counter row; the counter is incremented atomically via
    ``INSERT ... ON CONFLICT DO UPDATE``. Old window rows are not deleted
    eagerly; an index on ``window_start`` supports future periodic cleanup.

    Attributes:
        ip: The client IP address, sourced from ``X-Forwarded-For`` or the
            direct connection depending on ``TRUST_FORWARDED_FOR``.
        route: The route key being limited (e.g. ``"/api/v1/generate"``).
        window_start: The start of the current one-minute window (seconds and
            microseconds zeroed).
        count: Number of requests from ``ip`` to ``route`` within this window.
    """

    __tablename__ = "rate_limit_buckets"
    __table_args__ = (Index("ix_rate_limit_buckets_window_start", "window_start"),)

    ip: Mapped[str] = mapped_column(Text, primary_key=True)
    route: Mapped[str] = mapped_column(Text, primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False)
