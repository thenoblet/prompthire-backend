from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, Request
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings, get_settings
from app.core.deps import SessionDep
from app.core.exceptions import DatabaseUnavailableError, RateLimitedError
from app.repositories.rate_limit_repository import RateLimitRepository

SettingsDep = Annotated[Settings, Depends(get_settings)]


def _client_ip(request: Request, trust_forwarded_for: bool) -> str:
    if trust_forwarded_for:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
    if request.client is None:
        return "unknown"
    return request.client.host


def make_rate_limiter(
    route: str,
) -> Callable[..., Coroutine[Any, Any, None]]:
    """Build a FastAPI dependency that rate-limits requests by IP for a given route key."""

    async def _dep(
        request: Request,
        session: SessionDep,
        settings: SettingsDep,
    ) -> None:
        ip = _client_ip(request, settings.trust_forwarded_for)
        repo = RateLimitRepository(session)
        try:
            outcome = await repo.hit(ip, route)
        except SQLAlchemyError as e:
            raise DatabaseUnavailableError() from e
        if outcome.count > settings.rate_limit_per_min:
            raise RateLimitedError()

    return _dep
