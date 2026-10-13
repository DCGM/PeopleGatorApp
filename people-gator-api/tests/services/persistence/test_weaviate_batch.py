import uuid
from types import SimpleNamespace
from typing import Any, cast

import pytest

from people_gator_api.persistence.weaviate import (
    WeaviateEntityRepository,
)


@pytest.mark.asyncio
async def test_entity_delete_batch_uses_one_delete_many_call() -> None:
    calls: list[object] = []

    class _Data:
        async def delete_many(self, *, where: object) -> SimpleNamespace:
            calls.append(where)
            return SimpleNamespace(successful=2)

    from unittest.mock import AsyncMock
    collection = SimpleNamespace(data=_Data(), query=SimpleNamespace(fetch_objects=AsyncMock(return_value=SimpleNamespace(objects=[]))))

    def get_collection(_name: str) -> SimpleNamespace:
        return collection

    client = SimpleNamespace(collections=SimpleNamespace(get=get_collection))
    repository = WeaviateEntityRepository(cast(Any, client))

    deleted = await repository.delete_batch([uuid.uuid4(), uuid.uuid4(), uuid.uuid4()])

    assert deleted.deleted_count == 2
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_empty_entity_delete_batch_skips_weaviate() -> None:
    client = SimpleNamespace(collections=SimpleNamespace())
    repository = WeaviateEntityRepository(cast(Any, client))

    assert (await repository.delete_batch([])).deleted_count == 0
