"""Standalone provider account policy and refresh replay guarantees."""
import asyncio
import uuid
import argon2
import pytest
from fastapi import HTTPException

pytestmark = pytest.mark.asyncio
from people_gator_api.auth import accounts, keys
from people_gator_api.auth.settings import settings
from people_gator_api.services.auth_scopes import BROWSE_SCOPE, ADMIN_SCOPE


@pytest.fixture
def issuer(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "state_dir", tmp_path)
    monkeypatch.setattr(keys, "_keyset", None)
    monkeypatch.setattr(keys, "_last_fetch_time", None)
    monkeypatch.setattr(keys, "_keyset_lock", asyncio.Lock())
    monkeypatch.setattr(accounts, "_sessions", {})
    monkeypatch.setattr(accounts, "_lock", asyncio.Lock())
    user = accounts.Account(hash=argon2.PasswordHasher().hash("password"),
                            scopes={BROWSE_SCOPE}, user_id=uuid.uuid4())
    (tmp_path / "accounts.json").write_bytes(accounts._adapter.dump_json({"alice": user}))
    return user


async def test_login_refresh_rotation_replay_and_logout(issuer):
    token = await accounts.login("alice", "password", [BROWSE_SCOPE])
    assert (await keys.verify_access_token(token.access_token))["uid"] == issuer.user_id
    renewed = await accounts.refresh(token.refresh_token)
    assert renewed.refresh_token != token.refresh_token
    with pytest.raises(HTTPException) as error:
        await accounts.refresh(token.refresh_token)
    assert error.value.status_code == 401
    await accounts.logout(renewed.refresh_token)
    with pytest.raises(HTTPException):
        await accounts.refresh(renewed.refresh_token)


async def test_concurrent_refresh_has_one_winner(issuer):
    token = await accounts.login("alice", "password", [BROWSE_SCOPE])
    results = await asyncio.gather(*(accounts.refresh(token.refresh_token) for _ in range(6)), return_exceptions=True)
    assert sum(isinstance(result, accounts.TokenResponse) for result in results) == 1


async def test_account_disable_revokes_refresh_but_not_access(issuer):
    token = await accounts.login("alice", "password", [BROWSE_SCOPE])
    issuer.is_active = False
    (settings.state_dir / "accounts.json").write_bytes(accounts._adapter.dump_json({"alice": issuer}))
    for exchange in (accounts.login("alice", "password", [BROWSE_SCOPE]), accounts.refresh(token.refresh_token)):
        with pytest.raises(HTTPException) as error:
            await exchange
        assert error.value.status_code == 403
    assert (await keys.verify_access_token(token.access_token))["uid"] == issuer.user_id


@pytest.mark.parametrize("username,password,scopes,code", [
    ("alice", "wrong", [BROWSE_SCOPE], 401), ("unknown", "password", [BROWSE_SCOPE], 401),
    ("alice", "password", [ADMIN_SCOPE], 403), ("alice", "password", ["unknown"], 403),
])
async def test_login_rejects_bad_credentials_or_scopes(issuer, username, password, scopes, code):
    with pytest.raises(HTTPException) as error:
        await accounts.login(username, password, scopes)
    assert error.value.status_code == code


async def test_four_sessions_and_restart(issuer):
    tokens = [await accounts.login("alice", "password", [BROWSE_SCOPE]) for _ in range(5)]
    with pytest.raises(HTTPException):
        await accounts.refresh(tokens[0].refresh_token)
    await accounts.refresh(tokens[1].refresh_token)
    accounts._sessions.clear()
    with pytest.raises(HTTPException):
        await accounts.refresh(tokens[-1].refresh_token)
