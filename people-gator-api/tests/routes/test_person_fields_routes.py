"""Typed /people routes for the Person subtype; /entities stays shared-only (#123)."""
import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from people_gator_api.persistence.contracts import (
    EntityTypeConflictError,
    InvalidPersonFieldsError,
    PersonPutResult,
)
from people_gator_api.routes.v1 import router as v1_router
from people_gator_api.schemas.entities import (
    GenericEntityResponse,
    PersonListResponse,
    PersonResponse,
)
from people_gator_api.services.auth_service import get_auth_context
from people_gator_api.services.database_service import get_database

PERSON_FIELDS = {"first_name", "middle_names", "surname", "birth_date", "death_date"}


def _client(**entities: AsyncMock) -> TestClient:
    app = FastAPI()
    app.include_router(v1_router)
    app.dependency_overrides[get_database] = lambda: SimpleNamespace(entities=SimpleNamespace(**entities))
    app.dependency_overrides[get_auth_context] = lambda: SimpleNamespace(user_id=uuid.uuid4())
    return TestClient(app)


def _person(cls=PersonResponse, **fields):
    return cls(entity_id=uuid.uuid4(), entity_type="person", name="Ada", user_id=uuid.uuid4(), **fields)


def test_openapi_separates_typed_people_from_shared_entities() -> None:
    app = FastAPI()
    app.include_router(v1_router)
    spec = app.openapi()
    schemas = spec["components"]["schemas"]
    for name in ("EntityCreateRequest", "EntityPatchRequest", "EntityResponse", "EntityMergeBatchRequest"):
        assert not PERSON_FIELDS & set(schemas[name]["properties"]), name
    for name in ("PersonCreateRequest", "PersonPatchRequest", "PersonResponse", "PersonMergeBatchRequest", "FoundPerson"):
        assert PERSON_FIELDS <= set(schemas[name]["properties"]), name
    assert not any(name.startswith("GenericEntity") for name in schemas)
    people = spec["paths"]["/api/v1/people/{entity_id}"]
    assert people["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("/PersonResponse")
    assert set(people) == {"get", "patch", "put", "delete"}
    assert {"post", "get"} <= set(spec["paths"]["/api/v1/people"])
    assert "post" in spec["paths"]["/api/v1/people/{target_entity_id}:merge-batch"]


def test_entities_routes_omit_person_fields_from_generic_records() -> None:
    get = AsyncMock(return_value=_person(GenericEntityResponse, surname="Novak", birth_date=date(1890, 1, 1)))
    body = _client(get=get).get(f"/api/v1/entities/{uuid.uuid4()}").json()
    assert body["name"] == "Ada" and not PERSON_FIELDS & set(body)
    # Person fields sent to /entities are not part of its contract and are ignored.
    create = AsyncMock(return_value=_person(GenericEntityResponse))
    assert _client(create=create).post("/api/v1/entities", json={
        "entity_type": "person", "name": "Ada", "surname": "Novak"}).status_code == 201
    assert not hasattr(create.await_args.args[0], "surname")


def test_create_returns_person_fields_and_normalizes_middle_names() -> None:
    create = AsyncMock(side_effect=lambda payload, _: _person(
        **payload.model_dump(include={"first_name", "middle_names", "birth_date"})))
    response = _client(create_person=create).post("/api/v1/people", json={
        "name": "Ada", "first_name": "Ada", "middle_names": "  Maria   Luisa ", "birth_date": "1890-03-01",
    })
    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["first_name"], body["middle_names"], body["birth_date"]) == ("Ada", "Maria Luisa", "1890-03-01")
    assert body["entity_type"] == "person" and body["surname"] is None and body["death_date"] is None
    assert _client(create_person=create).post(
        "/api/v1/people", json={"name": "Ada", "entity_type": "organization"}).status_code == 422


