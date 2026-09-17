from unittest.mock import AsyncMock

import httpx
import pytest
from weaviate.classes.config import ReferenceProperty
from weaviate.exceptions import UnexpectedStatusCodeError

from people_gator_api.services.weaviate_service import client
from people_gator_api.services.weaviate_service import db_schema


class _FakeCollections:
    def __init__(self, existing_collections: set[str]) -> None:
        super().__init__()
        self._existing_collections = set(existing_collections)
        self.operation_log: list[tuple[str, str]] = []
        self.created_collections: list[str] = []
        self.exists_attempts = 0

    async def exists(self, collection_name: str) -> bool:
        self.operation_log.append(("exists", collection_name))
        self.exists_attempts += 1
        return collection_name in self._existing_collections

    async def create(
        self,
        *,
        name: str,
        description: str,
        properties: list[object],
        references: list[ReferenceProperty],
        vector_config: list[object] | None = None,
    ) -> None:
        del description
        del properties
        del references
        del vector_config
        self.operation_log.append(("create", name))
        self.created_collections.append(name)


class _RetryableCollections(_FakeCollections):
    def __init__(self, existing_collections: set[str], transient_failures: int) -> None:
        super().__init__(existing_collections)
        self._transient_failures = transient_failures

    async def exists(self, collection_name: str) -> bool:
        self.operation_log.append(("exists", collection_name))
        self.exists_attempts += 1
        if self.exists_attempts <= self._transient_failures:
            response = httpx.Response(
                500,
                json={
                    "error": [{"message": "failed to execute query: leader not found"}]
                },
            )
            raise UnexpectedStatusCodeError("Collection may not exist!", response)
        return collection_name in self._existing_collections


class _FakeWeaviateClient:
    def __init__(self, existing_collections: set[str]) -> None:
        super().__init__()
        self.collections = _FakeCollections(existing_collections)


class _LifecycleClient:
    def __init__(self, connect_error: Exception | None = None) -> None:
        self.connect_error = connect_error
        self.connect_calls = 0
        self.close_calls = 0

    async def connect(self) -> None:
        self.connect_calls += 1
        if self.connect_error is not None:
            raise self.connect_error

    async def close(self) -> None:
        self.close_calls += 1


@pytest.mark.asyncio
async def test_init_weaviate_rebuilds_client_after_failed_connect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failed_client = _LifecycleClient(ConnectionError("database is starting"))
    connected_client = _LifecycleClient()
    clients = iter((failed_client, connected_client))
    ensure_collections = AsyncMock()
    sleep = AsyncMock()

    monkeypatch.setattr(client, "_client", None)
    monkeypatch.setattr(client, "_build_client", lambda: next(clients))
    monkeypatch.setattr(client, "_ensure_collections", ensure_collections)
    monkeypatch.setattr(client.asyncio, "sleep", sleep)

    await client.init_weaviate()

    assert failed_client.close_calls == 1
    assert connected_client.connect_calls == 1
    assert client.get_weaviate_client() is connected_client
    ensure_collections.assert_awaited_once_with(connected_client)
    sleep.assert_awaited_once()

    await client.close_weaviate()


def test_ordered_collection_specs_respect_reference_dependencies() -> None:
    ordered_collection_names = [
        collection_name
        for collection_name, _ in client.ordered_collection_specs(
            db_schema.ALL_COLLECTION_SPECS
        )
    ]

    assert ordered_collection_names.index(
        db_schema.USER_COLLECTION
    ) < ordered_collection_names.index(db_schema.ENTITY_COLLECTION)
    assert ordered_collection_names.index(
        db_schema.SOURCE_COLLECTION
    ) < ordered_collection_names.index(db_schema.ENTITY_COLLECTION)
    assert ordered_collection_names.index(
        db_schema.USER_COLLECTION
    ) < ordered_collection_names.index(db_schema.ENTITY_COLLECTION)


def test_ordered_collection_specs_reject_cycles() -> None:
    cyclic_specs: dict[str, db_schema.CollectionSpec] = {
        "Alpha": (
            [],
            [
                ReferenceProperty(
                    name="beta",
                    target_collection="Beta",
                    description="Depends on Beta.",
                )
            ],
            None,
        ),
        "Beta": (
            [],
            [
                ReferenceProperty(
                    name="alpha",
                    target_collection="Alpha",
                    description="Depends on Alpha.",
                )
            ],
            None,
        ),
    }

    with pytest.raises(ValueError, match="unresolved reference dependencies"):
        client.ordered_collection_specs(cyclic_specs)


@pytest.mark.asyncio
async def test_ensure_collections_creates_only_missing_collections() -> None:
    collection_names_in_order = [
        collection_name
        for collection_name, _ in client.ordered_collection_specs(
            db_schema.ALL_COLLECTION_SPECS
        )
    ]
    existing_collections = set(collection_names_in_order[:2])
    fake_client = _FakeWeaviateClient(existing_collections)

    await client._ensure_collections(fake_client)  # type: ignore[arg-type]

    expected_created = [
        collection_name
        for collection_name in collection_names_in_order
        if collection_name not in existing_collections
    ]
    assert fake_client.collections.created_collections == expected_created


@pytest.mark.asyncio
async def test_ensure_collections_runs_existence_checks_before_create_calls() -> None:
    fake_client = _FakeWeaviateClient(existing_collections=set())

    await client._ensure_collections(fake_client)  # type: ignore[arg-type]

    first_create_index = next(
        index
        for index, (operation, _) in enumerate(fake_client.collections.operation_log)
        if operation == "create"
    )
    assert all(
        operation == "exists"
        for operation, _ in fake_client.collections.operation_log[:first_create_index]
    )

    existence_checks = [
        collection_name
        for operation, collection_name in fake_client.collections.operation_log
        if operation == "exists"
    ]
    expected_collection_names = [
        collection_name
        for collection_name, _ in client.ordered_collection_specs(
            db_schema.ALL_COLLECTION_SPECS
        )
    ]
    assert existence_checks == expected_collection_names


@pytest.mark.asyncio
async def test_ensure_collections_retries_transient_collection_errors() -> None:
    fake_client = _FakeWeaviateClient(existing_collections=set())
    fake_client.collections = _RetryableCollections(
        existing_collections=set(),
        transient_failures=2,
    )

    await client._ensure_collections(fake_client, retry_delay_seconds=0.0)  # type: ignore[arg-type]

    assert fake_client.collections.exists_attempts > 2
