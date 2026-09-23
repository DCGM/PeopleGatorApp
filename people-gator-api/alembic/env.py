from __future__ import annotations

import asyncio
from logging.config import fileConfig
from typing import Literal

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.engine import URL
from sqlalchemy.schema import Index, SchemaItem
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from people_gator_api.models import Base, INDEX_NAME_PREFIX
from people_gator_api.settings import settings


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def include_object(
    schema_item: SchemaItem,
    name: str | None,
    type_: Literal[
        "schema",
        "table",
        "column",
        "index",
        "unique_constraint",
        "foreign_key_constraint",
        "check_constraint",
    ],
    reflected: bool,
    compare_to: SchemaItem | None,
) -> bool:
    """Keep model-specific HNSW indexes outside Alembic ownership."""
    if (
        type_ == "index"
        and reflected
        and isinstance(schema_item, Index)
        and name is not None
        and schema_item.table is not None
        and name.startswith(INDEX_NAME_PREFIX)
        and name.endswith("_hnsw")
        and schema_item.table.name == "pg_demo_face_embeddings"
    ):
        return False
    return True


def postgres_url() -> URL:
    postgres = settings.persistence.postgres
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
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()