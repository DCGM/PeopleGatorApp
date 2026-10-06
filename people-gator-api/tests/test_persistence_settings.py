import os
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


def test_postgres_is_default_with_optional_weaviate() -> None:
    config = PersistenceSettings(postgres=POSTGRES)
    assert config.backend == "postgres"
    assert config.weaviate is None
    assert isinstance(config.postgres, PersistenceBaseSetting)
    assert PersistenceSettings(postgres=POSTGRES, weaviate=WEAVIATE).backend == "postgres"


@pytest.mark.parametrize("postgres_enabled,weaviate_enabled", [(False, False), (True, True)])
def test_requires_exactly_one_backend(postgres_enabled: bool, weaviate_enabled: bool) -> None:
    with pytest.raises(ValidationError, match="Exactly one persistence backend"):
        PersistenceSettings(
            postgres={**POSTGRES, "enabled": postgres_enabled},
            weaviate={**WEAVIATE, "enabled": weaviate_enabled},
        )


def test_missing_backend_and_connection_fields_are_rejected() -> None:
    with pytest.raises(ValidationError, match="Exactly one persistence backend"):
        PersistenceSettings()
    with pytest.raises(ValidationError):
        PersistenceSettings(weaviate={"enabled": True})


def test_weaviate_environment_without_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.startswith("PEOPLE_GATOR_API__PERSISTENCE__"):
            monkeypatch.delenv(name)
    for name, value in {**WEAVIATE, "enabled": True}.items():
        monkeypatch.setenv(f"PEOPLE_GATOR_API__PERSISTENCE__WEAVIATE__{name.upper()}", str(value))
    configured = Settings(_env_file=None, **settings.model_dump(exclude={"persistence"}))
    assert configured.persistence.backend == "weaviate"
    assert configured.persistence.postgres is None
    assert isinstance(configured.persistence.weaviate, PersistenceBaseSetting)


@pytest.mark.asyncio
async def test_weaviate_provider_and_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "persistence", PersistenceSettings(weaviate={**WEAVIATE, "enabled": True}))
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
