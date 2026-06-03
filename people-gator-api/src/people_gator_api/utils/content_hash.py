"""BLAKE3 content hashing utilities.

All content hashes stored in the DB are BLAKE3 256-bit digests encoded as
lowercase hex strings (64 characters).
"""

import json

import blake3


def compute_hash(data: bytes) -> str:
    """Return the BLAKE3 hex digest of *data*."""
    return blake3.blake3(data).hexdigest()


def compute_json_hash(payload: dict[str, object]) -> str:
    """Return the BLAKE3 hex digest of a JSON-serialised mapping.

    Keys are sorted for stability so that two semantically identical dicts
    produce the same hash regardless of key insertion order.
    """
    serialised = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return compute_hash(serialised)
