"""Issuer-only durable state. Never connects to the resource database.

Transactions cover complete code/refresh exchanges, including validation and
rotation, so concurrent workers cannot redeem the same credential twice.
Opaque credentials are indexed by hashes; browser cookies contain only handles.
"""
import hashlib
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class Store:
    def __init__(self, root: Path):
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "oidc.sqlite3"
        descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(descriptor)
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS state (kind TEXT, key TEXT, payload TEXT NOT NULL, expires REAL NOT NULL, PRIMARY KEY (kind, key))")

    @contextmanager
    def transaction(self):
        with sqlite3.connect(self.path, timeout=15) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM state WHERE expires <= ?", (time.time(),))
            yield Records(db)


class Records:
    def __init__(self, db):
        self.db = db

    def put(self, kind, secret, payload, lifetime):
        self.db.execute("INSERT INTO state VALUES (?, ?, ?, ?)",
                        (kind, digest(secret), json.dumps(payload), time.time() + lifetime))

    def get(self, kind, secret):
        row = self.db.execute("SELECT payload FROM state WHERE kind = ? AND key = ? AND expires > ?",
                              (kind, digest(secret), time.time())).fetchone()
        return json.loads(row[0]) if row else None

    def delete(self, kind, secret):
        self.db.execute("DELETE FROM state WHERE kind = ? AND key = ?", (kind, digest(secret)))

    def revoke_session(self, sid):
        self.revoke_session_hash(digest(sid))

    def revoke_session_hash(self, sid_hash):
        self.db.execute("DELETE FROM state WHERE kind = 'session' AND key = ?", (sid_hash,))
        self.db.execute("DELETE FROM state WHERE kind IN ('refresh', 'code') AND json_extract(payload, '$.sid') = ?", (sid_hash,))
