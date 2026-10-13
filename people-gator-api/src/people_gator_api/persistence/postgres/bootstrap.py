"""Validate and adopt schemas previously created outside Alembic.

The reference schemas come from frozen migration operations, never today's ORM
models. Only a complete, matching snapshot may advance the revision marker.
"""

from __future__ import annotations

import logging
import re
from types import FunctionType
from typing import Any

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, ForeignKeyConstraint, Index, MetaData, Table, inspect
from sqlalchemy.schema import CheckConstraint, Column, SchemaItem

from .schema import SchemaValidationError, validate_schema

logger = logging.getLogger(__name__)

# These known revisions contain declarative schema operations only. Future data
# migrations must run normally; do not automatically adopt arbitrary revisions.
SNAPSHOT_REVISIONS = ("c82e7f4a901d", "d34a021b0001", "d34a021b0002", "d34a021b0003")
LEGACY_REVISIONS = ("9897af156aa1", "65c4e6cdfa7f")


class _SnapshotOperations:
    """Collect the frozen revisions' table/index/constraint definitions without DDL."""

    def __init__(self) -> None:
        super().__init__()
        self.metadata = MetaData()

    def f(self, name: str) -> str:
        return name

    def create_table(self, name: str, *items: SchemaItem) -> Table:
        return Table(name, self.metadata, *items)

    def create_index(
        self, name: str, table_name: str, columns: list[str], **kwargs: Any
    ) -> None:
        table = self.metadata.tables[table_name]
        Index(name, *(table.c[column] for column in columns), **kwargs)

    def add_column(self, table_name: str, column: Column[Any]) -> None:
        self.metadata.tables[table_name].append_column(column)

    def create_foreign_key(
        self,
        name: str,
        source: str,
        target: str,
        local: list[str],
        remote: list[str],
        **kwargs: Any,
    ) -> None:
        constraint = ForeignKeyConstraint(
            local, [f"{target}.{column}" for column in remote], name=name, **kwargs
        )
        self.metadata.tables[source].append_constraint(constraint)


def frozen_schemas(config: Config) -> list[tuple[str, MetaData]]:
    scripts = ScriptDirectory.from_config(config)
    operations = _SnapshotOperations()
    snapshots: list[tuple[str, MetaData]] = []
    for revision in SNAPSHOT_REVISIONS:
        script = scripts.get_revision(revision)
        module = script.module
        # Execute trusted schema definitions with a private operations collector.
        # No module globals are patched and no live migration operations run here.
        upgrade = FunctionType(
            module.upgrade.__code__, {**vars(module), "op": operations}
        )
        upgrade()
        metadata = MetaData()
        for table in operations.metadata.sorted_tables:
            table.to_metadata(metadata)
        snapshots.append((revision, metadata))
    return snapshots


def _validate_constraints(connection: Connection, metadata: MetaData) -> None:
    inspector = inspect(connection)
    for table in metadata.sorted_tables:
        expected_pk = [column.name for column in table.primary_key.columns]
        if (
            inspector.get_pk_constraint(table.name)["constrained_columns"]
            != expected_pk
        ):
            raise SchemaValidationError(f"Primary key differs on {table.name}")

        # The known snapshots use simple integer comparisons and conjunctions.
        # PostgreSQL adds parentheses/whitespace when reflecting these checks.
        def normalized(expression: str) -> str:
            return re.sub(r"[\s()]", "", expression).lower()

        expected_checks = {
            str(item.name): normalized(str(item.sqltext))
            for item in table.constraints
            if isinstance(item, CheckConstraint)
        }
        actual_checks = {
            str(item["name"]): normalized(item["sqltext"])
            for item in inspector.get_check_constraints(table.name)
        }
        if actual_checks != expected_checks:
            raise SchemaValidationError(f"Check constraints differ on {table.name}")


def matching_bootstrap_revision(connection: Connection, config: Config) -> str | None:
    """Read-only match against known snapshots without changing migration history."""
    current = MigrationContext.configure(connection).get_current_heads()
    if len(current) > 1 or any(
        revision not in (*LEGACY_REVISIONS, *SNAPSHOT_REVISIONS) for revision in current
    ):
        raise SchemaValidationError(f"Cannot adopt unknown migration history {current}")
    tables = inspect(connection).get_table_names()
    if not any(name.startswith("pg_demo_") for name in tables):
        return None  # A genuinely fresh database should run the normal migrations.
    current_position = (
        SNAPSHOT_REVISIONS.index(current[0])
        if current and current[0] in SNAPSHOT_REVISIONS
        else -1
    )
    last_error = None
    for position, (revision, metadata) in reversed(
        list(enumerate(frozen_schemas(config)))
    ):
        if position < current_position:
            continue
        try:
            validate_schema(connection, check_revision=False, metadata=metadata)
            _validate_constraints(connection, metadata)
        except SchemaValidationError as exc:
            last_error = exc
            continue
        return revision
    raise SchemaValidationError(
        "Existing schema does not match a complete frozen migration snapshot; "
        + "refusing to change its revision. "
        + str(last_error)
    )


def adopt_bootstrap_schema(connection: Connection, config: Config) -> str | None:
    """Adopt a matching snapshot in the caller's migration transaction."""
    revision = matching_bootstrap_revision(connection, config)
    if revision is not None and MigrationContext.configure(
        connection
    ).get_current_heads() != (revision,):
        command.stamp(config, revision)
        logger.info("Adopted verified existing schema at revision %s", revision)
    return revision
