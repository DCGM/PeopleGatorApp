"""Async SQLAlchemy setup for the opt-in PostgreSQL demo."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from people_gator_api.services.postgres_demo.models import Base


def make_postgres_engine(database_url: str, *, echo: bool = False) -> AsyncEngine:
    """Build an asyncpg engine for the isolated demo database."""
    if not database_url.startswith("postgresql+asyncpg://"):
        raise ValueError("database_url must use the postgresql+asyncpg driver")

    return create_async_engine(database_url, echo=echo, pool_pre_ping=True)


def make_postgres_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Create non-expiring sessions suitable for request-scoped dependencies."""
    return async_sessionmaker(engine, expire_on_commit=False)


async def create_postgres_schema(engine: AsyncEngine) -> None:
    """Create extensions and demo tables; intentionally separate from API startup."""
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def session_dependency(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Small FastAPI-compatible dependency adapter for an eventual demo router."""
    async with factory() as session:
        yield session
