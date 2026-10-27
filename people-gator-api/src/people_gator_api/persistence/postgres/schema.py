"""Read-only PostgreSQL readiness and migration/schema compatibility checks."""

from __future__ import annotations

import asyncio
import logging
import re
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
from people_gator_api.persistence.postgres.thumbnail_ddl import THUMBNAIL_DDL

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
        _validate_thumbnail_invariants(connection)

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


def _canonical_sql(value: str) -> str:
    # Reflection qualifies objects outside search_path and DDL may use OR REPLACE.
    value = re.sub(r"\b\w+\.(?=pg_demo_)", "", value.replace("OR REPLACE ", ""))
    return " ".join(value.split())


def _validate_thumbnail_invariants(connection: Connection) -> None:
    """Compare portrait triggers, functions and checks with the current DDL.

    Names alone are insufficient: a trigger with the wrong level or timing, or
    a function body from another revision, fails only when data changes.
    """
    expected_triggers: dict[str, str] = {}
    expected_functions: dict[str, str] = {}
    for statement in THUMBNAIL_DDL:
        if function := re.match(r"CREATE OR REPLACE FUNCTION (\w+)\(.*?\$\$(.*)\$\$", statement, re.S):
            expected_functions[function[1]] = _canonical_sql(function[2])
        else:
            trigger = re.match(r"CREATE OR REPLACE TRIGGER (\w+)", statement)
            assert trigger is not None
            expected_triggers[trigger[1]] = _canonical_sql(statement)

    triggers = dict(connection.execute(text("""
        SELECT t.tgname, pg_get_triggerdef(t.oid) FROM pg_trigger t
        WHERE t.tgrelid IN (to_regclass('pg_demo_entities'), to_regclass('pg_demo_faces'),
                            to_regclass('pg_demo_image_occurrences'))
          AND t.tgname = ANY(:names) AND NOT t.tgisinternal AND t.tgenabled IN ('O', 'A')
    """), {"names": list(expected_triggers)}).all())
    for name, expected in expected_triggers.items():
        if name not in triggers:
            raise SchemaValidationError(f"Missing or disabled person thumbnail lifecycle trigger: {name}")
        if _canonical_sql(triggers[name]) != expected:
            raise SchemaValidationError(f"Incompatible person thumbnail lifecycle trigger: {name}")

    functions: dict[str, list[str]] = {}
    for name, source in connection.execute(text("""
        SELECT p.proname, p.prosrc FROM pg_proc p
        WHERE p.proname = ANY(:names) AND pg_function_is_visible(p.oid)
    """), {"names": list(expected_functions)}).all():
        functions.setdefault(name, []).append(_canonical_sql(source))
    for name, expected in expected_functions.items():
        if functions.get(name) != [expected]:
            raise SchemaValidationError(f"Missing or incompatible person thumbnail function: {name}")

    # PostgreSQL rewrites IN to ANY/ARRAY, inserts casts and parenthesizes every
    # operand. Drop casts and parentheses around bare names only; the remaining
    # parentheses keep boolean grouping, so regrouped checks do not compare equal.
    def normalized_check(value: str) -> str:
        for cast in ("::character varying", "::text[]", "::text"):
            value = value.replace(cast, "")
        value = re.sub(r"\((\w+)\)", r"\1", value)
        return "".join(value.lower().split())

    # The inspector reflects pretty-printed checks; request PostgreSQL's fully
    # parenthesized form so grouping is explicit and stable.
    checks = dict(connection.execute(text("""
        SELECT conname, pg_get_constraintdef(oid, false) FROM pg_constraint
        WHERE conrelid = to_regclass('pg_demo_entities') AND contype = 'c'
    """)).all())
    expected_checks = {
        "ck_pg_demo_entities_thumbnail_mode": (
            "(thumbnail_mode = ANY ((ARRAY['automatic', 'manual'])))",
            # pg_dump/restore reparses the array's text[] coercion into text
            # casts on its elements. Accept this exact equivalent spelling;
            # keep boolean grouping and the permitted values checked strictly.
            "(thumbnail_mode = ANY (ARRAY[('automatic'), ('manual')]))",
        ),
        "ck_pg_demo_entities_manual_thumbnail": (
            "((thumbnail_mode <> 'manual') OR (thumbnail_face_id IS NOT NULL))",
        ),
        "ck_pg_demo_entities_person_thumbnail": (
            "((kind = 'person') OR ((thumbnail_face_id IS NULL) AND (thumbnail_mode = 'automatic')))",
        ),
    }
    for name, alternatives in expected_checks.items():
        if name not in checks or not any(
            normalized_check(checks[name]) == normalized_check(f"CHECK ({expected})")
            for expected in alternatives
        ):
            raise SchemaValidationError(f"Missing or incompatible person thumbnail consistency constraint: {name}")


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
