"""Provider-owned accounts and rotating, process-local refresh sessions."""
import asyncio
import uuid
import argon2
from fastapi import HTTPException
from pydantic import BaseModel, Field, TypeAdapter
from people_gator_api.auth.settings import settings
from people_gator_api.auth.keys import issue_access_token, issue_refresh_token, verify_refresh_token
from people_gator_api.services.auth_scopes import KNOWN_SCOPES


class Account(BaseModel):
    hash: str = Field(repr=False)
    scopes: set[str]
    user_id: uuid.UUID
    is_active: bool = True


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


_adapter = TypeAdapter(dict[str, Account])
_sessions: dict[str, dict[str, list[str]]] = {}
_lock = asyncio.Lock()


def accounts() -> dict[str, Account]:
    # Reread on every exchange: account removal/disablement takes effect immediately.
    return _adapter.validate_json((settings.state_dir / "accounts.json").read_bytes())


def allowed(username: str, scopes: list[str]) -> Account:
    account = accounts().get(username)
    if account is None or not account.is_active:
        raise HTTPException(403, "Account unavailable")
    if not set(scopes) <= account.scopes or not set(scopes) <= KNOWN_SCOPES:
        raise HTTPException(403, "Not enough permissions")
    return account


async def exchange(username: str, scopes: list[str]) -> TokenResponse:
    account = allowed(username, scopes)
    access = await issue_access_token(username, scopes, account.user_id)
    jti = str(uuid.uuid4())
    refresh = await issue_refresh_token(username, scopes, jti)
    sessions = _sessions.setdefault(username, {})
    sessions[jti] = scopes
    if len(sessions) > 4:
        del sessions[next(iter(sessions))]
    return TokenResponse(access_token=access, refresh_token=refresh)


async def login(username: str, password: str, scopes: list[str]) -> TokenResponse:
    account = accounts().get(username)
    try:
        valid = account is not None and argon2.PasswordHasher().verify(account.hash, password)
    except argon2.exceptions.VerificationError:
        valid = False
    if not valid:
        raise HTTPException(401, "Invalid username or password")
    async with _lock:
        return await exchange(username, scopes or sorted(account.scopes))


async def refresh(token: str) -> TokenResponse:
    claims = await verify_refresh_token(token)
    async with _lock:
        sessions = _sessions.get(claims["sub"], {})
        scopes = sessions.pop(claims["jti"], None)
        if scopes is None:
            raise HTTPException(401, "Session expired")
        return await exchange(claims["sub"], scopes)


async def logout(token: str) -> None:
    claims = await verify_refresh_token(token)
    async with _lock:
        _sessions.get(claims["sub"], {}).pop(claims["jti"], None)
