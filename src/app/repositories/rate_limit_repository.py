from datetime import UTC, date, datetime
from typing import NamedTuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class RateLimitOutcome(NamedTuple):
    """Result of a per-IP per-minute rate limit increment.

    Attributes:
        count: The new request count for the current minute window after the
            atomic upsert.
        window_start: The UTC datetime marking the start of the current
            one-minute window (seconds and microseconds zeroed).
    """

    count: int
    window_start: datetime


class DailyOutcome(NamedTuple):
    """Result of a per-IP per-day rate limit increment.

    Attributes:
        count: The new request count for today after the atomic upsert.
        day: The UTC calendar date the counter covers.
    """

    count: int
    day: date


class GlobalOutcome(NamedTuple):
    """Result of a global per-day route counter increment.

    Attributes:
        count: The new total request count for the route today after the
            atomic upsert.
        day: The UTC calendar date the counter covers.
    """

    count: int
    day: date


class RateLimitRepository:
    """Postgres-backed counters for rate limiting.

    Three windows: per-(ip, route) per minute, per-(ip, route) per day, and
    global per-(route) per day. Each is an atomic UPSERT returning the new
    count; the caller compares to the configured cap.
    """

    _UPSERT_MINUTE_SQL = text(
        """
        INSERT INTO rate_limit_buckets (ip, route, window_start, count)
        VALUES (:ip, :route, :window_start, 1)
        ON CONFLICT (ip, route, window_start)
        DO UPDATE SET count = rate_limit_buckets.count + 1
        RETURNING count
        """
    )

    _UPSERT_DAILY_SQL = text(
        """
        INSERT INTO rate_limit_daily (ip, route, day, count)
        VALUES (:ip, :route, :day, 1)
        ON CONFLICT (ip, route, day)
        DO UPDATE SET count = rate_limit_daily.count + 1
        RETURNING count
        """
    )

    _UPSERT_GLOBAL_SQL = text(
        """
        INSERT INTO global_daily_count (day, route, count)
        VALUES (:day, :route, 1)
        ON CONFLICT (day, route)
        DO UPDATE SET count = global_daily_count.count + 1
        RETURNING count
        """
    )

    _SELECT_GLOBAL_SQL = text(
        """
        SELECT count FROM global_daily_count
        WHERE day = :day AND route = :route
        """
    )

    def __init__(self, session: AsyncSession) -> None:
        """Bind the repository to a request-scoped session.

        Args:
            session: The async session this repository reads and writes through.
                Each method commits inline.
        """
        self._session = session

    async def hit(self, ip: str, route: str) -> RateLimitOutcome:
        """Atomically increment the per-IP per-minute bucket and return the new count.

        The window key is the current UTC minute with seconds zeroed. Commits
        within the call.

        Args:
            ip: The client IP address.
            route: The route key being limited (e.g. ``"/api/v1/generate"``).

        Returns:
            A ``RateLimitOutcome`` with the updated count and the window start
            timestamp. The caller compares ``count`` to the configured cap.
        """
        now = datetime.now(UTC)
        window_start = now.replace(second=0, microsecond=0)
        result = await self._session.execute(
            self._UPSERT_MINUTE_SQL,
            {"ip": ip, "route": route, "window_start": window_start},
        )
        count: int = result.scalar_one()
        await self._session.commit()
        return RateLimitOutcome(count=count, window_start=window_start)

    async def hit_daily(self, ip: str, route: str) -> DailyOutcome:
        """Atomically increment the per-IP per-day counter and return the new count.

        Commits within the call.

        Args:
            ip: The client IP address.
            route: The route key being limited.

        Returns:
            A ``DailyOutcome`` with the updated count and today's UTC date.
            The caller compares ``count`` to the configured daily cap.
        """
        today = datetime.now(UTC).date()
        result = await self._session.execute(
            self._UPSERT_DAILY_SQL,
            {"ip": ip, "route": route, "day": today},
        )
        count: int = result.scalar_one()
        await self._session.commit()
        return DailyOutcome(count=count, day=today)

    async def hit_global(self, route: str) -> GlobalOutcome:
        """Atomically increment the global per-day counter for a route.

        Called after a successful LLM generation, not on cache hits. Commits
        within the call.

        Args:
            route: The route key being counted (e.g. ``"/api/v1/generate"``).

        Returns:
            A ``GlobalOutcome`` with the updated count and today's UTC date.
        """
        today = datetime.now(UTC).date()
        result = await self._session.execute(
            self._UPSERT_GLOBAL_SQL,
            {"day": today, "route": route},
        )
        count: int = result.scalar_one()
        await self._session.commit()
        return GlobalOutcome(count=count, day=today)

    async def read_global(self, route: str) -> int:
        """Read the current global per-day count for a route without modifying it.

        Used by ``QuestionService`` to check the cap before initiating an LLM
        call. Does not commit. Returns 0 if no row exists for today.

        Args:
            route: The route key to query (e.g. ``"/api/v1/generate"``).

        Returns:
            The current count for today, or ``0`` if no row exists yet.
        """
        today = datetime.now(UTC).date()
        result = await self._session.execute(
            self._SELECT_GLOBAL_SQL,
            {"day": today, "route": route},
        )
        row = result.scalar_one_or_none()
        return row if row is not None else 0
