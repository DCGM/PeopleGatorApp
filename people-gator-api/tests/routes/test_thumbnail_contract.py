import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from people_gator_api.routes.v1.entities import router
from people_gator_api.schemas.entities import EntityPatchRequest
from people_gator_api.schemas.missing import is_missing
from people_gator_api.services.auth_service import get_auth_context
from people_gator_api.services.database_service import get_database


def test_openapi_selection_is_optional_nullable_and_in_response_variants():
    app = FastAPI()
    app.include_router(router)
    schemas = app.openapi()['components']['schemas']
    for name in ('EntityPatchRequest', 'EntityPatchBatchItem'):
        schema = schemas[name]
        assert 'thumbnail_face_id' not in schema.get('required', [])
        assert {'type': 'null'} in schema['properties']['thumbnail_face_id']['anyOf']
        assert 'omit to preserve' in schema['properties']['thumbnail_face_id']['description']
    assert {'thumbnail_face_id', 'thumbnail_mode'} <= schemas['EntityResponse']['properties'].keys()
    assert is_missing(EntityPatchRequest().thumbnail_face_id)
    assert EntityPatchRequest(thumbnail_face_id=None).model_dump() == {'thumbnail_face_id': None}


def test_thumbnail_patch_keeps_annotator_authorization():
    from people_gator_api.services.auth_service import ANNOTATE_SCOPE
    app = FastAPI()
    app.include_router(router)
    for path in ('/entities/{entity_id}', '/entities:batch'):
        security = app.openapi()['paths'][path]['patch']['security']
        assert any(ANNOTATE_SCOPE in scopes for alternative in security for scopes in alternative.values())
