import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock

import argon2
import pytest
from botocore.exceptions import ClientError
from fastapi import HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import ValidationError

from people_gator_api.filesystem.local import LocalFilesystem
from people_gator_api.schemas.auth import TokenResponse
from people_gator_api.schemas.users import UserCreateRequest, UserResponse
from people_gator_api.services import auth_service, jwk_service
from people_gator_api.settings import (
    JwkSettings, LocalStorageSettings, Settings, StorageSettings, settings,
)


class FakeUsers:
    """Identity store with the get-or-create contract used at token issuance."""

    def __init__(self) -> None:
        self.records: dict[tuple[str, str], UserResponse] = {}
        self.entries = 0

    async def get_or_create(self, payload: UserCreateRequest) -> UserResponse:
        key = (payload.external_issuer, payload.external_subject)
        if key not in self.records:
            self.records[key] = UserResponse(
                user_id=uuid.uuid4(), email=None, **payload.model_dump(),
            )
        return self.records[key]

    def set_active(self, subject: str, active: bool) -> None:
        key = (settings.jwk.issuer, subject)
        self.records[key] = self.records[key].model_copy(update={"is_active": active})

    def context(self):
        @asynccontextmanager
        async def database():
            self.entries += 1
            yield self
        return database()

    @property
    def users(self) -> "FakeUsers":
        return self


fake_users = FakeUsers()


async def refresh(refresh_token: str) -> TokenResponse:
    return await auth_service.refresh_access_token(refresh_token, fake_users.context())


@pytest.fixture
def users_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    global fake_users
    fake_users = FakeUsers()
    monkeypatch.setattr(settings, "storage", StorageSettings(
        local=LocalStorageSettings(root=tmp_path),
    ))
    monkeypatch.setattr(settings, "jwk", JwkSettings(
        users_path="auth/custom-users.json", key_path="auth/jwks.json",
    ))
    monkeypatch.setattr(auth_service, "_refresh_sessions", {})
    monkeypatch.setattr(auth_service, "_refresh_session_locks", {})
    monkeypatch.setattr(jwk_service, "_keyset", None)
    monkeypatch.setattr(jwk_service, "_last_fetch_time", None)
    monkeypatch.setattr(jwk_service, "_keyset_lock", asyncio.Lock())
    path = tmp_path / settings.jwk.users_path
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({
        "alice": {
            "hash": argon2.PasswordHasher().hash("secret"),
            "scopes": [auth_service.BROWSE_SCOPE, auth_service.ANNOTATE_SCOPE],
        },
        "bob": {"hash": "unused", "scopes": []},
    }))
    return path


async def login(
    username: str = "alice", password: str = "secret",
    scope: str = auth_service.BROWSE_SCOPE,
) -> TokenResponse:
    return await auth_service.get_token(OAuth2PasswordRequestForm(
        username=username, password=password, scope=scope,
    ), fake_users.context())


def test_users_path_environment_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PEOPLE_GATOR_API__JWK__USERS_PATH", "custom/users.json")
    configured = Settings(
        _env_file=None,  # type: ignore[reportCallIssue]
        persistence={"postgres": {
            "host": "localhost", "port": 5432, "user": "test",
            "password": "test", "database": "test",
        }},
        storage={"local": {}},
    )
    assert configured.jwk.users_path == "custom/users.json"
    assert JwkSettings().users_path == "peoplegator_api/users.json"
    with pytest.raises(ValidationError):
        JwkSettings(users_path="")


@pytest.mark.asyncio
async def test_login_and_refresh_keep_users_file_unchanged(users_file: Path) -> None:
    before = users_file.read_bytes()
    token = await login()
    claims = await jwk_service.verify_access_token(token.access_token)
    assert claims["sub"] == "alice"
    assert claims["scopes"] == [auth_service.BROWSE_SCOPE]
    original_jti = (await jwk_service.verify_refresh_token(token.refresh_token))["jti"]
    refreshed = await refresh(token.refresh_token)
    refreshed_claims = await jwk_service.verify_access_token(refreshed.access_token)
    assert refreshed_claims["sub"] == "alice"
    assert refreshed_claims["scopes"] == [auth_service.BROWSE_SCOPE]
    new_jti = (await jwk_service.verify_refresh_token(refreshed.refresh_token))["jti"]
    assert original_jti != new_jti
    with pytest.raises(HTTPException) as expired:
        await refresh(token.refresh_token)
    assert expired.value.status_code == 401
    assert users_file.read_bytes() == before


