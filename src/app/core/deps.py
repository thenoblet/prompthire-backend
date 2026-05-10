from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.infrastructure.database import DatabaseManager
from app.infrastructure.llm import LLMClient
from app.repositories.audit_repository import AuditRepository
from app.repositories.cache_repository import CacheRepository
from app.repositories.rate_limit_repository import RateLimitRepository
from app.services.question_service import QuestionService


def get_db_manager(request: Request) -> DatabaseManager:
    return request.app.state.db


async def get_db(
    manager: Annotated[DatabaseManager, Depends(get_db_manager)],
) -> AsyncGenerator[AsyncSession, None]:
    async for session in manager.get_session():
        yield session


def get_llm_client(request: Request) -> LLMClient:
    return request.app.state.llm


SessionDep = Annotated[AsyncSession, Depends(get_db)]
LLMClientDep = Annotated[LLMClient, Depends(get_llm_client)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_question_service(
    session: SessionDep,
    llm: LLMClientDep,
    settings: SettingsDep,
) -> QuestionService:
    return QuestionService(
        llm=llm,
        audit=AuditRepository(session),
        cache=CacheRepository(session),
        rate_limit=RateLimitRepository(session),
        cache_enabled=settings.cache_enabled,
        cache_ttl_hours=settings.cache_ttl_hours,
        global_daily_cap=settings.global_daily_cap,
    )


QuestionServiceDep = Annotated[QuestionService, Depends(get_question_service)]
