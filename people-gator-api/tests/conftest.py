"""Provide deterministic settings and isolate tests from import-time env changes."""

import json
import os
from contextlib import ExitStack

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


WORKER_STORES = pytest.StashKey[ExitStack]()
DATABASE_URL_VARIABLES = ("PEOPLE_GATOR_POSTGRES_TEST_URL", "PEOPLE_GATOR_SCHEMA_TEST_URL")


def pytest_configure(config: pytest.Config) -> None:
    worker = getattr(config, "workerinput", None)
    if worker is None:
        config.stash[WORKER_STORES] = ExitStack()
        if config.getoption("numprocesses", default=0) and any(
            os.getenv(name) for name in (
                "PEOPLE_GATOR_WEAVIATE_TEST_HTTP_PORT", "PEOPLE_GATOR_WEAVIATE_TEST_GRPC_PORT",
            )
        ):
            raise pytest.UsageError("Run live Weaviate tests sequentially (-n 0)")
        return

    # This runs before test-module collection (which snapshots integration URLs).
    urls = worker["people_gator_database_urls"]
    os.environ.update(urls)
    repository_url = urls.get("PEOPLE_GATOR_POSTGRES_TEST_URL")
    if repository_url:
        from sqlalchemy.engine import make_url
        from people_gator_api.settings import PersistenceSettings, settings

        url = make_url(repository_url)
        settings.persistence = PersistenceSettings(postgres={
            "host": url.host, "port": url.port, "user": url.username,
            "password": url.password, "database": url.database,
        })
        # Nested CI env overrides must not send application connections back to
        # the controller's database. Keep the autouse settings snapshot in sync.
        for name in list(os.environ):
            if name.startswith("PEOPLE_GATOR_API__PERSISTENCE"):
                del os.environ[name]
                SETTINGS_ENVIRONMENT.pop(name, None)
        value = settings.persistence.model_dump_json()
        os.environ["PEOPLE_GATOR_API__PERSISTENCE"] = value
        SETTINGS_ENVIRONMENT["PEOPLE_GATOR_API__PERSISTENCE"] = value


@pytest.hookimpl(optionalhook=True)
def pytest_configure_node(node) -> None:
    from postgres_workers import worker_databases

    urls = {name: os.environ[name] for name in DATABASE_URL_VARIABLES if os.getenv(name)}
    node.workerinput["people_gator_database_urls"] = node.config.stash[WORKER_STORES].enter_context(
        worker_databases(urls)
    )


def pytest_unconfigure(config: pytest.Config) -> None:
    if WORKER_STORES in config.stash:
        config.stash[WORKER_STORES].close()


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
