from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from people_gator_api.persistence.postgres.models import Base
from people_gator_api.persistence.postgres.schema import include_object
from people_gator_api.settings import settings


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def postgres_url() -> URL:
    postgres = settings.persistence.postgres
    if postgres is None:
        raise ValueError("PostgreSQL migrations require persistence.postgres configuration")
    return URL.create(
        drivername="postgresql+asyncpg",
        username=postgres.user,
        password=postgres.password,
        host=postgres.host,
        port=postgres.port,
        database=postgres.database,
    )


def run_migrations_offline() -> None:
    """Run migrations without creating a database connection."""
    context.configure(
        url=postgres_url().render_as_string(hide_password=False),
        target_metadata=target_metadata,
        include_object=include_object,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable: AsyncEngine = create_async_engine(
        postgres_url(),
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations against the configured PostgreSQL database."""
    connection = config.attributes.get("connection")
    if connection is not None:
        do_run_migrations(connection)
    else:
        asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
