"""Trusted public-JWKS consumer. Never reads issuer secrets or application storage."""
import asyncio
import time
import uuid
from collections.abc import Mapping
from typing import TypedDict
import aiohttp
from fastapi import HTTPException
from joserfc.errors import ClaimError, InvalidKeyIdError, JoseError
from joserfc.jwk import KeySet
from joserfc.jws import JWSRegistry
from joserfc.jwt import ClaimsOption, JWTClaimsRegistry, decode
from people_gator_api.settings import settings

_keyset: KeySet | None = None
_last_fetch_time: float = float("-inf")
_last_attempt: float = float("-inf")
_keyset_lock = asyncio.Lock()


async def _fetch_public_keys() -> KeySet:
    config = settings.auth
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=config.timeout_seconds)) as client:
        async with client.get(config.jwks_url, allow_redirects=False) as response:
            response.raise_for_status()
            data = await response.content.read(65537)
            if len(data) > 65536:
                raise ValueError("JWKS exceeds limit")
    import json
    jwks = json.loads(data)
    if not jwks.get("keys") or len(jwks["keys"]) > 64:
        raise ValueError("Invalid JWKS")
    for key in jwks["keys"]:
        if key.get("kty") not in ("RSA", "EC") or any(
            field in key for field in ("d", "p", "q", "dp", "dq", "qi", "oth", "k")
        ):
            raise ValueError("JWKS must contain public asymmetric keys only")
    return KeySet.import_key_set(jwks)


async def get_key_set(*, refresh_if: KeySet | None = None) -> KeySet:
    global _keyset, _last_fetch_time, _last_attempt
    config = settings.auth
    async with _keyset_lock:
        now = time.monotonic()
        fresh = _keyset is not None and now - _last_fetch_time < config.key_cache_ttl_seconds
        refresh = refresh_if is _keyset and refresh_if is not None
        if fresh and not refresh:
            return _keyset
        if now - _last_attempt < config.refresh_interval_seconds:
            if fresh:
                return _keyset
            raise HTTPException(503, "Authorization provider unavailable")
        _last_attempt = now
        try:
            keys = await _fetch_public_keys()
        except (aiohttp.ClientError, TimeoutError, ValueError, JoseError) as exc:
            if fresh:
                return _keyset
            raise HTTPException(503, "Authorization provider unavailable") from exc
        _keyset = keys
        _last_fetch_time = time.monotonic()
        return keys


def _now() -> int:
    return int(time.time())


type JSONValue = str | int | float | bool | None | list[JSONValue] | dict[str, JSONValue]


class AccessTokenClaims(TypedDict):
    """Verified access-token claims used for database-free authorization."""

    iss: str
    sub: str
    iat: int
    exp: int
    scopes: list[str]
    uid: uuid.UUID


def _string_claim(claims: Mapping[str, JSONValue], name: str) -> str:
    value = claims.get(name)
    if not isinstance(value, str):
        raise ClaimError(name, f"'{name}' claim must be a string")
    return value


def _integer_claim(claims: Mapping[str, JSONValue], name: str) -> int:
    value = claims.get(name)
    # bool is an int subclass but never a valid NumericDate.
    if not isinstance(value, int) or isinstance(value, bool):
        raise ClaimError(name, f"'{name}' claim must be an integer")
    return value


def access_token_claims(claims: Mapping[str, JSONValue]) -> AccessTokenClaims:
    """Type-check registry-validated claims; ``uid`` must be a UUID string."""
    return AccessTokenClaims(
        iss=_string_claim(claims, "iss"),
        sub=_string_claim(claims, "sub"),
        iat=_integer_claim(claims, "iat"),
        exp=_integer_claim(claims, "exp"),
        scopes=_string_claim(claims, "scopes").split(),
        uid=uuid.UUID(_string_claim(claims, "uid")),
    )



async def verify_access_token(token: str) -> AccessTokenClaims:
    config = settings.auth
    keys = await get_key_set()
    registry = JWSRegistry(algorithms=config.algorithms)
    try:
        try:
            decoded = decode(token, keys, registry=registry)
        except InvalidKeyIdError:
            decoded = decode(token, await get_key_set(refresh_if=keys), registry=registry)
        claims = dict(decoded.claims)
        claims["uid"] = claims.get(config.actor_claim)
        claims["scopes"] = claims.get(config.scopes_claim)
        JWTClaimsRegistry(
            now=_now, leeway=0,
            iss=ClaimsOption(value=config.issuer, essential=True),
            aud=ClaimsOption(value=config.audience, essential=True),
            sub=ClaimsOption(allow_blank=False, essential=True),
            exp=ClaimsOption(essential=True),
            iat=ClaimsOption(essential=True),
            uid=ClaimsOption(allow_blank=False, essential=True),
            scopes=ClaimsOption(allow_blank=False, essential=True),
        ).validate(claims)
        # Built-in refresh tokens lack uid/exp; explicit type also rejects future ones.
        if claims.get("token_use", "access") != "access" or "jti" in claims:
            raise ValueError("Not an access token")
        return access_token_claims(claims)
    except (JoseError, ValueError, TypeError, KeyError) as exc:
        raise HTTPException(401, "Invalid bearer token", headers={"WWW-Authenticate": "Bearer"}) from exc
