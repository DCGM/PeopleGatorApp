"""Exercise HTTP security selection, live key configuration and OpenAPI."""

import json
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import argon2
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from people_gator_api.app import get_app
from people_gator_api.schemas.api_keys import APIKeyResponse
from people_gator_api.schemas.users import UserResponse
from people_gator_api.services import auth_service
from people_gator_api.services.database_service import get_database_context
from people_gator_api.settings import settings, StorageSettings, LocalStorageSettings


@pytest.fixture
def authenticated_client(tmp_path, monkeypatch):
    user = UserResponse(
        user_id=uuid.uuid4(),
        display_name="Robot",
        is_active=True,
        external_subject="robot",
        external_issuer=settings.jwk.issuer,
        email=None,
    )
    key = APIKeyResponse(
        api_key_id=uuid.uuid4(),
        identifier="importer",
        display_name="Importer",
        user_id=user.user_id,
    )
    database = SimpleNamespace(
        users=SimpleNamespace(get_or_create=AsyncMock(return_value=user)),
        api_keys=SimpleNamespace(get_or_create=AsyncMock(return_value=key)),
    )
    monkeypatch.setattr(
        settings, "storage", StorageSettings(local=LocalStorageSettings(root=tmp_path))
    )
    path = tmp_path / settings.api_keys.keys_path
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "importer": {
                    "display_name": "Importer",
                    "username": "robot",
                    "hash": argon2.PasswordHasher().hash("test-key"),
                    "scopes": [auth_service.BROWSE_SCOPE],
                }
            }
        )
    )
    verify = AsyncMock(
        return_value={
            "iss": settings.jwk.issuer,
            "sub": "robot",
            "scopes": [auth_service.BROWSE_SCOPE],
        }
    )
    monkeypatch.setattr(auth_service, "verify_access_token", verify)
    app = FastAPI()
    @asynccontextmanager
    async def database_context():
        yield database

    app.dependency_overrides[get_database_context] = lambda: database_context()

    @app.get("/browse")
    async def browse(actor: auth_service.BrowseActorDependency):
        return {
            "user_id": str(actor.user_id),
            "api_key_id": str(actor.api_key_id) if actor.api_key_id else None,
        }

    @app.get("/annotate")
    async def annotate(actor: auth_service.AnnotatorActorDependency):
        return {}

    @app.get("/ingest")
    async def ingest(actor: auth_service.DataIngestActorDependency):
        return {}

    @app.get("/admin")
    async def admin(actor: auth_service.AdminActorDependency):
        return {}

    return TestClient(app), database, path, verify, key


@pytest.mark.parametrize(
    "headers,status,challenge",
    [
        ({}, 401, "Bearer, APIKey"),
        ({"Authorization": ""}, 401, "Bearer"),
        ({"Authorization": "Basic abc"}, 401, "Bearer"),
        ({"Authorization": "Bearer "}, 401, "Bearer"),
        ({"X-API-Key": ""}, 401, "APIKey"),
        ({"X-API-Key": "bad"}, 401, "APIKey"),
        ({"Authorization": "Bearer good", "X-API-Key": "bad"}, 400, None),
        ({"Authorization": "", "X-API-Key": ""}, 400, None),
    ],
)
def test_authentication_error_matrix(authenticated_client, headers, status, challenge):
    client, database, _, verify, _ = authenticated_client
    response = client.get("/browse", headers=headers)
    assert response.status_code == status
    if challenge:
        assert response.headers["www-authenticate"] == challenge
    verify.assert_not_awaited()
    database.api_keys.get_or_create.assert_not_awaited()


def test_same_endpoint_accepts_either_method(authenticated_client):
    client, database, _, _, key = authenticated_client
    bearer = client.get("/browse", headers={"Authorization": "Bearer good"})
    api_key = client.get("/browse", headers={"X-API-Key": "test-key"})
    assert bearer.status_code == api_key.status_code == 200
    assert bearer.json()["api_key_id"] is None
    assert api_key.json()["api_key_id"] == str(key.api_key_id)
    assert bearer.json()["user_id"] == api_key.json()["user_id"]
    assert "hash" not in str(database.api_keys.get_or_create.call_args)
    assert "test-key" not in str(database.api_keys.get_or_create.call_args)


def test_revocation_and_insufficient_scopes(authenticated_client):
    client, database, path, _, _ = authenticated_client
    assert client.get("/annotate", headers={"X-API-Key": "test-key"}).status_code == 403
    database.api_keys.get_or_create.assert_not_awaited()
    assert (
        client.get("/annotate", headers={"Authorization": "Bearer good"}).status_code
        == 403
    )
    assert client.get("/browse", headers={"X-API-Key": "test-key"}).status_code == 200
    path.write_text("{}")
    assert client.get("/browse", headers={"X-API-Key": "test-key"}).status_code == 401


def test_invalid_jwt_has_bearer_challenge(authenticated_client):
    client, _, _, verify, _ = authenticated_client
    verify.side_effect = HTTPException(401, "expired")
    response = client.get("/browse", headers={"Authorization": "Bearer expired"})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_operational_errors_are_not_invalid_credentials(authenticated_client):
    client, _, path, _, _ = authenticated_client
    path.unlink()
    with pytest.raises(FileNotFoundError):
        client.get("/browse", headers={"X-API-Key": "test-key"})


def test_openapi_has_scoped_or_alternatives_and_cache():
    app = get_app()
    schema = app.openapi()
    assert app.openapi() is schema
    for path, operations in schema["paths"].items():
        for operation in operations.values():
            if not isinstance(operation, dict) or "security" not in operation:
                continue
            security = operation["security"]
            if {"PeopleGatorAPIKey": []} in security:
                assert {} not in security
                assert len(security) == 2
                oauth = next(
                    entry for entry in security if "PeopleGatorAPIKey" not in entry
                )
                assert len(oauth) == 1
                assert list(oauth.values())[0]


@pytest.mark.parametrize("path", ["/annotate", "/ingest", "/admin"])
@pytest.mark.parametrize(
    "headers", [{"Authorization": "Bearer good"}, {"X-API-Key": "test-key"}]
)
def test_each_actor_scope_is_enforced(authenticated_client, path, headers):
    client, _, _, _, _ = authenticated_client
    assert client.get(path, headers=headers).status_code == 403


@pytest.mark.parametrize("method", ["bearer", "api_key"])
def test_me_preserves_the_public_user_contract(authenticated_client, method):
    client, database, _, _, key = authenticated_client
    from people_gator_api.routes.v1.users import router

    app = client.app
    app.include_router(router)
    user = database.users.get_or_create.return_value
    context = auth_service.AuthContext(
        user_id=user.user_id,
        user=user,
        api_key_id=key.api_key_id if method == "api_key" else None,
        authentication_method=method,
        scopes={auth_service.ANNOTATE_SCOPE},
    )
    app.dependency_overrides[auth_service.get_auth_context] = lambda: context
    response = client.get("/me")
    assert response.status_code == 200
    assert response.json() == user.model_dump(mode="json")
    assert "api_key_id" not in response.json()
