import uuid
from dataclasses import dataclass
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from joserfc.jwk import KeySet
from sqlalchemy.ext.asyncio import AsyncSession

from people_gator_api.db.models.enums import PrincipalType
from people_gator_api.db.models.principal import User
from people_gator_api.services import authz


@dataclass
class _DecodedToken:
    claims: dict[str, object]


class _StaticJwksCache:
    async def get_key_set(self) -> KeySet:
        return KeySet([])


def _decode_with_claims(claims: dict[str, object]):
    def _decode(_token: str, _key_set: KeySet) -> _DecodedToken:
        return _DecodedToken(claims=claims)

    return _decode


def _validate_claims(_claims: object) -> None:
    return None


def _detail_dict(exc: HTTPException) -> dict[str, object]:
    assert isinstance(exc.detail, dict)
    return exc.detail


@pytest.mark.asyncio
async def test_resolve_principal_accepts_matching_audience(monkeypatch: pytest.MonkeyPatch) -> None:
    session = Mock(spec=AsyncSession)
    monkeypatch.setattr(authz.settings.keycloak, "audience", "people-gator-api")

    user = User(
        principal_id=uuid.uuid4(),
        principal_type=PrincipalType.user,
        display_name="alice",
        is_active=True,
        external_subject="sub-1",
        external_issuer="https://issuer.example.com",
        email="alice@example.com",
    )

    monkeypatch.setattr(authz, "_jwks_cache", _StaticJwksCache())
    monkeypatch.setattr(
        authz.jwt,
        "decode",
        _decode_with_claims(
            {
                "iss": authz.settings.keycloak.issuer,
                "sub": "sub-1",
                "aud": ["people-gator-api"],
                "scope": "people-gator:browse",
                "preferred_username": "alice",
            }
        ),
    )
    monkeypatch.setattr(authz, "_claims_registry", Mock(validate=_validate_claims))
    monkeypatch.setattr(authz.User, "get_or_create", AsyncMock(return_value=(user, False)))

    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="valid-token")
    context = await authz.get_auth_context(credentials=credentials, session=session)

    assert context.principal is user
    assert "people-gator:browse" in context.scopes


@pytest.mark.asyncio
async def test_resolve_principal_rejects_wrong_audience(monkeypatch: pytest.MonkeyPatch) -> None:
    session = Mock(spec=AsyncSession)
    monkeypatch.setattr(authz.settings.keycloak, "audience", "people-gator-api")

    monkeypatch.setattr(authz, "_jwks_cache", _StaticJwksCache())
    monkeypatch.setattr(
        authz.jwt,
        "decode",
        _decode_with_claims(
            {
                "iss": authz.settings.keycloak.issuer,
                "sub": "sub-1",
                "aud": ["some-other-service"],
            }
        ),
    )
    monkeypatch.setattr(authz, "_claims_registry", Mock(validate=_validate_claims))

    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="valid-token")

    with pytest.raises(HTTPException) as exc_info:
        await authz.get_auth_context(credentials=credentials, session=session)

    detail = _detail_dict(exc_info.value)

    assert exc_info.value.status_code == 401
    assert detail["code"] == "token_invalid"
    assert detail["message"] == "Token audience not accepted"


@pytest.mark.asyncio
async def test_resolve_principal_rejects_when_audience_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Mock(spec=AsyncSession)

    monkeypatch.setattr(authz, "_jwks_cache", _StaticJwksCache())
    monkeypatch.setattr(
        authz.jwt,
        "decode",
        _decode_with_claims(
            {
                "iss": authz.settings.keycloak.issuer,
                "sub": "sub-1",
                "aud": ["people-gator-api"],
            }
        ),
    )
    monkeypatch.setattr(authz, "_claims_registry", Mock(validate=_validate_claims))
    monkeypatch.setattr(authz.settings.keycloak, "audience", None)

    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="valid-token")

    with pytest.raises(HTTPException) as exc_info:
        await authz.get_auth_context(credentials=credentials, session=session)

    detail = _detail_dict(exc_info.value)

    assert exc_info.value.status_code == 500
    assert detail["code"] == "server_misconfigured"
    assert detail["message"] == "Token audience is not configured"
