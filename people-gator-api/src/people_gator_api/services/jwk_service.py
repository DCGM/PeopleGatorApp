import asyncio
import datetime
import time
import json
import uuid
import logging
from typing import Any
from botocore.exceptions import ClientError
from fastapi import HTTPException
from joserfc.errors import ClaimError, InvalidKeyIdError, JoseError
from joserfc.jwk import (
    ECKey,
    KeySet,
    KeySetSerialization,
)
from joserfc.jws import JWSRegistry
from joserfc.jwt import ClaimsOption, JWTClaimsRegistry, Token, encode, decode
from starlette import status
from people_gator_api.services.filesystem_service import open_file
from people_gator_api.settings import settings


logger = logging.getLogger(__name__)

_keyset: KeySet | None = None
_last_fetch_time: float | None = None
_last_key_miss_refresh_time: float | None = None
_keyset_lock = asyncio.Lock()
_KEY_MISS_REFRESH_INTERVAL_SECONDS = 5

TOKEN_ISSUER = settings.jwk.issuer
TOKEN_AUDIENCE = settings.jwk.audience

def _should_refresh_for_key_miss(refresh_if: KeySet | None, now: float) -> bool:
    # Unknown key IDs are untrusted; bound how often they can trigger storage I/O.
    return refresh_if is _keyset and (
        _last_key_miss_refresh_time is None
        or now - _last_key_miss_refresh_time >= _KEY_MISS_REFRESH_INTERVAL_SECONDS
    )


async def get_key_set(*, refresh_if: KeySet | None = None) -> KeySet:
    """Load signing keys, optionally refreshing the caller's cached key set."""
    global _keyset, _last_fetch_time, _last_key_miss_refresh_time
    now = time.monotonic()
    if (
        _keyset is not None
        and _last_fetch_time is not None
        and now - _last_fetch_time < settings.jwk.key_cache_ttl_seconds
        and not _should_refresh_for_key_miss(refresh_if, now)
    ):
        return _keyset
    async with _keyset_lock:
        now = time.monotonic()
        # A concurrent caller may have populated the cache while we waited.
        if (
            _keyset is not None
            and _last_fetch_time is not None
            and now - _last_fetch_time < settings.jwk.key_cache_ttl_seconds
            and not _should_refresh_for_key_miss(refresh_if, now)
        ):
            return _keyset
        try:
            async with open_file(settings.jwk.key_path, mode="r") as f:
                jwks_data: KeySetSerialization = json.load(f)
        except (FileNotFoundError, ClientError) as exc:
            if isinstance(exc, ClientError) and exc.response.get("Error", {}).get("Code") not in (
                "NoSuchKey", "404", "NotFound",
            ):
                raise
            logger.warning("JWK key set is not available at %s.", settings.jwk.key_path)
            logger.warning("Generating a new ES256 JWK key set at %s.", settings.jwk.key_path)
            key = ECKey.generate_key(
                "P-256", parameters={"alg": "ES256", "use": "sig"}, auto_kid=True,
            )
            jwks_data = KeySet([key]).as_dict(private=True)
            async with open_file(settings.jwk.key_path, mode="w") as f:
                json.dump(jwks_data, f)
        _keyset = KeySet.import_key_set(jwks_data)
        _last_fetch_time = time.monotonic()
        if refresh_if is not None:
            _last_key_miss_refresh_time = _last_fetch_time
        return _keyset

def _now_datetime() -> datetime.datetime:
    """Return the current UTC time as a datetime object."""
    return datetime.datetime.now(datetime.timezone.utc)

def _now() -> int:
    """Return the current UTC time as a Unix timestamp."""
    return int(_now_datetime().timestamp())


_access_claims_registry: JWTClaimsRegistry | None = None
_refresh_claims_registry: JWTClaimsRegistry | None = None

async def get_access_claims_registry() -> JWTClaimsRegistry:
    global _access_claims_registry
    if _access_claims_registry is not None:
        return _access_claims_registry
    _access_claims_registry = JWTClaimsRegistry(
        now=_now,
        leeway=0,
        iss=ClaimsOption(value=TOKEN_ISSUER, essential=True),
        aud=ClaimsOption(value=TOKEN_AUDIENCE, essential=True),
        sub=ClaimsOption(allow_blank=False, essential=True),
        scopes=ClaimsOption(allow_blank=False, essential=True),
        uid=ClaimsOption(allow_blank=False, essential=True),
    )
    return _access_claims_registry


