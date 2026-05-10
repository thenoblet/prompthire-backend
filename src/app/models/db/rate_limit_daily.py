from datetime import date

from sqlalchemy import Date, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db.base import Base


class RateLimitDaily(Base):
    """Per-IP daily request counter for the day-level rate limit.

    Composite primary key ``(ip, route, day)`` where ``day`` is the current
    UTC calendar date. The counter is incremented atomically via
    ``INSERT ... ON CONFLICT DO UPDATE``. Old day rows accumulate and are not
    pruned automatically.

    Attributes:
        ip: The client IP address used for rate limiting.
        route: The route key being limited (e.g. ``"/api/v1/generate"``).
        day: The UTC calendar date this counter covers.
        count: Number of requests from ``ip`` to ``route`` on ``day``.
    """

    __tablename__ = "rate_limit_daily"

    ip: Mapped[str] = mapped_column(Text, primary_key=True)
    route: Mapped[str] = mapped_column(Text, primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False)
