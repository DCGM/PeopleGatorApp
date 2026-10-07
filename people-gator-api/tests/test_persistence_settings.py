import json
import os
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError

from people_gator_api.settings import (
    PersistenceBaseSetting, PersistenceSettings, Settings, settings,
)
from people_gator_api.services import database_service
from people_gator_api.persistence import weaviate


POSTGRES = {
    "host": "localhost", "port": 5432, "user": "test",
    "password": "test", "database": "test",
}
WEAVIATE = {
    "http_host": "localhost", "http_port": 8080, "http_secure": False,
    "grpc_host": "localhost", "grpc_port": 50051, "grpc_secure": False,
}


@pytest.mark.parametrize("backend,connection", [("postgres", POSTGRES), ("weaviate", WEAVIATE)])
@pytest.mark.parametrize("explicit_null", [False, True], ids=["omitted", "null"])
def test_non_null_configuration_selects_backend(
    backend: str, connection: dict[str, Any], explicit_null: bool,
) -> None:
    other = "weaviate" if backend == "postgres" else "postgres"
    data: dict[str, Any] = {backend: connection}
    if explicit_null:
        data[other] = None
    config = PersistenceSettings.model_validate(data)
    assert config.backend == backend
    assert getattr(config, other) is None
    selected = getattr(config, backend)
    assert isinstance(selected, PersistenceBaseSetting)
    assert "enabled" not in selected.model_dump()
    assert PersistenceSettings.model_validate_json(config.model_dump_json()) == config


@pytest.mark.parametrize("data", [
    {}, {"postgres": None}, {"weaviate": None},
    {"postgres": None, "weaviate": None},
    {"postgres": POSTGRES, "weaviate": WEAVIATE},
], ids=["omitted", "postgres-null", "weaviate-null", "both-null", "both-set"])
def test_requires_exactly_one_backend(data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError, match="Exactly one persistence backend must be set"):
        PersistenceSettings.model_validate(data)


@pytest.mark.parametrize("backend,connection", [("postgres", POSTGRES), ("weaviate", WEAVIATE)])
def test_non_null_backend_requires_connection_fields(
    backend: str, connection: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError) as empty:
        PersistenceSettings.model_validate({backend: {}})
    assert all(error["type"] == "missing" for error in empty.value.errors())
    for field in connection:
        incomplete = {key: value for key, value in connection.items() if key != field}
        with pytest.raises(ValidationError) as missing:
            PersistenceSettings.model_validate({backend: incomplete})
        assert missing.value.errors()[0]["loc"] == (backend, field)
        assert missing.value.errors()[0]["type"] == "missing"


@pytest.fixture
def clean_settings_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.startswith("PEOPLE_GATOR_API__"):
            monkeypatch.delenv(name)


@pytest.mark.usefixtures("clean_settings_environment")
@pytest.mark.parametrize("backend,connection", [("postgres", POSTGRES), ("weaviate", WEAVIATE)])
@pytest.mark.parametrize("source", ["nested", "json"])
def test_environment_selects_non_null_backend(
    backend: str, connection: dict[str, Any], source: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    other = "weaviate" if backend == "postgres" else "postgres"
    if source == "json":
        monkeypatch.setenv("PEOPLE_GATOR_API__PERSISTENCE", json.dumps({backend: connection, other: None}))
    else:
        for name, value in connection.items():
            monkeypatch.setenv(f"PEOPLE_GATOR_API__PERSISTENCE__{backend.upper()}__{name.upper()}", str(value))
    configured = Settings(_env_file=None, storage={"local": {}})
    assert configured.persistence.backend == backend
    assert getattr(configured.persistence, other) is None
    assert getattr(configured.persistence, backend).model_dump(include=set(connection)) == connection


@pytest.mark.usefixtures("clean_settings_environment")
def test_environment_rejects_two_configured_backends(monkeypatch: pytest.MonkeyPatch) -> None:
    for backend, connection in [("postgres", POSTGRES), ("weaviate", WEAVIATE)]:
        for name, value in connection.items():
            monkeypatch.setenv(f"PEOPLE_GATOR_API__PERSISTENCE__{backend.upper()}__{name.upper()}", str(value))
    with pytest.raises(ValidationError, match="Exactly one persistence backend must be set"):
        Settings(_env_file=None, storage={"local": {}})


@pytest.mark.asyncio
async def test_weaviate_provider_and_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "persistence", PersistenceSettings(weaviate=WEAVIATE))
    init_weaviate = AsyncMock()
    init_postgres = AsyncMock()
    monkeypatch.setattr(database_service, "init_weaviate", init_weaviate)
    monkeypatch.setattr(database_service, "init_postgres", init_postgres)
    await database_service.init_db()
    init_weaviate.assert_awaited_once()
    init_postgres.assert_not_awaited()

    vector_client, facade = object(), object()
    monkeypatch.setattr(database_service, "get_weaviate_client", lambda: vector_client)
    factory = Mock(return_value=facade)
    monkeypatch.setattr(weaviate, "weaviate_database", factory)
    assert [database async for database in database_service.get_database()] == [facade]
    factory.assert_called_once_with(vector_client)

    close_postgres, close_weaviate = AsyncMock(), AsyncMock()
    monkeypatch.setattr(database_service, "close_postgres", close_postgres)
    monkeypatch.setattr(database_service, "close_weaviate", close_weaviate)
    await database_service.close_db()
    close_postgres.assert_awaited_once()
    close_weaviate.assert_awaited_once()


@pytest.mark.asyncio
async def test_postgres_provider_and_initialization(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "persistence", PersistenceSettings(postgres=POSTGRES))
    init_postgres, create_schema = AsyncMock(), AsyncMock()
    engine = object()
    monkeypatch.setattr(database_service, "init_postgres", init_postgres)
    monkeypatch.setattr(database_service, "_postgres_engine", engine)
    monkeypatch.setattr(database_service, "create_postgres_schema", create_schema)
    await database_service.init_db()
    init_postgres.assert_awaited_once()
    create_schema.assert_awaited_once_with(engine)

    session, facade = object(), object()
    context = AsyncMock()
    context.__aenter__.return_value = session
    sessions = Mock(return_value=context)
    monkeypatch.setattr(database_service, "_postgres_sessions", sessions)
    factory = Mock(return_value=facade)
    monkeypatch.setattr(database_service, "postgres_database", factory)
    assert [database async for database in database_service.get_database()] == [facade]
    factory.assert_called_once_with(session)
    context.__aexit__.assert_awaited_once()
