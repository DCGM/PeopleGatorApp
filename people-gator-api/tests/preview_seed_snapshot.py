"""Seed the preview once per worker; give each eligible case a copy of the result.

A real seed takes seconds of CPU, and most preview-seed cases start with one on
an empty migrated store. Each worker runs that fresh seed once into a template
database and storage directory. An eligible case gets ``CREATE DATABASE ...
TEMPLATE`` and a storage copy, and its first ``seed_preview`` call returns the
template's result instead of repeating the identical work. Every later call in
the case (reruns after edits, upgrades, recovery) runs the real seed.

One worker builds the template for the whole run under a file lock in the
run's shared temporary directory; the others reuse it. The pytest controller
drops it with the worker databases (it is named after the builder's database).

A case is eligible only when its body starts with
``<names> = seed_target`` followed directly by ``await
preview.seed_preview(<database>, <filesystem>)``, so nothing it does can
precede the replaced call. Cases that prepare state, patch the seed or test a
fresh run first (``@fresh_seed``) keep a real first seed.
"""

import ast
import fcntl
import inspect
import json
import os
import shutil
import textwrap
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from alembic import command
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

SCHEMA = "preview_seed"


def fresh_seed[F: Callable](case: F) -> F:
    """Run this case's first seed for real even though it starts with one."""
    case.fresh_seed = True
    return case


@cache
def starts_with_seed(function: Callable) -> bool:
    """Whether the case's first action is the seed call on its own target."""
    if getattr(function, "fresh_seed", False):
        return False
    tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
    body = [
        statement for statement in tree.body[0].body
        if not isinstance(statement, (ast.Import, ast.ImportFrom))
        and not (isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant))
    ]
    if len(body) < 2:
        return False
    unpack, first = body[:2]
    if not (
        isinstance(unpack, ast.Assign) and len(unpack.targets) == 1
        and isinstance(unpack.targets[0], ast.Tuple)
        and isinstance(unpack.value, ast.Name) and unpack.value.id == "seed_target"
    ):
        return False
    names = [ast.unparse(name) for name in unpack.targets[0].elts][:2]
    if not isinstance(first, (ast.Assign, ast.Expr)) or not isinstance(first.value, ast.Await):
        return False
    call = first.value.value
    return (
        isinstance(call, ast.Call) and ast.unparse(call.func) == "preview.seed_preview"
        and [ast.unparse(argument) for argument in call.args] == names and not call.keywords
    )


def database_url(server_url: str, database: str) -> str:
    return make_url(server_url).set(database=database).render_as_string(hide_password=False)


def schema_engine(url: str) -> AsyncEngine:
    return create_async_engine(
        url, connect_args={"server_settings": {"search_path": SCHEMA + ",public"}}
    )


async def admin_command(url: str, statement: str) -> None:
    # CREATE/DROP DATABASE cannot run in a transaction or across event loops.
    engine = create_async_engine(url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            await connection.execute(text(statement))
    finally:
        await engine.dispose()


@dataclass
class SeedTemplate:
    server_url: str
    database: str
    storage: Path
    result: object  # preview.SeedResult
    models: list[tuple[str, int]]

    async def clone(self, storage: Path) -> tuple[str, AsyncEngine]:
        """A private copy of the seeded database and storage for one case."""
        name = f"{self.database}_{uuid.uuid4().hex[:12]}"
        await admin_command(self.server_url, f'CREATE DATABASE "{name}" TEMPLATE "{self.database}"')
        shutil.copytree(self.storage, storage, dirs_exist_ok=True)
        # Registering a model attaches its index definition to the ORM table,
        # as the replaced seed run would have done in this process.
        from people_gator_api.persistence.postgres.models import face_embedding_hnsw_index

        for stub, dimension in self.models:
            face_embedding_hnsw_index(stub, dimension)
        return name, schema_engine(database_url(self.server_url, name))

    async def drop(self, name: str) -> None:
        await admin_command(self.server_url, f'DROP DATABASE "{name}" WITH (FORCE)')


async def build_template(server_url: str, storage: Path, seed) -> SeedTemplate:
    """Migrate a template database and run one real fresh seed into it."""
    from people_gator_api.filesystem.local import LocalFilesystem
    from people_gator_api.persistence.postgres import postgres_database
    from people_gator_api.persistence.postgres.models import FaceEmbedding
    from people_gator_api.persistence.postgres.schema import migration_config

    # Seed-test servers are the worker's private database, or the caller's
    # disposable one without workers; derived names share its prefix so the
    # pytest controller's cleanup also removes them.
    database = make_url(server_url).database + "_seed"
    await admin_command(server_url, f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)')
    await admin_command(server_url, f'CREATE DATABASE "{database}"')
    url = database_url(server_url, database)
    admin = create_async_engine(url, poolclass=NullPool)
    async with admin.begin() as connection:
        for extension in ("vector", "pg_trgm", "unaccent"):
            await connection.execute(text(f"CREATE EXTENSION IF NOT EXISTS {extension} WITH SCHEMA public"))
        await connection.execute(text(f"CREATE SCHEMA {SCHEMA}"))
        await connection.execute(text(
            f"CREATE TABLE {SCHEMA}.alembic_version (version_num VARCHAR(32) PRIMARY KEY)"
        ))
    await admin.dispose()

    indexes = FaceEmbedding.__table__.indexes
    original = set(indexes)
    engine = schema_engine(url)
    try:
        def migrate(connection):
            config = migration_config()
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

        async with engine.begin() as connection:
            await connection.run_sync(migrate)
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            database_ = postgres_database(session)
            result = await seed(database_, LocalFilesystem(storage))
            models = [(model.model_stub, model.embedding_dim) for model in (await database_.face_models.list()).items]
    finally:
        # A template database must have no open connections when it is copied.
        await engine.dispose()
        indexes.clear()
        indexes.update(original)
    return SeedTemplate(server_url, database, storage, result, models)


async def shared_template(url: str, basetemp: Path, seed, result_type) -> SeedTemplate:
    """The run's template: built by the first worker that needs it, then reused.

    ``basetemp`` is pytest's per-worker temporary root; xdist workers share its
    parent, which pytest creates afresh for every run.
    """
    root = basetemp.parent if os.getenv("PYTEST_XDIST_WORKER") else basetemp
    info = root / "preview-seed-template.json"
    with open(root / "preview-seed-template.lock", "a") as lock:
        # Other workers are separate processes; blocking this event loop is fine.
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            if not info.exists():
                storage = root / "preview-seed-template"
                storage.mkdir()
                template = await build_template(url, storage, seed)
                info.write_text(json.dumps({
                    "database": template.database, "storage": str(storage),
                    "result": template.result.model_dump(mode="json"), "models": template.models,
                }))
            data = json.loads(info.read_text())
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
    # Copies are created through this worker's own database on the same server.
    return SeedTemplate(
        url, data["database"], Path(data["storage"]),
        result_type.model_validate(data["result"]), [tuple(model) for model in data["models"]],
    )


def owns_template() -> bool:
    """Without xdist the session drops its template; otherwise the controller does."""
    return not os.getenv("PYTEST_XDIST_WORKER")
