"""Database connection and session management."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DB_POOL_SIZE = 5
DB_MAX_OVERFLOW = 10


class DatabaseManager:
    """Owns the SQLAlchemy async engine and session factory for the application.

    A single instance is created at startup and shared for the lifetime of the
    process. Sessions are handed out per-request via ``get_session`` and are
    committed or rolled back automatically. Connection pooling uses
    ``pool_pre_ping`` to detect stale connections before they reach application
    code.
    """

    def __init__(self, connection_string: str) -> None:
        """Create the async engine and configure the session factory.

        Args:
            connection_string: SQLAlchemy async-compatible database URL
                (e.g. ``"postgresql+asyncpg://user:pass@host/db"``).
        """
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
        """Yield a request-scoped session with automatic commit and rollback.

        Commits the session on clean exit and rolls back on any exception before
        re-raising. Intended for use as a FastAPI dependency via ``Depends``.

        Yields:
            An ``AsyncSession`` bound to a single database connection for the
            duration of the request.
        """
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def dispose(self) -> None:
        """Gracefully close all pooled connections.

        Called during application shutdown to ensure connections are released
        before the process exits.
        """
        await self.engine.dispose()
