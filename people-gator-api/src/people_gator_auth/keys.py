import os
import asyncio
import time
import json
import uuid
from joserfc.jwk import (
    ECKey,
    KeySet,
)
from joserfc.jwt import encode
from people_gator_auth.settings import settings


_keyset: KeySet | None = None
_last_fetch_time: float | None = None
_last_key_miss_refresh_time: float | None = None
_keyset_lock = asyncio.Lock()
_KEY_MISS_REFRESH_INTERVAL_SECONDS = 5


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
        and now - _last_fetch_time < settings.key_cache_ttl_seconds
        and not _should_refresh_for_key_miss(refresh_if, now)
    ):
        return _keyset
    async with _keyset_lock:
        now = time.monotonic()
        # A concurrent caller may have populated the cache while we waited.
        if (
            _keyset is not None
            and _last_fetch_time is not None
            and now - _last_fetch_time < settings.key_cache_ttl_seconds
            and not _should_refresh_for_key_miss(refresh_if, now)
        ):
            return _keyset
        path = settings.state_dir / "jwks.json"
        try:
            jwks_data = json.loads(path.read_text())
        except FileNotFoundError:
            path.parent.mkdir(parents=True, exist_ok=True)
            key = ECKey.generate_key("P-256", parameters={"alg": "ES256", "use": "sig"}, auto_kid=True)
            jwks_data = KeySet([key]).as_dict(private=True)
            # Exclusive creation prevents concurrent first starts replacing a key.
            try:
                with os.fdopen(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "w") as stream:
                    json.dump(jwks_data, stream)
            except FileExistsError:
                jwks_data = json.loads(path.read_text())
        _keyset = KeySet.import_key_set(jwks_data)
        _last_fetch_time = time.monotonic()
        if refresh_if is not None:
            _last_key_miss_refresh_time = _last_fetch_time
        return _keyset

def _now() -> int:
    return int(time.time())


def access_token(key_set, subject: str, scopes: list[str], user_id: uuid.UUID, *, scope: str = ""):
    now = _now()
    key = key_set.keys[0]
    return encode({"alg": "ES256", "kid": key.kid, "typ": "at+jwt"}, {
        "iss": settings.issuer, "aud": settings.audience, "sub": subject,
        "iat": now, "exp": now + settings.access_token_lifetime_seconds,
        "scopes": " ".join(sorted(scopes)), "scope": scope,
        "uid": str(user_id), "token_use": "access",
    }, key)


async def issue_access_token(subject: str, scopes: list[str], user_id: uuid.UUID):
    return access_token(await get_key_set(), subject, scopes, user_id)
