from version_preconditions import versioned_targets
import uuid
from people_gator_api.schemas.common import GenericActor
from types import SimpleNamespace
from typing import Any, cast

import pytest

from people_gator_api.persistence.weaviate import (
    WeaviateEntityRepository,
)


@pytest.mark.asyncio
async def test_versioned_entity_delete_batch_is_explicitly_unsupported() -> None:
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

    with pytest.raises(NotImplementedError, match="require PostgreSQL"):
        await repository.delete_batch(
            versioned_targets({}),
            context=GenericActor(user_id=uuid.uuid4()),
        )

    assert calls == []


@pytest.mark.asyncio
async def test_empty_entity_delete_batch_skips_weaviate() -> None:
    client = SimpleNamespace(collections=SimpleNamespace())
    repository = WeaviateEntityRepository(cast(Any, client))

    with pytest.raises(NotImplementedError, match="require PostgreSQL"):
        await repository.delete_batch(
            versioned_targets({}), context=GenericActor(user_id=uuid.uuid4())
        )


@pytest.mark.asyncio
async def test_thumbnail_batch_rejected_before_any_weaviate_write():
    from unittest.mock import AsyncMock
    from people_gator_api.schemas.entities import EntityPatchBatchItem, EntityPatchRequest

    repository = WeaviateEntityRepository(cast(Any, SimpleNamespace()))
    repository.get = AsyncMock()
    actor = GenericActor(user_id=uuid.uuid4())
    with pytest.raises(NotImplementedError, match="require PostgreSQL"):
        await repository.patch_batch(
            [
                EntityPatchBatchItem(
                    entity_id=uuid.uuid4(),
                    name="Must stay unchanged",
                    version=1,
                ),
                EntityPatchBatchItem(
                    entity_id=uuid.uuid4(), thumbnail_face_id=None, version=1
                ),
            ],
            actor,
        )
    with pytest.raises(NotImplementedError, match="require PostgreSQL"):
        await repository.patch(
            uuid.uuid4(),
            EntityPatchRequest(thumbnail_face_id=uuid.uuid4(), version=1),
            actor,
        )
    repository.get.assert_not_awaited()
