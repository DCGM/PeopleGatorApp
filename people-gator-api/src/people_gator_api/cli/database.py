"""Production PostgreSQL checks and one-shot deployment migrations."""

import argparse
import asyncio
import logging

from alembic import command
from sqlalchemy import Connection, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from people_gator_api.persistence.postgres.bootstrap import adopt_bootstrap_schema
from people_gator_api.persistence.postgres.schema import (
    migration_config,
    validate_postgres_schema,
    validate_schema,
    wait_for_postgres,
)
from people_gator_api.services.database_service import postgres_url
from people_gator_api.settings import settings


async def check_database(*, schema_only: bool = False, wait_only: bool = False) -> None:
    config = settings.persistence.postgres
    if settings.persistence.backend != "postgres" or config is None:
        raise ValueError("The production database commands require PostgreSQL")
    engine = create_async_engine(postgres_url(), poolclass=NullPool)
    try:
        await wait_for_postgres(
            engine,
            timeout_seconds=config.startup_timeout_seconds,
            retry_interval_seconds=config.startup_retry_interval_seconds,
        )
        if not wait_only:
            await validate_postgres_schema(engine, check_revision=not schema_only)
    finally:
        await engine.dispose()


async def migrate_database(*, adopt_bootstrap: bool = False) -> None:
    config = settings.persistence.postgres
    if settings.persistence.backend != "postgres" or config is None:
        raise ValueError("The production database commands require PostgreSQL")
    engine = create_async_engine(postgres_url(), poolclass=NullPool)
    try:
        await wait_for_postgres(
            engine,
            timeout_seconds=config.startup_timeout_seconds,
            retry_interval_seconds=config.startup_retry_interval_seconds,
        )
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "SELECT pg_advisory_xact_lock(hashtextextended('people-gator-migrations', 0))"
                )
            )

            def migrate(sync_connection: Connection) -> None:
                alembic_config = migration_config()
                alembic_config.attributes["connection"] = sync_connection
                if adopt_bootstrap:
                    adopt_bootstrap_schema(sync_connection, alembic_config)
                command.upgrade(alembic_config, "head")
                validate_schema(sync_connection)

            await connection.run_sync(migrate)
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("check", "migrate"))
    parser.add_argument(
        "--schema-only",
        action="store_true",
        help="Check the current application schema without revision history",
    )
    parser.add_argument(
        "--adopt-bootstrap",
        action="store_true",
        help="Validate and adopt an existing bootstrap schema before applying missing migrations",
    )
    args = parser.parse_args()
    if args.schema_only and args.action != "check":
        parser.error("--schema-only is only valid with check")
    if args.adopt_bootstrap and args.action != "migrate":
        parser.error("--adopt-bootstrap is only valid with migrate")
    logging.basicConfig(level=logging.INFO)
    if args.action == "migrate":
        asyncio.run(migrate_database(adopt_bootstrap=args.adopt_bootstrap))
    else:
        asyncio.run(check_database(schema_only=args.schema_only))


if __name__ == "__main__":
    main()
