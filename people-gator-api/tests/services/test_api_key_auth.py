"""Exercise HTTP security selection, live key configuration and OpenAPI."""

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import argon2
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, TypeAdapter

from auth_doubles import IdentityStore, InMemoryAPIKeyRepository
from people_gator_api.app import get_app
from people_gator_api.schemas.users import UserResponse
from people_gator_api.services import auth_service
from people_gator_api.services.database_service import get_database, get_database_context
from people_gator_api.services.jwk_service import AccessTokenClaims
from people_gator_api.settings import settings, StorageSettings, LocalStorageSettings


@dataclass
class FakeVerifier:
    """Stands in for JWT verification, returning fixed claims for any token."""

    claims: AccessTokenClaims
    error: HTTPException | None = None
    tokens: list[str] = field(default_factory=list[str])

    async def __call__(self, token: str) -> AccessTokenClaims:
        self.tokens.append(token)
        if self.error is not None:
            raise self.error
        return self.claims


@dataclass
class AuthenticatedClient:
    client: TestClient
    app: FastAPI
    store: IdentityStore
    api_keys: InMemoryAPIKeyRepository
    keys_path: Path
    verify: FakeVerifier
    user: UserResponse


async def browse(actor: auth_service.BrowseActorDependency) -> dict[str, str | None]:
    return {
        "user_id": str(actor.user_id),
        "api_key_id": str(actor.api_key_id) if actor.api_key_id else None,
    }


async def annotate(actor: auth_service.AnnotatorActorDependency) -> dict[str, str]:
    return {"user_id": str(actor.user_id)}


async def ingest(actor: auth_service.DataIngestActorDependency) -> dict[str, str]:
    return {"user_id": str(actor.user_id)}


async def admin(actor: auth_service.AdminActorDependency) -> dict[str, str]:
    return {"user_id": str(actor.user_id)}


@pytest.fixture
def authenticated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AuthenticatedClient:
    api_keys = InMemoryAPIKeyRepository()
    store = IdentityStore(api_keys=api_keys)
    user = UserResponse(
        user_id=uuid.uuid4(),
        display_name="Robot",
        is_active=True,
        external_subject="robot",
        external_issuer=settings.jwk.issuer,
        email=None,
    )
    store.users.records[user.user_id] = user
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
    verify = FakeVerifier(AccessTokenClaims(
        iss=settings.jwk.issuer, sub="robot", iat=0, exp=1,
        scopes=[auth_service.BROWSE_SCOPE], uid=user.user_id,
    ))
    monkeypatch.setattr(auth_service, "verify_access_token", verify)
    app = FastAPI()
    app.dependency_overrides[get_database_context] = store.context
    app.dependency_overrides[get_database] = lambda: store
    for path_name, handler in (
        ("/browse", browse), ("/annotate", annotate), ("/ingest", ingest), ("/admin", admin),
    ):
        app.add_api_route(path_name, handler)
    return AuthenticatedClient(TestClient(app), app, store, api_keys, path, verify, user)


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
def test_authentication_error_matrix(
    authenticated: AuthenticatedClient, headers: dict[str, str], status: int, challenge: str | None,
) -> None:
    response = authenticated.client.get("/browse", headers=headers)
    assert response.status_code == status
    if challenge:
        assert response.headers["www-authenticate"] == challenge
    assert authenticated.verify.tokens == []
    assert authenticated.api_keys.requests == []


def test_same_endpoint_accepts_either_method(authenticated: AuthenticatedClient) -> None:
    bearer = authenticated.client.get("/browse", headers={"Authorization": "Bearer good"})
    api_key = authenticated.client.get("/browse", headers={"X-API-Key": "test-key"})
    assert bearer.status_code == api_key.status_code == 200
    assert bearer.json()["api_key_id"] is None
    assert api_key.json()["api_key_id"] == str(authenticated.api_keys.records["importer"].api_key_id)
    assert bearer.json()["user_id"] == api_key.json()["user_id"] == str(authenticated.user.user_id)
    registered = str(authenticated.api_keys.requests)
    assert "hash" not in registered
    assert "test-key" not in registered


def test_revocation_and_insufficient_scopes(authenticated: AuthenticatedClient) -> None:
    client = authenticated.client
    assert client.get("/annotate", headers={"X-API-Key": "test-key"}).status_code == 403
    assert authenticated.api_keys.requests == []
    assert (
        client.get("/annotate", headers={"Authorization": "Bearer good"}).status_code
        == 403
    )
    assert client.get("/browse", headers={"X-API-Key": "test-key"}).status_code == 200
    authenticated.keys_path.write_text("{}")
    assert client.get("/browse", headers={"X-API-Key": "test-key"}).status_code == 401


def test_invalid_jwt_has_bearer_challenge(authenticated: AuthenticatedClient) -> None:
    authenticated.verify.error = HTTPException(401, "expired")
    response = authenticated.client.get("/browse", headers={"Authorization": "Bearer expired"})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_operational_errors_are_not_invalid_credentials(authenticated: AuthenticatedClient) -> None:
    authenticated.keys_path.unlink()
    with pytest.raises(FileNotFoundError):
        authenticated.client.get("/browse", headers={"X-API-Key": "test-key"})


class _Operation(BaseModel):
    """The part of an OpenAPI operation these checks read; other fields are ignored."""

    security: list[dict[str, list[str]]] | None = None


# FastAPI path items contain only HTTP-method operations.
_paths = TypeAdapter(dict[str, dict[str, _Operation]])


def test_openapi_has_scoped_or_alternatives_and_cache() -> None:
    app = get_app()
    schema = app.openapi()
    assert app.openapi() is schema
    for operations in _paths.validate_python(schema["paths"]).values():
        for operation in operations.values():
            if operation.security is None:
                continue
            security = operation.security
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
def test_each_actor_scope_is_enforced(
    authenticated: AuthenticatedClient, path: str, headers: dict[str, str],
) -> None:
    assert authenticated.client.get(path, headers=headers).status_code == 403


@pytest.mark.parametrize("method", ["bearer", "api_key"])
def test_me_preserves_the_public_user_contract(
    authenticated: AuthenticatedClient, method: Literal["bearer", "api_key"],
) -> None:
    from people_gator_api.routes.v1.users import router

    authenticated.app.include_router(router)
    user = authenticated.user
    context = auth_service.AuthContext(
        user_id=user.user_id,
        api_key_id=uuid.uuid4() if method == "api_key" else None,
        authentication_method=method,
        scopes={auth_service.ANNOTATE_SCOPE},
    )
    authenticated.app.dependency_overrides[auth_service.get_auth_context] = lambda: context
    response = authenticated.client.get("/me")
    assert response.status_code == 200
    assert response.json() == user.model_dump(mode="json")
    assert "api_key_id" not in response.json()
    assert authenticated.store.users.calls == ["get"]


def test_api_keys_of_inactive_users_are_rejected(authenticated: AuthenticatedClient) -> None:
    authenticated.store.users.set_active(authenticated.user.user_id, False)
    response = authenticated.client.get("/browse", headers={"X-API-Key": "test-key"})
    assert response.status_code == 403
    assert authenticated.api_keys.requests == []
    assert not authenticated.store.users.records[authenticated.user.user_id].is_active


def test_bearer_requests_do_not_resolve_users(authenticated: AuthenticatedClient) -> None:
    response = authenticated.client.get("/browse", headers={"Authorization": "Bearer good"})
    assert response.status_code == 200
    assert response.json()["user_id"] == str(authenticated.user.user_id)
    assert authenticated.store.users.calls == []
    assert authenticated.store.entries == 0
