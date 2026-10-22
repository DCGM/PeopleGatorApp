"""Bearer authorization over HTTP with real signing and no persistence access."""

import asyncio
import datetime
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from joserfc.jwk import ECKey, KeySet
from joserfc.jwt import encode

from people_gator_api.services import auth_service, jwk_service
from people_gator_api.services.database_service import get_database, get_database_context
from people_gator_api.settings import JwkSettings, LocalStorageSettings, StorageSettings, settings


class ForbiddenDatabase:
    """Records and fails any attempt to enter a database scope."""

    def __init__(self) -> None:
        self.attempts = 0

    def context(self):
        outer = self

        class Context:
            async def __aenter__(self):
                outer.attempts += 1
                raise AssertionError("bearer authentication entered a database context")

            async def __aexit__(self, *exc):
                return False

        return Context()

    def dependency(self):
        self.attempts += 1
        raise AssertionError("bearer authentication requested a database session")


@pytest.fixture
def bearer_app(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage", StorageSettings(local=LocalStorageSettings(root=tmp_path)))
    monkeypatch.setattr(settings, "jwk", JwkSettings(key_path="auth/jwks.json"))
    monkeypatch.setattr(jwk_service, "_keyset", None)
    monkeypatch.setattr(jwk_service, "_last_fetch_time", None)
    monkeypatch.setattr(jwk_service, "_keyset_lock", asyncio.Lock())
    monkeypatch.setattr(jwk_service, "_access_claims_registry", None)
    database = ForbiddenDatabase()
    app = FastAPI()
    app.dependency_overrides[get_database_context] = database.context
    app.dependency_overrides[get_database] = database.dependency

    @app.get("/browse")
    async def browse(actor: auth_service.BrowseActorDependency):
        return {"user_id": str(actor.user_id), "method": actor.authentication_method,
                "api_key_id": actor.api_key_id}

    @app.get("/admin")
    async def admin(actor: auth_service.AdminActorDependency):
        return {}

    return TestClient(app), database


def sign(claims: dict, key_set: KeySet | None = None) -> str:
    return encode({"alg": "ES256"}, claims, key_set or asyncio.run(jwk_service.get_key_set()))


def claims(**overrides) -> dict:
    now = datetime.datetime.now(datetime.timezone.utc)
    base = {
        "iss": jwk_service.TOKEN_ISSUER, "aud": jwk_service.TOKEN_AUDIENCE, "sub": "alice",
        "iat": now, "exp": now + datetime.timedelta(minutes=5),
        "scopes": auth_service.BROWSE_SCOPE, "uid": str(uuid.uuid4()),
    }
    base.update(overrides)
    return {key: value for key, value in base.items() if value is not None}


def test_valid_token_authorizes_without_database(bearer_app):
    client, database = bearer_app
    user_id = uuid.uuid4()
    token = asyncio.run(jwk_service.issue_access_token("alice", [auth_service.BROWSE_SCOPE], user_id))
    for _ in range(3):
        response = client.get("/browse", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json() == {"user_id": str(user_id), "method": "bearer", "api_key_id": None}
    assert database.attempts == 0


def test_insufficient_scope_is_rejected_without_database(bearer_app):
    client, database = bearer_app
    token = asyncio.run(jwk_service.issue_access_token("alice", [auth_service.BROWSE_SCOPE], uuid.uuid4()))
    assert client.get("/admin", headers={"Authorization": f"Bearer {token}"}).status_code == 403
    assert database.attempts == 0


def test_expired_token_is_rejected_without_database(bearer_app, monkeypatch):
    client, database = bearer_app
    token = asyncio.run(jwk_service.issue_access_token("alice", [auth_service.BROWSE_SCOPE], uuid.uuid4()))
    expires = jwk_service._now() + settings.jwk.access_token_lifetime_seconds
    monkeypatch.setattr(jwk_service, "_now", lambda: expires + 1)
    response = client.get("/browse", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert database.attempts == 0


@pytest.mark.parametrize("make_token", [
    pytest.param(lambda: None, id="missing"),
    pytest.param(lambda: "not-a-jwt", id="malformed"),
    pytest.param(lambda: sign(claims(), KeySet([ECKey.generate_key(
        "P-256", parameters={"alg": "ES256", "kid": next(iter(
            asyncio.run(jwk_service.get_key_set()).keys)).kid}),
    ])), id="wrong-signature"),
    pytest.param(lambda: sign(claims(iss="https://elsewhere.test")), id="issuer"),
    pytest.param(lambda: sign(claims(aud="elsewhere")), id="audience"),
    pytest.param(lambda: sign(claims(uid=None)), id="pre-uid-token"),
    pytest.param(lambda: sign(claims(uid="not-a-uuid")), id="malformed-uid"),
    pytest.param(lambda: sign(claims(uid=42)), id="non-string-uid"),
    pytest.param(lambda: sign(claims(scopes=["people-gator:browse"])), id="non-string-scopes"),
    pytest.param(lambda: sign(claims(sub=None)), id="missing-subject"),
])
def test_invalid_tokens_are_rejected_without_database(bearer_app, make_token):
    client, database = bearer_app
    token = make_token()
    headers = {} if token is None else {"Authorization": f"Bearer {token}"}
    response = client.get("/browse", headers=headers)
    assert response.status_code == 401
    assert database.attempts == 0
