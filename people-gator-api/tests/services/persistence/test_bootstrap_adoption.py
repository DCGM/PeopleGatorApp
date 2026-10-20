"""Adopt old create_all schemas only after checking frozen migration snapshots."""

import os
import uuid

import pytest
import pytest_asyncio
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from people_gator_api.cli import database as database_cli
from people_gator_api.persistence.postgres.bootstrap import (
    frozen_schemas,
    matching_bootstrap_revision,
)
from people_gator_api.persistence.postgres.schema import (
    SchemaValidationError,
    migration_config,
    validate_postgres_schema,
)


def test_frozen_snapshots_preserve_their_original_fields():
    snapshots = frozen_schemas(migration_config())
    assert [revision for revision, _ in snapshots] == [
        "c82e7f4a901d",
        "d34a021b0001",
        "d34a021b0002",
        "d34a021b0003",
    ]
    baseline, keys, touch, names = [metadata for _, metadata in snapshots]
    assert "pg_demo_api_keys" not in baseline.tables
    assert "pg_demo_api_keys" in keys.tables
    assert "last_touched_at" not in keys.tables["pg_demo_entities"].c
    assert "last_touched_at" in touch.tables["pg_demo_entities"].c
    assert "name" not in touch.tables["pg_demo_documents"].c
    assert names.tables["pg_demo_documents"].c.name.nullable


