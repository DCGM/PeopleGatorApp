"""Request-scoped database dependencies.

API persistence is exposed through the backend-neutral Database contract.
This module owns the process-wide lifecycle of both database backends.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Annotated

if TYPE_CHECKING:
    from weaviate import WeaviateAsyncClient

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
from people_gator_api.persistence.postgres.models import Base

from people_gator_api.settings import settings
from people_gator_api.utils.opentelemetry import instrument_sqlalchemy_engine


logger = logging.getLogger(__name__)

_weaviate_client: WeaviateAsyncClient | None = None
_postgres_engine: AsyncEngine | None = None
_postgres_sessions: async_sessionmaker[AsyncSession] | None = None


def postgres_url() -> URL:
    config = settings.persistence.postgres
    if config is None:
        raise ValueError("PostgreSQL requires persistence.postgres configuration")
    return URL.create(
        drivername="postgresql+asyncpg",
        username=config.user,
        password=config.password,
        host=config.host,
        port=config.port,
        database=config.database,
    )


def make_postgres_engine(database_url: URL, *, echo: bool = False) -> AsyncEngine:
    """Build an asyncpg engine for the isolated demo database."""
    if database_url.drivername != "postgresql+asyncpg":
        raise ValueError("database_url must use the postgresql+asyncpg driver")

    engine = create_async_engine(database_url, echo=echo, pool_pre_ping=True)
    if settings.otel.enabled:
        # The SQLAlchemy instrumentor needs the sync facade of an async engine.
        # This creates parent SQL spans around the asyncpg driver spans.
        instrument_sqlalchemy_engine(engine)
    return engine


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
        postgres_url(),
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


async def init_weaviate() -> None:
    """Connect the async Weaviate client and ensure collection schemas exist.

    Call once during application startup (e.g. from FastAPI lifespan).
    """
    from people_gator_api.persistence.weaviate.client import (
        build_weaviate_client,
        ensure_collections,
    )

    global _weaviate_client  # noqa: PLW0603
    if _weaviate_client is not None:
        return

    cfg = settings.persistence.weaviate
    if cfg is None:
        raise ValueError("Weaviate requires persistence.weaviate configuration")
    deadline = time.monotonic() + cfg.startup_timeout_seconds
    attempt = 0
    while True:
        attempt += 1
        candidate = build_weaviate_client()
        try:
            await candidate.connect()
            await ensure_collections(candidate)
        except Exception as exc:
            # A failed connect can still allocate HTTP/gRPC resources. Close
            # the whole candidate and build a fresh client for the next try.
            await candidate.close()
            remaining_seconds = deadline - time.monotonic()
            if remaining_seconds <= 0:
                logger.error(
                    "Unable to initialise Weaviate within %.1f seconds",
                    cfg.startup_timeout_seconds,
                )
                raise
            delay_seconds = min(
                cfg.startup_retry_interval_seconds,
                remaining_seconds,
            )
            logger.warning(
                "Weaviate is not ready (attempt %s); retrying in %.1f seconds: %s",
                attempt,
                delay_seconds,
                exc,
            )
            await asyncio.sleep(delay_seconds)
            continue

        _weaviate_client = candidate
        logger.info(
            "Weaviate client connected and schema is ready",
            extra={
                "http_host": cfg.http_host,
                "http_port": cfg.http_port,
                "attempt": attempt,
            },
        )
        return


async def close_weaviate() -> None:
    """Close the async Weaviate client.

    Call once during application shutdown (e.g. from FastAPI lifespan).
    """
    global _weaviate_client  # noqa: PLW0603
    if _weaviate_client is not None:
        await _weaviate_client.close()
        _weaviate_client = None
        logger.info("Weaviate client closed")


def get_weaviate_client() -> WeaviateAsyncClient:
    """Return the connected WeaviateAsyncClient.

    Raises RuntimeError if :func:`init_weaviate` has not been called.
    """
    if _weaviate_client is None:
        raise RuntimeError(
            "Weaviate client is not initialised.  "
            + "Ensure init_weaviate() has been awaited during startup."
        )
    return _weaviate_client


async def get_database() -> AsyncGenerator[Database, None]:
    """Yield a contract facade for the enabled persistence backend."""
    if settings.persistence.backend == "weaviate":
        from people_gator_api.persistence.weaviate import weaviate_database

        yield weaviate_database(get_weaviate_client())
        return

    if _postgres_sessions is None:
        await init_postgres()
    assert _postgres_sessions is not None
    async with _postgres_sessions() as session:
        yield postgres_database(session)


type DatabaseDependency = Annotated[Database, Depends(get_database)]


async def init_db() -> None:
    """Initialize the enabled persistence backend and its schema."""
    if settings.persistence.backend == "weaviate":
        await init_weaviate()
        return
    await init_postgres()
    assert _postgres_engine is not None
    config = settings.persistence.postgres
    assert config is not None
    if config.schema_mode == "bootstrap":
        await create_postgres_schema(_postgres_engine)
        return

    from people_gator_api.persistence.postgres.schema import (
        validate_postgres_schema,
        wait_for_postgres,
    )

    await wait_for_postgres(
        _postgres_engine,
        timeout_seconds=config.startup_timeout_seconds,
        retry_interval_seconds=config.startup_retry_interval_seconds,
    )
    await validate_postgres_schema(_postgres_engine)


async def close_db() -> None:
    """Release persistence resources initialized by the application."""
    await close_postgres()
    await close_weaviate()


__all__ = [
    "DatabaseDependency",
    "close_db",
    "close_postgres",
    "close_weaviate",
    "get_database",
    "get_weaviate_client",
    "init_db",
    "init_postgres",
    "init_weaviate",
]
