"""Database connection and session management."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DB_POOL_SIZE = 5
DB_MAX_OVERFLOW = 10


class DatabaseManager:
    """Manages async database connections and sessions."""

    def __init__(self, connection_string: str) -> None:
        self.engine = create_async_engine(
            connection_string,
            echo=False,
            pool_pre_ping=True,
            pool_size=DB_POOL_SIZE,
            max_overflow=DB_MAX_OVERFLOW,
        )
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Yield a session with automatic commit/rollback."""
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def dispose(self) -> None:
        """Clean up engine connections."""
        await self.engine.dispose()
