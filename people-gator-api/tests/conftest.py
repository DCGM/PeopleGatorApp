"""Provide deterministic settings and isolate tests from import-time env changes."""

import json
import os

import pytest
import pytest_asyncio


os.environ.setdefault("PEOPLE_GATOR_API__PERSISTENCE", json.dumps({
    "postgres": {
        "host": "localhost", "port": 5432, "user": "test",
        "password": "test", "database": "test",
    },
    "weaviate": None,
}))
os.environ.setdefault("PEOPLE_GATOR_API__STORAGE", json.dumps({
    "local": {"root": "/tmp/people-gator-tests"}, "s3": None,
}))
SETTINGS_ENVIRONMENT = {
    name: value for name, value in os.environ.items()
    if name.startswith("PEOPLE_GATOR_API__")
}

# Initialize settings before older media tests set their legacy environment
# defaults during collection. Each test receives the original environment below.
import people_gator_api.schemas  # noqa: E402, F401


@pytest.fixture(autouse=True)
def isolated_settings_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.startswith("PEOPLE_GATOR_API__"):
            monkeypatch.delenv(name)
    for name, value in SETTINGS_ENVIRONMENT.items():
        monkeypatch.setenv(name, value)


@pytest_asyncio.fixture
async def migrated_postgres():
    """A unique migrated schema on the explicitly disposable schema-test store."""
    import uuid

    from alembic import command
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from people_gator_api.persistence.postgres.schema import migration_config

    url = os.getenv("PEOPLE_GATOR_SCHEMA_TEST_URL")
    if not url:
        pytest.skip("requires a disposable schema test database")
    admin = create_async_engine(url)
    schema = "isolated_test_" + uuid.uuid4().hex
    async with admin.begin() as connection:
        for extension in ("vector", "pg_trgm", "unaccent"):
            await connection.execute(
                text(f"CREATE EXTENSION IF NOT EXISTS {extension} WITH SCHEMA public")
            )
        await connection.execute(text(f"CREATE SCHEMA {schema}"))
        # Hide any public Alembic version table left by other migration tests.
        await connection.execute(text(
            f"CREATE TABLE {schema}.alembic_version (version_num VARCHAR(32) PRIMARY KEY)"
        ))
    engine = create_async_engine(
        url, connect_args={"server_settings": {"search_path": schema + ",public"}}
    )
    try:
        def migrate(connection):
            config = migration_config()
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

        async with engine.begin() as connection:
            await connection.run_sync(migrate)
        yield engine
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        await admin.dispose()
