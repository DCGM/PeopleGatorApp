"""Read-only PostgreSQL readiness and migration/schema compatibility checks."""

from __future__ import annotations

import asyncio
import logging
import warnings
from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from asyncpg.exceptions import CannotConnectNowError, PostgresConnectionError
from sqlalchemy import Connection, Index, MetaData, text, inspect
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.schema import SchemaItem

from people_gator_api.persistence.postgres.models import (
    Base,
    INDEX_NAME_PREFIX,
    TABLE_NAME_PREFIX,
)

logger = logging.getLogger(__name__)


class SchemaValidationError(RuntimeError):
    """The database is unavailable or incompatible with this application."""


def migration_config() -> Config:
    # Production images must include alembic.ini and the migration directory.
    return Config(str(Path("alembic.ini").resolve()))


def include_object(
    schema_item: SchemaItem,
    name: str | None,
    type_: str,
    reflected: bool,
    compare_to: SchemaItem | None,
) -> bool:
    """Model registration owns its per-model HNSW indexes, not Alembic."""
    return not (
        type_ == "index"
        and isinstance(schema_item, Index)
        and name is not None
        and name.startswith(INDEX_NAME_PREFIX)
        and name.endswith("_hnsw")
        and schema_item.table is not None
        and schema_item.table.name == "pg_demo_face_embeddings"
    )


def _include_name(
    name: str | None, type_: str, parent_names: dict[str, str | None],
) -> bool:
    # Other applications and extensions may own tables in the same database.
    return type_ != "table" or (
        name is not None and name.startswith(TABLE_NAME_PREFIX)
    )


def validate_schema(
    connection: Connection, *, check_revision: bool = True, metadata: MetaData | None = None,
) -> None:
    """Reject incompatible migration history and structural drift without DDL.

    Alembic detects table/column/type/nullability, foreign key, unique constraint
    and static index changes. It does not comprehensively compare CHECK/primary
    key constraints or arbitrary functions; migration tests remain necessary.
    """
    context = MigrationContext.configure(connection, opts={
        "compare_type": True,
        "include_object": include_object,
        "include_name": _include_name,
    })
    if check_revision:
        expected = set(ScriptDirectory.from_config(migration_config()).get_heads())
        current = set(context.get_current_heads())
        if not expected or current != expected:
            raise SchemaValidationError(
                f"Database revisions {sorted(current)} do not match application "
                + f"revisions {sorted(expected)}. Run the deployment migration job."
            )

    installed = set(connection.execute(text(
        "SELECT extname FROM pg_extension"
    )).scalars())
    missing = {"vector", "pg_trgm", "unaccent"} - installed
    if missing:
        raise SchemaValidationError(f"Missing PostgreSQL extensions: {sorted(missing)}")
    if connection.execute(text(
        "SELECT to_regprocedure('demo_unaccent(text)')"
    )).scalar_one() is None:
        raise SchemaValidationError("Missing demo_unaccent(text) function")
    if connection.execute(text(
        "SELECT demo_unaccent('Příliš')"
    )).scalar_one() != "Prilis":
        raise SchemaValidationError("demo_unaccent(text) returned an unexpected result")

    expected_metadata = Base.metadata if metadata is None else metadata
    if "last_touched_at" in expected_metadata.tables["pg_demo_sources"].c:
        # Alembic does not compare CHECK constraints. Verify source metadata remains
        # an all-null history or a complete time/user pair with an optional key.
        constraint = next((item for item in inspect(connection).get_check_constraints("pg_demo_sources") if item["name"] == "ck_pg_demo_sources_touch"), None)
        expected = "(last_touched_at IS NULL AND last_touched_by_user_id IS NULL AND last_touched_by_api_key_id IS NULL) OR (last_touched_at IS NOT NULL AND last_touched_by_user_id IS NOT NULL)"
        def normalized(value: str) -> str:
            return "".join(value.lower().split()).replace("(", "").replace(")", "")
        if constraint is None or normalized(constraint["sqltext"]) != normalized(expected):
            raise SchemaValidationError("Missing or incompatible source touch consistency constraint")

    if "thumbnail_face_id" in expected_metadata.tables["pg_demo_entities"].c:
        required = {
            ("pg_demo_entities", "select_thumbnail"),
            ("pg_demo_faces", "thumbnail_face_insert"),
            ("pg_demo_image_occurrences", "thumbnail_reassignment"),
        }
        installed = set(connection.execute(text("""
            SELECT c.relname, t.tgname FROM pg_trigger t
            JOIN pg_class c ON c.oid = t.tgrelid
            WHERE c.oid IN (to_regclass('pg_demo_entities'), to_regclass('pg_demo_faces'),
                            to_regclass('pg_demo_image_occurrences'))
              AND NOT t.tgisinternal AND t.tgenabled IN ('O', 'A')
        """)).all())
        if not required <= installed:
            raise SchemaValidationError("Missing or disabled person thumbnail lifecycle triggers")
        checks = {c["name"] for c in inspect(connection).get_check_constraints("pg_demo_entities")}
        if not {"ck_pg_demo_entities_thumbnail_mode", "ck_pg_demo_entities_manual_thumbnail",
                "ck_pg_demo_entities_person_thumbnail"} <= checks:
            raise SchemaValidationError("Missing person thumbnail consistency constraints")

    # Alembic reports unsupported generated-column changes as warnings. Treat
    # these as failures rather than accepting a mismatched generated expression.
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        try:
            differences = compare_metadata(context, Base.metadata if metadata is None else metadata)
        except UserWarning as exc:
            raise SchemaValidationError(f"Schema comparison failed: {exc}") from exc
    if differences:
        raise SchemaValidationError(
            f"Database schema differs from application models: {differences!r}. "
            + "Apply a reviewed migration before starting the API."
        )


async def wait_for_postgres(
    engine: AsyncEngine, *, timeout_seconds: float, retry_interval_seconds: float,
) -> None:
    """Retry transient connectivity failures, with a bounded overall deadline."""
    try:
        async with asyncio.timeout(timeout_seconds):
            while True:
                try:
                    async with engine.connect() as connection:
                        await connection.execute(text("SELECT 1"))
                    return
                except DBAPIError as exc:
                    sqlstate = getattr(exc.orig, "sqlstate", "") or ""
                    if not (
                        exc.connection_invalidated
                        or sqlstate.startswith("08")
                        or sqlstate == "57P03"
                    ):
                        raise
                except (OSError, PostgresConnectionError, CannotConnectNowError):
                    pass
                logger.warning("PostgreSQL is unavailable; retrying connection")
                await asyncio.sleep(retry_interval_seconds)
    except TimeoutError as exc:
        raise SchemaValidationError(
            f"PostgreSQL did not become reachable within {timeout_seconds:g} seconds"
        ) from exc


async def validate_postgres_schema(
    engine: AsyncEngine, *, check_revision: bool = True,
) -> None:
    async with engine.connect() as connection:
        async with connection.begin():
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            await connection.run_sync(
                lambda sync_connection: validate_schema(
                    sync_connection, check_revision=check_revision,
                )
            )
    logger.info("PostgreSQL schema validation passed")
