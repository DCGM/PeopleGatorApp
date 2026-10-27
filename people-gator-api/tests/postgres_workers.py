"""Give each xdist worker private stores, including destructive schema tests."""

import asyncio
from contextlib import contextmanager
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool


async def database_command(url: str, statement: str) -> None:
    # CREATE/DROP DATABASE cannot run in a transaction. No pooled connections
    # cross asyncio.run() event loops or keep a database alive during cleanup.
    engine = create_async_engine(url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            await connection.execute(text(statement))
    finally:
        await engine.dispose()


@contextmanager
def worker_databases(urls: dict[str, str]):
    """Create empty databases; always remove only the names allocated here.

    Owned by the controller so even a crashed/restarted worker is cleaned up.
    The supplied disposable databases are connection targets, never reset.
    """
    created: list[tuple[str, str]] = []
    allocated: dict[str, str] = {}
    try:
        for variable, original in urls.items():
            name = "pytest_worker_" + uuid4().hex
            asyncio.run(database_command(original, f'CREATE DATABASE "{name}"'))
            created.append((original, name))
            allocated[variable] = make_url(original).set(database=name).render_as_string(
                hide_password=False
            )
        yield allocated
    finally:
        # Try every cleanup even if one fails. FORCE also handles a dead worker's
        # leftover connections; it never targets the caller's original store.
        errors = []
        for original, name in reversed(created):
            try:
                asyncio.run(database_command(original, f'DROP DATABASE "{name}" WITH (FORCE)'))
            except Exception as error:
                errors.append(error)
        if errors:
            raise ExceptionGroup("Could not remove private pytest databases", errors)