@pytest_asyncio.fixture
async def bootstrap_database(monkeypatch):
    url = os.getenv("PEOPLE_GATOR_SCHEMA_TEST_URL")
    if not url:
        pytest.skip("requires disposable schema test DB")
    admin = create_async_engine(make_url(url))
    schema = "bootstrap_test_" + uuid.uuid4().hex
    async with admin.begin() as connection:
        for extension in ("vector", "pg_trgm", "unaccent"):
            await connection.execute(
                text(f"CREATE EXTENSION IF NOT EXISTS {extension} WITH SCHEMA public")
            )
        await connection.execute(text(f"CREATE SCHEMA {schema}"))
        await connection.execute(text(f"CREATE TABLE {schema}.alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
    engine = create_async_engine(
        make_url(url),
        connect_args={"server_settings": {"search_path": schema + ",public"}},
    )
    monkeypatch.setattr(
        database_cli, "create_async_engine", lambda *args, **kwargs: engine
    )
    yield engine
    await engine.dispose()
    async with admin.begin() as connection:
        await connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
    await admin.dispose()


async def seed_bootstrap(engine, snapshot=1):
    def seed(connection):
        config = migration_config()
        config.attributes["connection"] = connection
        command.upgrade(config, "65c4e6cdfa7f")
        frozen_schemas(config)[snapshot][1].create_all(connection, checkfirst=False)
        connection.execute(
            text(
                "INSERT INTO pg_demo_users(id, display_name, is_active, external_subject, external_issuer) VALUES ('11111111-1111-1111-1111-111111111111', 'Historical user', true, 'historical', 'bootstrap-test')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO pg_demo_entities(id, user_id, kind, name) VALUES ('22222222-2222-2222-2222-222222222222', '11111111-1111-1111-1111-111111111111', 'person', 'Historical identity')"
            )
        )
        if snapshot >= 1:
            connection.execute(
                text(
                    "INSERT INTO pg_demo_api_keys(id, identifier, display_name, user_id) VALUES ('33333333-3333-3333-3333-333333333333', 'existing-importer', 'Existing importer', '11111111-1111-1111-1111-111111111111')"
                )
            )

    async with engine.begin() as connection:
        await connection.run_sync(seed)


@pytest.mark.asyncio
@pytest.mark.parametrize("snapshot", [0, 1, 2, 3])
async def test_adopt_bootstrap_preserves_data_and_applies_only_missing_migrations(
    bootstrap_database, snapshot
):
    engine = bootstrap_database
    await seed_bootstrap(engine, snapshot)
    await database_cli.migrate_database(adopt_bootstrap=True)
    await validate_postgres_schema(engine)
    async with engine.connect() as connection:
        record = (
            await connection.execute(
                text(
                    "SELECT name, last_touched_at, last_touched_by_user_id, last_touched_by_api_key_id FROM pg_demo_entities"
                )
            )
        ).one()
        assert record == ("Historical identity", None, None, None)
        if snapshot >= 1:
            assert (
                str(
                    await connection.scalar(
                        text(
                            "SELECT id FROM pg_demo_api_keys WHERE identifier = 'existing-importer'"
                        )
                    )
                )
                == "33333333-3333-3333-3333-333333333333"
            )
    # Re-running with or without adoption remains safe once Alembic is current.
    await database_cli.migrate_database(adopt_bootstrap=True)
    await database_cli.migrate_database()


@pytest.mark.asyncio
async def test_adoption_flag_handles_a_fresh_database(bootstrap_database):
    await database_cli.migrate_database(adopt_bootstrap=True)
    await validate_postgres_schema(bootstrap_database)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "drift",
    [
        "ALTER TABLE pg_demo_users DROP COLUMN email",
        "DROP INDEX ix_pg_demo_users_is_active",
        "ALTER TABLE pg_demo_face_models DROP CONSTRAINT ck_pg_demo_face_model_embedding_dim",
        "ALTER TABLE pg_demo_face_embeddings DROP CONSTRAINT pg_demo_face_embeddings_pkey; ALTER TABLE pg_demo_face_embeddings ADD PRIMARY KEY (model_id, face_id)",
    ],
)
async def test_adoption_rejects_drift_without_advancing_history(
    bootstrap_database, drift
):
    engine = bootstrap_database
    await seed_bootstrap(engine)
    async with engine.begin() as connection:
        for statement in drift.split(";"):
            await connection.execute(text(statement))
    with pytest.raises(SchemaValidationError, match="refusing"):
        await database_cli.migrate_database(adopt_bootstrap=True)
    async with engine.connect() as connection:
        assert (
            await connection.scalar(text("SELECT version_num FROM alembic_version"))
            == "65c4e6cdfa7f"
        )
        assert (
            await connection.scalar(text("SELECT name FROM pg_demo_entities"))
            == "Historical identity"
        )


@pytest.mark.asyncio
async def test_adoption_and_migration_rollback_together(
    bootstrap_database, monkeypatch
):
    engine = bootstrap_database
    await seed_bootstrap(engine)

    def fail_validation(connection):
        raise RuntimeError("injected validation failure")

    monkeypatch.setattr(database_cli, "validate_schema", fail_validation)
    with pytest.raises(RuntimeError, match="injected"):
        await database_cli.migrate_database(adopt_bootstrap=True)
    async with engine.connect() as connection:
        assert (
            await connection.scalar(text("SELECT version_num FROM alembic_version"))
            == "65c4e6cdfa7f"
        )
        assert (
            await connection.scalar(
                text(
                    "SELECT count(*) FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = 'pg_demo_entities' AND column_name = 'last_touched_at'"
                )
            )
            == 0
        )
        assert (
            await connection.scalar(text("SELECT name FROM pg_demo_entities"))
            == "Historical identity"
        )


@pytest.mark.asyncio
async def test_bootstrap_preflight_is_read_only(bootstrap_database):
    engine = bootstrap_database
    await seed_bootstrap(engine)
    async with engine.connect() as connection:
        async with connection.begin():
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            revision = await connection.run_sync(
                lambda sync: matching_bootstrap_revision(sync, migration_config())
            )
            assert revision == "d34a021b0001"
            assert (
                await connection.scalar(text("SELECT version_num FROM alembic_version"))
                == "65c4e6cdfa7f"
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("adopt", [False, True])
async def test_link_migration_reuses_bootstrap_enum_and_preserves_old_data(
    bootstrap_database, adopt
):
    from people_gator_api.persistence.postgres.models import Base

    engine = bootstrap_database
    await seed_bootstrap(engine, snapshot=3)
    async with engine.begin() as connection:
        if not adopt:
            await connection.execute(text("UPDATE alembic_version SET version_num = 'd34a021b0003'"))
        # Reproduce starting the newer ORM in bootstrap mode against old tables.
        await connection.run_sync(Base.metadata.create_all)
        assert await connection.scalar(text("SELECT to_regtype('pg_demo_entity_link_state')"))
        assert await connection.scalar(text("""
            SELECT count(*) FROM information_schema.columns
            WHERE table_schema = current_schema() AND column_name = 'entity_link_state'
        """)) == 0
    await database_cli.migrate_database(adopt_bootstrap=adopt)
    await validate_postgres_schema(engine)
    async with engine.connect() as connection:
        assert await connection.scalar(text("SELECT name FROM pg_demo_entities")) == "Historical identity"
        assert await connection.scalar(text("SELECT version_num FROM alembic_version")) == ScriptDirectory.from_config(migration_config()).get_current_head()
    await database_cli.migrate_database(adopt_bootstrap=True)


@pytest.mark.asyncio
async def test_link_migration_rejects_conflicting_bootstrap_enum(bootstrap_database):
    engine = bootstrap_database
    await seed_bootstrap(engine, snapshot=3)
    async with engine.begin() as connection:
        await connection.execute(text("CREATE TYPE pg_demo_entity_link_state AS ENUM ('automatic', 'wrong')"))
    with pytest.raises(ValueError, match="type does not match"):
        await database_cli.migrate_database(adopt_bootstrap=True)
    async with engine.connect() as connection:
        assert await connection.scalar(text("SELECT version_num FROM alembic_version")) == "65c4e6cdfa7f"
        assert await connection.scalar(text("SELECT name FROM pg_demo_entities")) == "Historical identity"
        assert await connection.scalar(text("""
            SELECT count(*) FROM information_schema.columns
            WHERE table_schema = current_schema() AND column_name = 'entity_link_state'
        """)) == 0


@pytest.mark.asyncio
async def test_link_migration_does_not_reuse_another_schemas_visible_enum(bootstrap_database):
    engine = bootstrap_database
    await seed_bootstrap(engine, snapshot=3)
    async with engine.begin() as connection:
        schema = await connection.scalar(text("SELECT current_schema()"))
        shadow = "enum_shadow_" + uuid.uuid4().hex
        await connection.execute(text(f'CREATE SCHEMA "{shadow}"'))
        await connection.execute(text(
            f'CREATE TYPE "{shadow}".pg_demo_entity_link_state AS ENUM '
            "('automatic', 'manual', 'verified')"
        ))
        await connection.execute(text(f'SET LOCAL search_path TO "{schema}", "{shadow}", public'))
        await connection.execute(text("UPDATE alembic_version SET version_num = 'd34a021b0003'"))

        def migrate(sync):
            config = migration_config()
            config.attributes["connection"] = sync
            command.upgrade(config, "head")

        await connection.run_sync(migrate)
        namespaces = (await connection.execute(text("""
            SELECT DISTINCT type_namespace.nspname
            FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid
            JOIN pg_namespace table_namespace ON table_namespace.oid = c.relnamespace
            JOIN pg_type t ON t.oid = a.atttypid
            JOIN pg_namespace type_namespace ON type_namespace.oid = t.typnamespace
            WHERE table_namespace.nspname = current_schema()
                AND a.attname = 'entity_link_state'
                AND c.relname IN ('pg_demo_text_mentions', 'pg_demo_image_occurrences')
        """))).scalars().all()
        assert namespaces == [schema]
        await connection.execute(text(f'DROP SCHEMA "{shadow}" CASCADE'))
    await validate_postgres_schema(engine)
