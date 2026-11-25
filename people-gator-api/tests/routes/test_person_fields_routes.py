"""HTTP contract for person fields, life-date filters and sorts (#123)."""
import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from people_gator_api.persistence.contracts import InvalidPersonFieldsError
from people_gator_api.routes.v1 import router as v1_router
from people_gator_api.schemas.entities import EntityListResponse, EntityResponse
from people_gator_api.services.auth_service import get_auth_context
from people_gator_api.services.database_service import get_database


def _client(**entities: AsyncMock) -> TestClient:
    app = FastAPI()
    app.include_router(v1_router)
    app.dependency_overrides[get_database] = lambda: SimpleNamespace(entities=SimpleNamespace(**entities))
    app.dependency_overrides[get_auth_context] = lambda: SimpleNamespace(user_id=uuid.uuid4())
    return TestClient(app)


def _entity(**fields) -> EntityResponse:
    return EntityResponse(entity_id=uuid.uuid4(), entity_type="person", name="Ada",
                          user_id=uuid.uuid4(), **fields)


def test_create_returns_person_fields_and_normalizes_middle_names() -> None:
    create = AsyncMock(side_effect=lambda payload, _: _entity(
        **payload.model_dump(include={"first_name", "middle_names", "birth_date"})))
    response = _client(create=create).post("/api/v1/entities", json={
        "entity_type": "person", "name": "Ada", "first_name": "Ada",
        "middle_names": "  Maria   Luisa ", "birth_date": "1890-03-01",
    })
    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["first_name"], body["middle_names"], body["birth_date"]) == ("Ada", "Maria Luisa", "1890-03-01")
    assert body["surname"] is None and body["death_date"] is None


@pytest.mark.parametrize("body", [
    {"birth_date": "1890-02-30"},
    {"birth_date": "1890"},
    {"birth_date": "1900-01-02", "death_date": "1900-01-01"},
])
def test_invalid_dates_are_unprocessable(body) -> None:
    create, patch = AsyncMock(), AsyncMock()
    client = _client(create=create, patch=patch)
    assert client.post("/api/v1/entities", json={"entity_type": "person", "name": "Ada", **body}).status_code == 422
    assert client.patch(f"/api/v1/entities/{uuid.uuid4()}", json=body).status_code == 422
    create.assert_not_awaited()
    patch.assert_not_awaited()


def test_patch_distinguishes_omitted_and_null() -> None:
    patch = AsyncMock(return_value=_entity())
    response = _client(patch=patch).patch(f"/api/v1/entities/{uuid.uuid4()}", json={"death_date": None})
    assert response.status_code == 200
    assert patch.await_args.args[1].person_values() == {"death_date": None}


@pytest.mark.parametrize("operation", ["patch", "merge"])
def test_stored_state_violations_are_unprocessable(operation) -> None:
    error = AsyncMock(side_effect=InvalidPersonFieldsError("death_date must not be earlier than birth_date"))
    target = uuid.uuid4()
    if operation == "patch":
        response = _client(patch=error).patch(f"/api/v1/entities/{target}", json={"death_date": "1800-01-01"})
    else:
        response = _client(merge_batch=error).post(
            f"/api/v1/entities/{target}:merge-batch",
            json={"source_entity_ids": [str(uuid.uuid4())], "death_date": "1800-01-01"},
        )
    assert response.status_code == 422
    assert "birth_date" in response.json()["detail"]["message"]


def test_list_parses_date_ranges_and_new_sorts() -> None:
    listed = AsyncMock(return_value=EntityListResponse(items=[], limit=10))
    response = _client(list=listed).get("/api/v1/entities", params={
        "filter.birth_date_from": "1890-01-01", "filter.birth_date_to": "1899-12-31",
        "filter.death_date_from": "1950-01-01", "sort": "surname",
    })
    assert response.status_code == 200, response.text
    request = listed.await_args.args[0]
    assert (request.filter_.birth_date_from, request.filter_.birth_date_to) == (date(1890, 1, 1), date(1899, 12, 31))
    assert request.filter_.death_date_from == date(1950, 1, 1)
    assert request.effective_sort() == ("surname", "asc")


@pytest.mark.parametrize("params", [
    {"filter.birth_date_from": "1900-01-02", "filter.birth_date_to": "1900-01-01"},
    {"filter.death_date_to": "not-a-date"},
])
def test_invalid_ranges_are_rejected(params) -> None:
    listed = AsyncMock()
    assert _client(list=listed).get("/api/v1/entities", params=params).status_code == 422
    listed.assert_not_awaited()
