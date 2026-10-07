"""Production PostgreSQL checks and one-shot deployment migrations."""

import argparse
import asyncio
import logging

from alembic import command
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from people_gator_api.persistence.postgres.schema import (
    migration_config,
    validate_postgres_schema,
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("check", "migrate"))
    parser.add_argument(
        "--schema-only", action="store_true",
        help="Check structure without revision history, before adopting an existing DB",
    )
    args = parser.parse_args()
    if args.schema_only and args.action != "check":
        parser.error("--schema-only is only valid with check")
    logging.basicConfig(level=logging.INFO)
    asyncio.run(check_database(schema_only=args.schema_only, wait_only=args.action == "migrate"))
    if args.action == "migrate":
        command.upgrade(migration_config(), "head")
        asyncio.run(check_database())


if __name__ == "__main__":
    main()
