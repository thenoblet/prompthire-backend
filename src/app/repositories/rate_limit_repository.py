from datetime import UTC, datetime
from typing import NamedTuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class RateLimitOutcome(NamedTuple):
    count: int
    window_start: datetime


class RateLimitRepository:
    """Postgres-backed fixed-window rate limiter.

    One row per (ip, route, window_start). Each request is an UPSERT that
    returns the new count; the caller compares it to the configured limit.
    """

    _UPSERT_SQL = text(
        """
        INSERT INTO rate_limit_buckets (ip, route, window_start, count)
        VALUES (:ip, :route, :window_start, 1)
        ON CONFLICT (ip, route, window_start)
        DO UPDATE SET count = rate_limit_buckets.count + 1
        RETURNING count
        """
    )

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def hit(self, ip: str, route: str) -> RateLimitOutcome:
        now = datetime.now(UTC)
        window_start = now.replace(second=0, microsecond=0)
        result = await self._session.execute(
            self._UPSERT_SQL,
            {"ip": ip, "route": route, "window_start": window_start},
        )
        count: int = result.scalar_one()
        await self._session.commit()
        return RateLimitOutcome(count=count, window_start=window_start)
