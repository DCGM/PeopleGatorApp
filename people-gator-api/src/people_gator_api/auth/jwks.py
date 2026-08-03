import asyncio
import time

import httpx
from joserfc.jwk import (
    KeySet,
    KeySetSerialization,
)


class JwksCache:
    """Fetches and caches a JWKS key set from a remote URI with TTL-based refresh."""

    def __init__(self, jwks_uri: str, ttl: float = 3600.0) -> None:
        super().__init__()
        self._jwks_uri = jwks_uri
        self._ttl = ttl
        self._key_set: KeySet | None = None
        self._fetched_at: float = 0.0
        self._lock: asyncio.Lock = asyncio.Lock()

    async def get_key_set(self) -> KeySet:
        now = time.monotonic()
        if self._key_set is not None and (now - self._fetched_at) < self._ttl:
            return self._key_set
        async with self._lock:
            # Re-check after acquiring lock — another coroutine may have refreshed first.
            now = time.monotonic()
            if self._key_set is not None and (now - self._fetched_at) < self._ttl:
                return self._key_set
            async with httpx.AsyncClient() as client:
                response = await client.get(self._jwks_uri, timeout=10.0)
                response.raise_for_status()
                jwks_data: KeySetSerialization = response.json()
            self._key_set = KeySet.import_key_set(jwks_data)
            self._fetched_at = time.monotonic()
            return self._key_set

    def invalidate(self) -> None:
        """Force the next call to re-fetch — useful when a token fails due to key rotation."""
        self._fetched_at = 0.0
