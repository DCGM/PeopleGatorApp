import time
import httpx
from joserfc.jwk import (
    KeySet,
    KeySetSerialization,
)

_keyset: KeySet | None = None
_last_fetch_time: float | None = None


async def get_key_set() -> KeySet:
    global _keyset, _last_fetch_time
    now = time.monotonic()
    if (
        _keyset is not None
        and _last_fetch_time is not None
        and now - _last_fetch_time < 3600
    ):
        return _keyset
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://example.com/.well-known/jwks.json", timeout=10.0
        )
        response.raise_for_status()
        jwks_data: KeySetSerialization = response.json()
    _keyset = KeySet.import_key_set(jwks_data)
    _last_fetch_time = now
    return _keyset
