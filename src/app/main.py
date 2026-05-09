import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.error_handlers import register_exception_handlers
from app.infrastructure.database import DatabaseManager
from app.infrastructure.llm import LLMClient
from app.routers import health
from app.routers.v1 import api_v1

# Export .env entries to os.environ so litellm picks up provider keys
# (GEMINI_API_KEY, ANTHROPIC_API_KEY, etc.). pydantic-settings populates the
# Settings model but does not write back to os.environ; litellm reads from there.
load_dotenv()


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.db = DatabaseManager(settings.database_url)
        app.state.llm = LLMClient(
            model=settings.litellm_model,
            timeout_seconds=settings.litellm_timeout_seconds,
        )
        try:
            yield
        finally:
            await app.state.db.dispose()

    app = FastAPI(title="PromptHire Backend", lifespan=lifespan)

    if settings.cors_origins_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins_list,
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["content-type"],
        )

    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(api_v1)
    return app


app = create_app()
