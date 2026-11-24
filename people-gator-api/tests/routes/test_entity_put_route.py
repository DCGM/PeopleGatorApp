import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from people_gator_api.persistence.contracts import EntityPutResult, EntityTypeConflictError
from people_gator_api.routes.v1 import router as v1_router
from people_gator_api.routes.v1.entities import router
from people_gator_api.schemas.entities import EntityCreateRequest, EntityResponse
from people_gator_api.schemas.enums import EntityType
from people_gator_api.services.auth_service import get_auth_context
from people_gator_api.services.database_service import get_database


def test_put_documents_create_replace_and_type_conflict() -> None:
    app = FastAPI()
    app.include_router(router)
    operation = app.openapi()["paths"]["/entities/{entity_id}"]["put"]

    assert operation["requestBody"]["required"] is True
    assert operation["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/EntityCreateRequest"
    )
    for code in ("200", "201"):
        schema = operation["responses"][code]["content"]["application/json"]["schema"]
        assert schema["$ref"].endswith("/EntityResponse")
    assert "409" in operation["responses"]
    assert "cleared" in operation["description"]
    assert any(
        "people-gator:annotate" in scopes
        for item in operation["security"]
        for scopes in item.values()
    )


def _client(put: AsyncMock) -> TestClient:
    app = FastAPI()
    app.include_router(v1_router)
    app.dependency_overrides[get_database] = lambda: SimpleNamespace(
        entities=SimpleNamespace(put=put)
    )
    actor = SimpleNamespace(user_id=uuid.uuid4())
    app.dependency_overrides[get_auth_context] = lambda: actor
    return TestClient(app)


def _entity(entity_id: uuid.UUID) -> EntityResponse:
    return EntityResponse(
        entity_id=entity_id,
        entity_type=EntityType.person,
        name="Ada",
        user_id=uuid.uuid4(),
    )


@pytest.mark.parametrize("created,status_code", [(True, 201), (False, 200)])
def test_put_status_reports_whether_the_entity_was_created(created, status_code) -> None:
    entity_id = uuid.uuid4()
    put = AsyncMock(return_value=EntityPutResult(_entity(entity_id), created=created))

    response = _client(put).put(
        f"/api/v1/entities/{entity_id}", json={"entity_type": "person", "name": "Ada"}
    )

    assert response.status_code == status_code
    assert response.json()["entity_id"] == str(entity_id)
    called_id, payload, _ = put.await_args.args
    assert called_id == entity_id
    assert payload == EntityCreateRequest(entity_type=EntityType.person, name="Ada")


def test_put_type_change_is_a_conflict() -> None:
    # Only "person" exists today; the repository guards future types.
    put = AsyncMock(side_effect=EntityTypeConflictError("entity_type cannot change"))

    response = _client(put).put(
        f"/api/v1/entities/{uuid.uuid4()}", json={"entity_type": "person", "name": "Ada"}
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "entity_type_conflict"


def test_put_other_persistence_errors_are_unprocessable() -> None:
    put = AsyncMock(side_effect=ValueError("actor user not found"))

    response = _client(put).put(
        f"/api/v1/entities/{uuid.uuid4()}", json={"entity_type": "person", "name": "Ada"}
    )

    assert response.status_code == 422


def test_put_requires_a_name_and_type() -> None:
    put = AsyncMock()

    response = _client(put).put(f"/api/v1/entities/{uuid.uuid4()}", json={"name": "Ada"})

    assert response.status_code == 422
    put.assert_not_awaited()
