import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from people_gator_api.routes.v1 import router
from people_gator_api.services.auth_service import get_auth_context
from people_gator_api.services.database_service import get_database


@pytest.mark.parametrize("path", ["/api/v1/entities", "/api/v1/search-entities"])
@pytest.mark.parametrize(
    "params",
    [
        {
            "filter.last_touched_from": "2026-01-02T00:00:00Z",
            "filter.last_touched_to": "2026-01-01T00:00:00Z",
        },
        {"filter.last_touched_from": "2026-01-01T00:00:00"},
        {"filter.last_touched_to": "not-a-date"},
    ],
)
def test_invalid_touch_ranges_return_validation_error(path, params):
    app = FastAPI()
    app.include_router(router)
    entities = SimpleNamespace(list=AsyncMock(), search=AsyncMock())
    app.dependency_overrides[get_database] = lambda: SimpleNamespace(entities=entities)
    app.dependency_overrides[get_auth_context] = lambda: SimpleNamespace(
        user_id=uuid.uuid4()
    )
    response = TestClient(app).get(path, params={**params, "query.text": "Ada"})
    assert response.status_code == 422
    entities.list.assert_not_awaited()
    entities.search.assert_not_awaited()


@pytest.mark.parametrize('path', ['/api/v1/entities', '/api/v1/search-entities', '/api/v1/faces', '/api/v1/text-mentions', '/api/v1/documents', '/api/v1/search-documents', '/api/v1/pages', '/api/v1/search-pages'])
@pytest.mark.parametrize('params', [
    {'filter.evidence_touched_from': '2026-01-02T00:00:00Z', 'filter.evidence_touched_to': '2026-01-01T00:00:00Z'},
    {'filter.evidence_touched_from': '2026-01-01T00:00:00'},
    {'filter.evidence_touched_to': 'not-a-date'},
])
def test_shared_annotation_bounds_are_validated_on_every_resource(path, params):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_database] = lambda: SimpleNamespace()
    app.dependency_overrides[get_auth_context] = lambda: SimpleNamespace(user_id=uuid.uuid4())
    response = TestClient(app).get(path, params={**params, 'query.text': 'Irena'})
    assert response.status_code == 422