@pytest.mark.asyncio
async def test_refresh_sessions_do_not_survive_restart(
    users_file: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = users_file.read_bytes()
    token = await login()
    monkeypatch.setattr(auth_service, "_refresh_sessions", {})
    monkeypatch.setattr(auth_service, "_refresh_session_locks", {})
    with pytest.raises(HTTPException) as expired:
        await refresh(token.refresh_token)
    assert expired.value.status_code == 401
    assert users_file.read_bytes() == before


@pytest.mark.asyncio
@pytest.mark.parametrize("username,password,scope,code", [
    ("alice", "wrong", auth_service.BROWSE_SCOPE, 401),
    ("unknown", "secret", auth_service.BROWSE_SCOPE, 401),
    ("alice", "secret", "unknown:scope", 403),
    ("alice", "secret", auth_service.ADMIN_SCOPE, 403),
    ("alice", "secret", f"{auth_service.BROWSE_SCOPE} {auth_service.INGEST_SCOPE}", 403),
])
async def test_rejected_login_does_not_modify_users(
    users_file: Path, username: str, password: str, scope: str, code: int,
) -> None:
    before = users_file.read_bytes()
    with pytest.raises(HTTPException) as rejected:
        await login(username, password, scope)
    assert rejected.value.status_code == code
    assert users_file.read_bytes() == before


@pytest.mark.asyncio
async def test_users_can_request_allowed_scopes(users_file: Path) -> None:
    scopes = [auth_service.BROWSE_SCOPE, auth_service.ANNOTATE_SCOPE]
    token = await login(scope=" ".join(scopes))
    assert (await jwk_service.verify_access_token(token.access_token))["scopes"] == scopes


@pytest.mark.asyncio
async def test_login_observes_allowed_scope_changes(users_file: Path) -> None:
    users = json.loads(users_file.read_text())
    users["alice"]["scopes"] = sorted(auth_service.KNOWN_SCOPES)
    users_file.write_text(json.dumps(users))
    token = await login(scope=auth_service.ADMIN_SCOPE)
    assert (await jwk_service.verify_access_token(token.access_token))["scopes"] == [auth_service.ADMIN_SCOPE]


@pytest.mark.asyncio
async def test_session_limit_and_concurrent_logins(users_file: Path) -> None:
    first = await login()
    tokens = await asyncio.gather(*(login() for _ in range(4)))
    with pytest.raises(HTTPException) as evicted:
        await refresh(first.refresh_token)
    assert evicted.value.status_code == 401
    for token in tokens:
        refreshed = await refresh(token.refresh_token)
        assert (await jwk_service.verify_access_token(refreshed.access_token))["sub"] == "alice"


@pytest.mark.asyncio
async def test_concurrent_refresh_only_succeeds_once(
    users_file: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = await login()
    original_sign = auth_service.issue_refresh_token
    both_signing = asyncio.Event()
    signing_count = 0

    async def sign_together(subject: str, scopes: list[str], jti: str) -> str:
        nonlocal signing_count
        signing_count += 1
        if signing_count == 2:
            both_signing.set()
        await both_signing.wait()
        return await original_sign(subject=subject, scopes=scopes, jti=jti)

    monkeypatch.setattr(auth_service, "issue_refresh_token", sign_together)
    async with asyncio.timeout(5):
        results = await asyncio.gather(
            refresh(token.refresh_token),
            refresh(token.refresh_token),
            return_exceptions=True,
        )
    failures = [result for result in results if isinstance(result, HTTPException)]
    assert len(failures) == 1
    assert failures[0].status_code == 401
    assert sum(isinstance(result, TokenResponse) for result in results) == 1


@pytest.mark.asyncio
async def test_login_signs_before_user_lock_and_other_users_proceed(
    users_file: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    users = json.loads(users_file.read_text())
    users["bob"] = users["alice"]
    users_file.write_text(json.dumps(users))
    locks = {"alice": asyncio.Lock()}
    monkeypatch.setattr(auth_service, "_refresh_session_locks", locks)
    alice_signed = asyncio.Event()
    original_sign = auth_service.issue_refresh_token

    async def record_signing(subject: str, scopes: list[str], jti: str) -> str:
        token = await original_sign(subject=subject, scopes=scopes, jti=jti)
        if subject == "alice":
            alice_signed.set()
        return token

    monkeypatch.setattr(auth_service, "issue_refresh_token", record_signing)
    async with asyncio.timeout(5):
        async with asyncio.TaskGroup() as tasks:
            async with locks["alice"]:
                alice_login = tasks.create_task(login())
                await alice_signed.wait()
                assert not alice_login.done()
                bob_token = await login(username="bob")
                assert (await jwk_service.verify_access_token(bob_token.access_token))["sub"] == "bob"
    assert (await jwk_service.verify_access_token(alice_login.result().access_token))["sub"] == "alice"


@pytest.mark.asyncio
async def test_refresh_does_not_restore_session_evicted_while_signing(
    users_file: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = await login()
    for _ in range(3):
        await login()
    signing_started = asyncio.Event()
    resume_signing = asyncio.Event()
    original_sign = auth_service.issue_refresh_token
    pause_next_sign = True

    async def pause_signing(subject: str, scopes: list[str], jti: str) -> str:
        nonlocal pause_next_sign
        if pause_next_sign:
            pause_next_sign = False
            signing_started.set()
            await resume_signing.wait()
        return await original_sign(subject=subject, scopes=scopes, jti=jti)

    monkeypatch.setattr(auth_service, "issue_refresh_token", pause_signing)

    async def refresh_result() -> TokenResponse | HTTPException:
        try:
            return await refresh(first.refresh_token)
        except HTTPException as exc:
            return exc

    async with asyncio.timeout(5):
        async with asyncio.TaskGroup() as tasks:
            refreshing = tasks.create_task(refresh_result())
            await signing_started.wait()
            latest = await login()
            resume_signing.set()
    result = refreshing.result()
    assert isinstance(result, HTTPException)
    assert result.status_code == 401
    assert (await refresh(latest.refresh_token)).access_token


@pytest.mark.asyncio
async def test_concurrent_first_logins_share_signing_keys(users_file: Path) -> None:
    users = json.loads(users_file.read_text())
    users["bob"] = users["alice"]
    users_file.write_text(json.dumps(users))
    alice, bob = await asyncio.gather(login(), login(username="bob"))
    assert (await jwk_service.verify_access_token(alice.access_token))["sub"] == "alice"
    assert (await jwk_service.verify_access_token(bob.access_token))["sub"] == "bob"


@pytest.mark.asyncio
async def test_refresh_observes_user_removal(users_file: Path) -> None:
    token = await login()
    users = json.loads(users_file.read_text())
    del users["alice"]
    users_file.write_text(json.dumps(users))
    before = users_file.read_bytes()
    with pytest.raises(HTTPException) as rejected:
        await refresh(token.refresh_token)
    assert rejected.value.status_code == 401
    assert users_file.read_bytes() == before


@pytest.mark.asyncio
async def test_login_observes_password_hash_changes(users_file: Path) -> None:
    users = json.loads(users_file.read_text())
    users["alice"]["hash"] = argon2.PasswordHasher().hash("new-secret")
    users_file.write_text(json.dumps(users))
    with pytest.raises(HTTPException) as rejected:
        await login()
    assert rejected.value.status_code == 401
    assert (await login(password="new-secret")).access_token


@pytest.mark.asyncio
@pytest.mark.parametrize("scopes", [[], [auth_service.ANNOTATE_SCOPE]])
async def test_refresh_rejects_revoked_scopes(users_file: Path, scopes: list[str]) -> None:
    token = await login()
    users = json.loads(users_file.read_text())
    users["alice"]["scopes"] = scopes
    users_file.write_text(json.dumps(users))
    before = users_file.read_bytes()
    with pytest.raises(HTTPException) as rejected:
        await refresh(token.refresh_token)
    assert rejected.value.status_code == 403
    assert users_file.read_bytes() == before


@pytest.mark.asyncio
async def test_refresh_preserves_requested_scopes_when_permissions_expand(users_file: Path) -> None:
    token = await login()
    users = json.loads(users_file.read_text())
    users["alice"]["scopes"] = sorted(auth_service.KNOWN_SCOPES)
    users_file.write_text(json.dumps(users))
    refreshed = await refresh(token.refresh_token)
    assert (await jwk_service.verify_access_token(refreshed.access_token))["scopes"] == [auth_service.BROWSE_SCOPE]


@pytest.mark.asyncio
async def test_missing_file_initializes_without_default_account(users_file: Path) -> None:
    users_file.unlink()
    with pytest.raises(HTTPException) as rejected:
        await login("test")
    assert rejected.value.status_code == 401
    assert json.loads(users_file.read_text()) == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("data", [
    b"invalid json", b'{"alice": {"scopes": []}}',
    b'{"alice": {"hash": "unused"}}', b'{"alice": {"hash": "unused", "scopes": "all"}}',
])
async def test_invalid_file_is_not_overwritten(users_file: Path, data: bytes) -> None:
    users_file.write_bytes(data)
    with pytest.raises(ValidationError):
        await login()
    assert users_file.read_bytes() == data


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["NoSuchKey", "404", "NotFound", "AccessDenied"])
async def test_s3_missing_file_and_storage_errors(
    users_file: Path, monkeypatch: pytest.MonkeyPatch, code: str,
) -> None:
    filesystem = AsyncMock(spec=LocalFilesystem)
    filesystem.read_bytes.side_effect = ClientError({"Error": {"Code": code}}, "GetObject")
    monkeypatch.setattr(auth_service, "get_filesystem", lambda: filesystem)
    if code == "AccessDenied":
        with pytest.raises(ClientError):
            await login()
        filesystem.write_bytes.assert_not_awaited()
    else:
        with pytest.raises(HTTPException) as rejected:
            await login()
        assert rejected.value.status_code == 401
        filesystem.write_bytes.assert_awaited_once_with(settings.jwk.users_path, b"{}")


@pytest.mark.asyncio
async def test_tokens_carry_the_persisted_user_uuid(users_file: Path) -> None:
    token = await login()
    user = fake_users.records[(settings.jwk.issuer, "alice")]
    assert user.is_active
    assert (await jwk_service.verify_access_token(token.access_token))["uid"] == user.user_id
    refreshed = await refresh(token.refresh_token)
    assert (await jwk_service.verify_access_token(refreshed.access_token))["uid"] == user.user_id
    assert len(fake_users.records) == 1


@pytest.mark.asyncio
async def test_inactive_user_cannot_log_in_and_is_not_reactivated(users_file: Path) -> None:
    await login()
    fake_users.set_active("alice", False)
    with pytest.raises(HTTPException) as rejected:
        await login()
    assert rejected.value.status_code == 403
    assert not fake_users.records[(settings.jwk.issuer, "alice")].is_active
    assert len(auth_service._refresh_sessions["alice"]) == 1


@pytest.mark.asyncio
async def test_disabling_between_login_and_refresh_revokes_the_session(users_file: Path) -> None:
    token = await login()
    fake_users.set_active("alice", False)
    with pytest.raises(HTTPException) as rejected:
        await refresh(token.refresh_token)
    assert rejected.value.status_code == 403
    assert auth_service._refresh_sessions["alice"] == {}
    # The original access token remains valid until it expires.
    assert (await jwk_service.verify_access_token(token.access_token))["sub"] == "alice"
    fake_users.set_active("alice", True)
    with pytest.raises(HTTPException) as revoked:
        await refresh(token.refresh_token)
    assert revoked.value.status_code == 401


@pytest.mark.asyncio
async def test_rejected_credentials_do_not_resolve_identities(users_file: Path) -> None:
    for username, password, scope in (
        ("alice", "wrong", auth_service.BROWSE_SCOPE),
        ("alice", "secret", auth_service.ADMIN_SCOPE),
    ):
        with pytest.raises(HTTPException):
            await login(username, password, scope)
    assert fake_users.entries == 0
    assert fake_users.records == {}


@pytest.mark.asyncio
async def test_access_token_lifetime_is_configurable(
    users_file: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings.jwk, "access_token_lifetime_seconds", 60)
    token = await login()
    claims = await jwk_service.verify_access_token(token.access_token)
    assert claims["exp"] - claims["iat"] == 60
    monkeypatch.setattr(jwk_service, "_now", lambda: claims["exp"] + 1)
    monkeypatch.setattr(jwk_service, "_access_claims_registry", None)
    with pytest.raises(HTTPException) as expired:
        await jwk_service.verify_access_token(token.access_token)
    assert expired.value.status_code == 401
