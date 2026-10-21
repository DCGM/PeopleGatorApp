import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from people_gator_api.routes.v1 import router
from people_gator_api.schemas.search import (
    EntitySearchQuery,
    FoundItemBase,
    SearchEntitiesRequest,
    SearchFacesRequest,
)
from people_gator_api.persistence.weaviate import (
    WeaviateEntityRepository,
    WeaviateFaceRepository,
)
from people_gator_api.services.auth_service import get_auth_context
from people_gator_api.services.database_service import get_database


def test_annotation_defaults_are_canonical_and_selection_cannot_be_empty():
    entity_id = uuid.uuid4()
    default = EntitySearchQuery(entity_id=entity_id)
    explicit = EntitySearchQuery(
        entity_id=entity_id, entity_annotations=["name", "aliases", "faces", "name"]
    )
    assert default.model_dump() == explicit.model_dump()
    for values in (
        {"entity_id": entity_id, "entity_annotations": []},
        {"text": ["test"], "entity_annotations": ["name"]},
        {"entity_id": entity_id, "entity_annotations": ["unknown"]},
    ):
        with pytest.raises(ValidationError):
            EntitySearchQuery(**values)


@pytest.mark.parametrize("endpoint", ["faces", "entities"])
def test_internal_score_validation_is_not_reported_as_invalid_search(endpoint):
    async def broken(_request):
        FoundItemBase(score=1.0, face_score=float("nan"))

    repository = SimpleNamespace(search=AsyncMock(side_effect=broken))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_auth_context] = lambda: SimpleNamespace(
        user_id=uuid.uuid4()
    )
    app.dependency_overrides[get_database] = lambda: SimpleNamespace(
        **{endpoint: repository}
    )
    response = TestClient(app, raise_server_exceptions=False).get(
        f"/api/v1/search-{endpoint}", params={"query.entity_id": str(uuid.uuid4())}
    )
    assert response.status_code == 500
    assert "invalid_search" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "repository,request_type",
    [
        (WeaviateEntityRepository, SearchEntitiesRequest),
        (WeaviateFaceRepository, SearchFacesRequest),
    ],
)
async def test_weaviate_truthfully_rejects_entity_resolution(repository, request_type):
    with pytest.raises(NotImplementedError, match="requires PostgreSQL"):
        await repository(Mock()).search(
            request_type(limit=10, query=EntitySearchQuery(entity_id=uuid.uuid4()))
        )
