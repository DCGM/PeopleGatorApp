import logging
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from people_gator_api.settings import settings
from people_gator_api.models import Base

logger = logging.getLogger(__name__)


def build_async_engine() -> AsyncEngine:
    url = (
        f"postgresql+asyncpg://{settings.postgres.user}:{settings.postgres.password}"
        f"@{settings.postgres.host}:{settings.postgres.port}/{settings.postgres.database}"
    )
    engine = create_async_engine(
        url,
        echo=settings.debug,
        pool_pre_ping=True,
    )
    logger.info(
        "Async SQLAlchemy engine created",
        extra={
            "db_host": settings.postgres.host,
            "db_port": settings.postgres.port,
            "db_name": settings.postgres.database,
            "db_user": settings.postgres.user,
        },
    )
    return engine


engine: AsyncEngine = build_async_engine()

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a managed async session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Initialize database tables from SQLAlchemy metadata."""
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