@pytest.mark.parametrize("body", [
    {"birth_date": "1890-02-30"},
    {"birth_date": "1890"},
    {"birth_date": "1900-01-02", "death_date": "1900-01-01"},
])
def test_invalid_dates_are_unprocessable(body) -> None:
    create, patch = AsyncMock(), AsyncMock()
    client = _client(create_person=create, patch_person=patch)
    assert client.post("/api/v1/people", json={"name": "Ada", **body}).status_code == 422
    assert client.patch(f"/api/v1/people/{uuid.uuid4()}", json=body).status_code == 422
    create.assert_not_awaited()
    patch.assert_not_awaited()


def test_patch_distinguishes_omitted_and_null_and_404s_non_people() -> None:
    patch = AsyncMock(return_value=_person())
    response = _client(patch_person=patch).patch(f"/api/v1/people/{uuid.uuid4()}", json={"death_date": None})
    assert response.status_code == 200
    assert patch.await_args.args[1].person_values() == {"death_date": None}
    missing = AsyncMock(return_value=None)
    assert _client(get_person=missing).get(f"/api/v1/people/{uuid.uuid4()}").status_code == 404
    assert _client(patch_person=missing).patch(f"/api/v1/people/{uuid.uuid4()}", json={}).status_code == 404


@pytest.mark.parametrize(("created", "code"), [(True, 201), (False, 200)])
def test_put_creates_or_replaces_and_rejects_other_types(created, code) -> None:
    put = AsyncMock(return_value=PersonPutResult(_person(surname="Novak"), created))
    response = _client(put_person=put).put(f"/api/v1/people/{uuid.uuid4()}", json={"name": "Ada", "surname": "Novak"})
    assert response.status_code == code and response.json()["surname"] == "Novak"
    conflict = AsyncMock(side_effect=EntityTypeConflictError("entity_type cannot change"))
    assert _client(put_person=conflict).put(f"/api/v1/people/{uuid.uuid4()}", json={"name": "Ada"}).status_code == 409


def test_merge_validates_stored_dates_and_404s_non_people() -> None:
    target = uuid.uuid4()
    body = {"source_entity_ids": [str(uuid.uuid4())], "death_date": "1800-01-01"}
    error = AsyncMock(side_effect=InvalidPersonFieldsError("death_date must not be earlier than birth_date"))
    response = _client(merge_people=error).post(f"/api/v1/people/{target}:merge-batch", json=body)
    assert response.status_code == 422 and "birth_date" in response.json()["detail"]["message"]
    assert error.await_args.args[1].death_date == date(1800, 1, 1)
    missing = AsyncMock(return_value=None)
    assert _client(merge_people=missing).post(f"/api/v1/people/{target}:merge-batch", json=body).status_code == 404


def test_list_parses_date_ranges_and_person_sorts() -> None:
    listed = AsyncMock(return_value=PersonListResponse(items=[], limit=10))
    response = _client(list_people=listed).get("/api/v1/people", params={
        "filter.birth_date_from": "1890-01-01", "filter.birth_date_to": "1899-12-31",
        "filter.death_date_from": "1950-01-01", "sort": "surname",
    })
    assert response.status_code == 200, response.text
    request = listed.await_args.args[0]
    assert (request.filter_.birth_date_from, request.filter_.birth_date_to) == (date(1890, 1, 1), date(1899, 12, 31))
    assert request.filter_.death_date_from == date(1950, 1, 1)
    assert request.effective_sort() == ("surname", "asc")
    assert request.to_generic().filter_.entity_type == ["person"]


@pytest.mark.parametrize(("path", "params"), [
    ("/api/v1/people", {"filter.birth_date_from": "1900-01-02", "filter.birth_date_to": "1900-01-01"}),
    ("/api/v1/people", {"filter.death_date_to": "not-a-date"}),
    ("/api/v1/entities", {"sort": "surname"}),
])
def test_invalid_ranges_and_generic_person_sorts_are_rejected(path, params) -> None:
    listed = AsyncMock()
    client = _client(list=listed, list_people=listed)
    assert client.get(path, params=params).status_code == 422
    listed.assert_not_awaited()
