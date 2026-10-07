"""Run integration cases only against a disposable PEOPLE_GATOR_SCHEMA_TEST_URL."""

import asyncio
import os
from unittest.mock import AsyncMock, Mock

from alembic import command
from asyncpg.exceptions import CannotConnectNowError, InvalidPasswordError
import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from people_gator_api.persistence.postgres.schema import (
    SchemaValidationError,
    migration_config,
    validate_postgres_schema,
    validate_schema,
    wait_for_postgres,
)
from people_gator_api.services import database_service
from people_gator_api.settings import PersistenceSettings, settings


@pytest.mark.asyncio
async def test_validate_mode_does_not_bootstrap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "persistence", PersistenceSettings(postgres={
        "host": "localhost", "port": 5432, "user": "test", "password": "test",
        "database": "test", "schema_mode": "validate",
    }))
    monkeypatch.setattr(database_service, "init_postgres", AsyncMock())
    engine = object()
    monkeypatch.setattr(database_service, "_postgres_engine", engine)
    create_schema = AsyncMock()
    monkeypatch.setattr(database_service, "create_postgres_schema", create_schema)
    from people_gator_api.persistence.postgres import schema
    wait, validate = AsyncMock(), AsyncMock(side_effect=SchemaValidationError("drift"))
    monkeypatch.setattr(schema, "wait_for_postgres", wait)
    monkeypatch.setattr(schema, "validate_postgres_schema", validate)
    with pytest.raises(SchemaValidationError, match="drift"):
        await database_service.init_db()
    wait.assert_awaited_once()
    validate.assert_awaited_once_with(engine)
    create_schema.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [ConnectionRefusedError(), CannotConnectNowError()])
async def test_connection_retry_has_deadline(failure: Exception) -> None:
    engine = Mock()
    engine.connect.side_effect = failure
    with pytest.raises(SchemaValidationError, match="did not become reachable"):
        await wait_for_postgres(engine, timeout_seconds=0.03, retry_interval_seconds=0.01)
    assert engine.connect.call_count >= 2


@pytest.mark.asyncio
async def test_authentication_failure_is_not_retried() -> None:
    engine = Mock()
    engine.connect.side_effect = InvalidPasswordError()
    with pytest.raises(InvalidPasswordError):
        await wait_for_postgres(engine, timeout_seconds=1, retry_interval_seconds=0.01)
    assert engine.connect.call_count == 1


SCHEMA_TEST_URL = os.environ.get("PEOPLE_GATOR_SCHEMA_TEST_URL")


@pytest.mark.skipif(SCHEMA_TEST_URL is None, reason="requires disposable schema test DB")
@pytest.mark.asyncio
async def test_migration_and_read_only_schema_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    assert SCHEMA_TEST_URL is not None
    url = make_url(SCHEMA_TEST_URL)
    monkeypatch.setattr(settings, "persistence", PersistenceSettings(postgres={
        "host": url.host, "port": url.port, "user": url.username,
        "password": url.password, "database": url.database,
    }))
    engine = create_async_engine(url)
    try:
        # Verify an empty DB fails, even when it has a reachable server.
        with pytest.raises(SchemaValidationError, match="revisions"):
            await validate_postgres_schema(engine)
        await asyncio.to_thread(command.upgrade, migration_config(), "head")
        await validate_postgres_schema(engine)
        # Repeated migration deployments are safe.
        await asyncio.to_thread(command.upgrade, migration_config(), "head")

        async with engine.connect() as connection:
            async with connection.begin():
                await connection.execute(text("UPDATE alembic_version SET version_num = '65c4e6cdfa7f'"))
                with pytest.raises(SchemaValidationError, match="revisions"):
                    await connection.run_sync(validate_schema)
                await connection.run_sync(lambda sync: validate_schema(sync, check_revision=False))
                await connection.rollback()

            async with connection.begin():
                await connection.execute(text("ALTER TABLE pg_demo_users DROP COLUMN email"))
                with pytest.raises(SchemaValidationError, match="differs"):
                    await connection.run_sync(validate_schema)
                await connection.rollback()

            async with connection.begin():
                await connection.execute(text("DROP INDEX ix_pg_demo_users_is_active"))
                with pytest.raises(SchemaValidationError, match="differs"):
                    await connection.run_sync(validate_schema)
                await connection.rollback()

            async with connection.begin():
                await connection.execute(text("ALTER TABLE pg_demo_users ALTER COLUMN is_active DROP NOT NULL"))
                with pytest.raises(SchemaValidationError, match="differs"):
                    await connection.run_sync(validate_schema)
                await connection.rollback()

            async with connection.begin():
                await connection.execute(text("DROP EXTENSION pg_trgm CASCADE"))
                with pytest.raises(SchemaValidationError, match="Missing PostgreSQL extensions"):
                    await connection.run_sync(validate_schema)
                await connection.rollback()

            async with connection.begin():
                await connection.execute(text("DROP FUNCTION demo_unaccent(text) CASCADE"))
                with pytest.raises(SchemaValidationError, match="Missing demo_unaccent"):
                    await connection.run_sync(validate_schema)
                await connection.rollback()

            async with connection.begin():
                await connection.execute(text("CREATE INDEX ix_pg_demo_face_embedding_validation_3dim_hnsw ON pg_demo_face_embeddings USING hnsw ((embedding::vector(3)) vector_cosine_ops) WHERE model_id = 'schema-test'"))
                await connection.execute(text("CREATE TABLE unrelated_application_data (id integer)"))
                await connection.run_sync(validate_schema)
                await connection.rollback()

            # Runtime roles need no schema CREATE permission for validation.
            async with connection.begin():
                await connection.execute(text("CREATE ROLE schema_runtime_test"))
                await connection.execute(text("GRANT USAGE ON SCHEMA public TO schema_runtime_test"))
                await connection.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO schema_runtime_test"))
                await connection.execute(text("SET LOCAL ROLE schema_runtime_test"))
                await connection.execute(text("SET TRANSACTION READ ONLY"))
                await connection.run_sync(validate_schema)
                await connection.rollback()

        await validate_postgres_schema(engine)
    finally:
        await engine.dispose()
