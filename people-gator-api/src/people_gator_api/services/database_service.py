"""Request-scoped database dependencies.

Core API persistence is exposed only through the backend-neutral Database
contract. The raw Weaviate dependency remains available for blob-derived
subresources that are not part of that contract.
"""

from collections.abc import AsyncGenerator
from typing import Annotated, Any

from fastapi import Depends

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy import URL


from people_gator_api.persistence.contracts import Database
from people_gator_api.persistence.postgres import postgres_database
from people_gator_api.models import Base

from people_gator_api.settings import settings


_postgres_engine: AsyncEngine | None = None
_postgres_sessions: async_sessionmaker[AsyncSession] | None = None


def _postgres_url() -> str:
    config = settings.persistence.postgres
    return URL.create(
        drivername="postgresql+asyncpg",
        username=config.user,
        password=config.password,
        host=config.host,
        port=config.port,
        database=config.database,
    ).render_as_string(hide_password=False)

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
    """Create extensions and PostgreSQL persistence tables."""
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def init_postgres() -> None:
    """Initialize the process-wide engine and request session factory."""
    global _postgres_engine, _postgres_sessions
    if _postgres_engine is not None:
        return
    _postgres_engine = make_postgres_engine(
        _postgres_url(),
        echo=settings.debug,
    )
    _postgres_sessions = make_postgres_session_factory(_postgres_engine)


async def close_postgres() -> None:
    """Dispose the process-wide PostgreSQL connection pool."""
    global _postgres_engine, _postgres_sessions
    engine = _postgres_engine
    _postgres_engine = None
    _postgres_sessions = None
    if engine is not None:
        await engine.dispose()


async def get_database() -> AsyncGenerator[Database, None]:
    """Yield one PostgreSQL-backed contract facade per request."""
    if _postgres_sessions is None:
        await init_postgres()
    assert _postgres_sessions is not None
    async with _postgres_sessions() as session:
        yield postgres_database(session)


type DatabaseDependency = Annotated[Database, Depends(get_database)]


async def get_session() -> AsyncGenerator[Any, None]:
    """Yield the raw vector client only to non-contract legacy subresources."""
    from people_gator_api.services.weaviate_service.client import get_weaviate_client

    yield get_weaviate_client()


type WeaviateSessionDependency = Annotated[
    Any,
    Depends(get_session),
]


async def init_db() -> None:
    """Create the PostgreSQL persistence schema."""
    await init_postgres()
    assert _postgres_engine is not None
    await create_postgres_schema(_postgres_engine)


__all__ = [
    "DatabaseDependency",
    "WeaviateSessionDependency",
    "close_postgres",
    "get_database",
    "get_session",
    "init_db",
    "init_postgres",
]
