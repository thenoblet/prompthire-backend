from datetime import date

from sqlalchemy import Date, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db.base import Base


class GlobalDailyCount(Base):
    """Service-wide daily request counter used to enforce the global capacity cap.

    Composite primary key ``(day, route)`` means each route gets an independent
    daily counter. The counter is incremented atomically via
    ``INSERT ... ON CONFLICT DO UPDATE`` so no separate SELECT is needed.
    Cache hits bypass the LLM and are not counted here.

    Attributes:
        day: The UTC calendar date this counter covers.
        route: The route key being counted (e.g. ``"/api/v1/generate"``).
        count: Total successful LLM calls for this route on ``day``.
    """

    __tablename__ = "global_daily_count"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    route: Mapped[str] = mapped_column(Text, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False)
