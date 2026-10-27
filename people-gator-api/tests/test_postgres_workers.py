"""Protect worker allocation/cleanup without requiring a live service."""

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

import postgres_workers


URLS = {
    "PEOPLE_GATOR_POSTGRES_TEST_URL": "postgresql+asyncpg://test:test@localhost/repository",
    "PEOPLE_GATOR_SCHEMA_TEST_URL": "postgresql+asyncpg://test:test@localhost/schema_tests",
}


@pytest.mark.parametrize("iteration", range(2))
def test_model_indexes_do_not_leak_between_cases(iteration):
    from people_gator_api.persistence.postgres.models import FaceEmbedding, face_embedding_hnsw_index

    indexes = FaceEmbedding.__table__.indexes
    assert not any(index.info.get("worker_isolation_probe") for index in indexes)
    index = face_embedding_hnsw_index("worker-isolation-probe", 3)
    index.info["worker_isolation_probe"] = True
    assert index in indexes


@pytest.mark.parametrize("variable", URLS)
def test_worker_settings_replace_nested_controller_overrides(monkeypatch, variable):
    import conftest
    from people_gator_api.settings import Settings, settings

    monkeypatch.setattr(conftest, "SETTINGS_ENVIRONMENT", dict(conftest.SETTINGS_ENVIRONMENT))
    monkeypatch.setattr(settings, "persistence", settings.persistence)
    monkeypatch.setenv("PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__DATABASE", "controller_store")
    config = SimpleNamespace(workerinput={
        "people_gator_database_urls": {variable: "postgresql+asyncpg://test:test@localhost/private_worker"},
    })
    conftest.pytest_configure(config)
    assert settings.persistence.postgres.database == "private_worker"
    assert settings.persistence.postgres.port == 5432
    assert Settings(_env_file=None).persistence.postgres.database == "private_worker"
    assert "PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__DATABASE" not in os.environ
    assert conftest.SETTINGS_ENVIRONMENT["PEOPLE_GATOR_API__PERSISTENCE"] == os.environ["PEOPLE_GATOR_API__PERSISTENCE"]


def test_parallel_live_weaviate_is_rejected(monkeypatch):
    import conftest

    monkeypatch.setenv("PEOPLE_GATOR_WEAVIATE_TEST_HTTP_PORT", "8080")
    config = SimpleNamespace(stash={}, getoption=lambda *args, **kwargs: 2)
    with pytest.raises(pytest.UsageError, match="sequentially"):
        conftest.pytest_configure(config)
    conftest.pytest_unconfigure(config)


def test_workers_and_store_types_receive_distinct_databases(monkeypatch):
    execute = AsyncMock()
    monkeypatch.setattr(postgres_workers, "database_command", execute)
    with postgres_workers.worker_databases(URLS) as first:
        with postgres_workers.worker_databases(URLS) as second:
            names = [make_url(url).database for urls in (first, second) for url in urls.values()]
            assert len(set(names)) == 4
            for variable, original in URLS.items():
                assert make_url(first[variable]).set(database=make_url(original).database) == make_url(original)
            assert execute.await_count == 4  # Both workers remain alive.
        assert execute.await_count == 6
    statements = [call.args[1] for call in execute.await_args_list]
    for name in names:
        assert statements.count(f'CREATE DATABASE "{name}"') == 1
        assert statements.count(f'DROP DATABASE "{name}" WITH (FORCE)') == 1


def test_failed_partial_allocation_cleans_only_created_database(monkeypatch):
    execute = AsyncMock(side_effect=[None, RuntimeError("create denied"), None])
    monkeypatch.setattr(postgres_workers, "database_command", execute)
    with pytest.raises(RuntimeError, match="create denied"):
        with postgres_workers.worker_databases(URLS):
            pytest.fail("An incompletely provisioned worker must not start")
    create, failed, drop = [call.args[1] for call in execute.await_args_list]
    assert drop == create.replace("CREATE", "DROP") + " WITH (FORCE)"
    assert failed.split('"')[1] not in drop


def test_worker_failure_still_removes_both_databases(monkeypatch):
    execute = AsyncMock()
    monkeypatch.setattr(postgres_workers, "database_command", execute)
    with pytest.raises(RuntimeError, match="worker crashed"):
        with postgres_workers.worker_databases(URLS):
            raise RuntimeError("worker crashed")
    assert execute.await_count == 4


def test_cleanup_attempts_every_database_even_when_one_drop_fails(monkeypatch):
    execute = AsyncMock(side_effect=[None, None, RuntimeError("drop denied"), None])
    monkeypatch.setattr(postgres_workers, "database_command", execute)
    with pytest.raises(ExceptionGroup, match="private pytest databases"):
        with postgres_workers.worker_databases(URLS):
            pass
    assert execute.await_count == 4


@pytest.mark.skipif(
    not os.getenv("PEOPLE_GATOR_SCHEMA_TEST_URL"), reason="requires disposable schema test DB",
)
def test_real_worker_stores_isolate_commits_and_ddl_and_are_removed():
    original = os.environ["PEOPLE_GATOR_SCHEMA_TEST_URL"]

    async def query(url, sql):
        engine = create_async_engine(url)
        try:
            async with engine.begin() as connection:
                return (await connection.execute(text(sql))).scalar()
        finally:
            await engine.dispose()

    with postgres_workers.worker_databases({"first": original, "second": original}) as urls:
        for key, value in (("first", 1), ("second", 2)):
            asyncio.run(postgres_workers.database_command(
                urls[key], "CREATE TABLE worker_isolation_probe (id integer PRIMARY KEY)",
            ))
            asyncio.run(postgres_workers.database_command(
                urls[key], f"INSERT INTO worker_isolation_probe VALUES ({value})",
            ))
        # Fresh connections observe real commits, with no outer rollback fixture.
        assert asyncio.run(query(urls["first"], "SELECT id FROM worker_isolation_probe")) == 1
        assert asyncio.run(query(urls["second"], "SELECT id FROM worker_isolation_probe")) == 2
        asyncio.run(postgres_workers.database_command(urls["first"], "DROP TABLE worker_isolation_probe"))
        assert asyncio.run(query(urls["second"], "SELECT id FROM worker_isolation_probe")) == 2
        assert asyncio.run(query(original, "SELECT to_regclass('worker_isolation_probe')")) is None
        names = [make_url(url).database for url in urls.values()]
    for name in names:
        assert asyncio.run(query(original, f"SELECT count(*) FROM pg_database WHERE datname = '{name}'")) == 0