async def get_refresh_claims_registry() -> JWTClaimsRegistry:
    global _refresh_claims_registry
    if _refresh_claims_registry is not None:
        return _refresh_claims_registry
    _refresh_claims_registry = JWTClaimsRegistry(
        now=_now,
        leeway=0,
        iss=ClaimsOption(value=TOKEN_ISSUER, essential=True),
        aud=ClaimsOption(value=TOKEN_AUDIENCE, essential=True),
        sub=ClaimsOption(allow_blank=False, essential=True),
        scopes=ClaimsOption(allow_blank=False, essential=True),
        jti=ClaimsOption(allow_blank=False, essential=True),
    )
    return _refresh_claims_registry


_jws_registry: JWSRegistry | None = None

async def get_jws_registry() -> JWSRegistry:
    global _jws_registry
    if _jws_registry is not None:
        return _jws_registry
    _jws_registry = JWSRegistry(algorithms=["ES256"])
    return _jws_registry


async def issue_access_token(
    subject: str,
    scopes: list[str],
    user_id: uuid.UUID,
):
    """Sign an access token carrying the persisted user UUID for attribution."""
    iss = TOKEN_ISSUER
    iat = _now_datetime()
    exp = iat + datetime.timedelta(seconds=settings.jwk.access_token_lifetime_seconds)
    aud = TOKEN_AUDIENCE
    claims = {
        "iss": iss,
        "sub": subject,
        "aud": aud,
        "iat": iat,
        "exp": exp,
        "scopes": " ".join(scopes),
        "uid": str(user_id),
    }
    protected = {"alg": "ES256"}
    key_set = await get_key_set()
    jws_registry = await get_jws_registry()
    return encode(protected, claims, key_set, registry=jws_registry)


async def issue_refresh_token(
    subject: str,
    scopes: list[str],
    jti: str,
) -> str:
    """Issue a refresh token that can be used to obtain new access tokens.
    
    Refresh tokens do not expire and include the caller-provided unique
    identifier (jti) and session_id to track concurrent sessions.
    """
    iss = TOKEN_ISSUER
    iat = _now_datetime()
    aud = TOKEN_AUDIENCE
    claims = {
        "iss": iss,
        "sub": subject,
        "aud": aud,
        "iat": iat,
        "scopes": " ".join(scopes),
        "jti": jti,
    }
    protected = {"alg": "ES256"}
    key_set = await get_key_set()
    jws_registry = await get_jws_registry()
    return encode(protected, claims, key_set, registry=jws_registry)


async def _decode_token(token: str, *, refresh: bool = False) -> Token:
    """Verify a signature, retrying once if cached keys lack the token's kid."""
    key_set = await get_key_set()
    jws_registry = await get_jws_registry()
    try:
        try:
            return decode(token, key_set, registry=jws_registry)
        except InvalidKeyIdError:
            key_set = await get_key_set(refresh_if=key_set)
            return decode(token, key_set, registry=jws_registry)
    except JoseError as exc:
        label = "refresh token" if refresh else "token"
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid {label}: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def _require_string_claims(claims: dict[str, Any], *names: str) -> None:
    for name in names:
        if not isinstance(claims.get(name), str):
            raise ClaimError(name, f"'{name}' claim must be a string")


async def verify_access_token(token: str) -> dict[str, Any]:
    """Decode and validate an access token without consulting persistence.

    ``uid`` is converted to a UUID and ``scopes`` to a list. Tokens issued
    before ``uid`` existed are rejected; clients refresh or log in again.
    """
    decoded_claims = await _decode_token(token)
    try:
        claims_registry = await get_access_claims_registry()
        claims_registry.validate(decoded_claims.claims)
        _require_string_claims(decoded_claims.claims, "sub", "iss", "scopes", "uid")
        decoded_claims.claims["uid"] = uuid.UUID(decoded_claims.claims["uid"])
        decoded_claims.claims["scopes"] = decoded_claims.claims["scopes"].split()
    except ClaimError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token claims: {str(e)}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
        )
    return decoded_claims.claims


async def verify_refresh_token(token: str) -> dict[str, Any]:
    """Decode and validate a refresh token."""
    decoded_claims = await _decode_token(token, refresh=True)
    try:
        claims_registry = await get_refresh_claims_registry()
        claims_registry.validate(decoded_claims.claims)
    except ClaimError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid refresh token claims: {str(e)}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid refresh token: {str(e)}",
        )
    return decoded_claims.claims
