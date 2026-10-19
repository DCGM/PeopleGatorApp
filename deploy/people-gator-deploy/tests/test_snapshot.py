"""Real database snapshot preservation and migrations, independent of media/storage."""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import sys
import secrets
import subprocess
import tempfile
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / "src/people_gator_deploy/assets/snapshot.py"
REPOSITORY = MODULE.parents[5]
spec = importlib.util.spec_from_file_location("snapshot", MODULE)
snapshot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshot)

TABLES = ("pg_demo_users", "pg_demo_api_keys", "pg_demo_entities", "pg_demo_aliases", "pg_demo_sources",
          "pg_demo_documents", "pg_demo_pages", "pg_demo_images", "pg_demo_text_mentions",
          "pg_demo_image_occurrences", "pg_demo_faces", "pg_demo_face_models", "pg_demo_face_embeddings",
          "alembic_version")


@unittest.skipUnless(os.environ.get("STAGING_TEST_DATABASE_PORT"), "Set isolated STAGING_TEST_DATABASE_PORT; requires backend venv")
class SnapshotIntegrationTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.database = "staging_0123456789abcdef"
        cls.username = os.environ.get("STAGING_TEST_DATABASE_USER", "test")
        cls.password = os.environ.get("STAGING_TEST_DATABASE_PASSWORD", "test")
        cls.container = os.environ.get("STAGING_TEST_POSTGRES_CONTAINER")
        if not cls.container:
            return  # explicitly prepared local disposable database
        cls.database = "staging_" + secrets.token_hex(8)
        cls.source = "fixture_" + secrets.token_hex(8)
        def sql(query, database="postgres"):
            return subprocess.run(["docker", "exec", "-i", cls.container, "psql", "-XqAt", "-U", cls.username,
                                   "-d", database, "-v", "ON_ERROR_STOP=1"], input=query, text=True,
                                  capture_output=True, check=True).stdout
        cls.sql = staticmethod(sql)
        sql(f"CREATE DATABASE {cls.source}; CREATE DATABASE {cls.database};")
        cls.workspace = tempfile.TemporaryDirectory()
        cls.environment = {k: v for k, v in os.environ.items() if not k.startswith(("PEOPLE_GATOR_API__PERSISTENCE", "PEOPLE_GATOR_API__STORAGE"))}
        cls.environment.update({"PEOPLE_GATOR_API__PERSISTENCE": json.dumps({"postgres": {
            "host": "127.0.0.1", "port": int(os.environ["STAGING_TEST_DATABASE_PORT"]), "user": cls.username,
            "password": cls.password, "database": cls.source, "schema_mode": "validate"}, "weaviate": None}),
            "PEOPLE_GATOR_API__STORAGE": json.dumps({"local": {"root": cls.workspace.name}, "s3": None})})
        api = REPOSITORY / "people-gator-api"
        for command in (("database", "migrate"), ("seed",), ("seed",), ("database", "check")):
            subprocess.run([sys.executable, "-m", "people_gator_api.cli." + command[0], *command[1:]],
                           cwd=api, env=cls.environment, capture_output=True, check=True)
        # Represent a retained production-shaped store at an older real revision.
        subprocess.run([sys.executable, "-m", "alembic", "downgrade", "d34a021b0005"], cwd=api,
                       env=cls.environment, capture_output=True, check=True)
        sql("UPDATE pg_demo_users SET email='SENSITIVE-PRODUCTION@example.test'; "
            "UPDATE pg_demo_entities SET description='SENSITIVE-PRODUCTION'; "
            "UPDATE pg_demo_text_mentions SET context='SENSITIVE-PRODUCTION';", cls.source)
        # A real custom-format pg_dump/pg_restore fixture: no production dump or secrets.
        archive = subprocess.run(["docker", "exec", cls.container, "pg_dump", "-Fc", "-U", cls.username,
                                  "-d", cls.source], capture_output=True, check=True).stdout
        cls.archive = archive
        assert archive[:5] == b"PGDMP"
        subprocess.run(["docker", "exec", "-i", cls.container, "pg_restore", "--no-owner", "--no-privileges",
                        "--exit-on-error", "--single-transaction", "-U", cls.username, "-d", cls.database],
                       input=archive, capture_output=True, check=True)
        assert sql("SELECT version_num FROM alembic_version", cls.source) == sql("SELECT version_num FROM alembic_version", cls.database)
        # Standalone integration tests cannot inherit pytest conftest's defaults.
        # Select this fixture's database/storage before any application import.
        local_environment = dict(cls.environment)
        config = json.loads(local_environment["PEOPLE_GATOR_API__PERSISTENCE"])
        config["postgres"]["database"] = cls.database
        local_environment["PEOPLE_GATOR_API__PERSISTENCE"] = json.dumps(config)
        cls.settings_patch = patch.dict(os.environ, local_environment, clear=True)
        cls.settings_patch.start()

    @classmethod
    def tearDownClass(cls):
        if cls.container:
            cls.settings_patch.stop()
            cls.sql(f"DROP DATABASE {cls.source} WITH (FORCE); DROP DATABASE {cls.database} WITH (FORCE);")
            cls.workspace.cleanup()

    async def asyncSetUp(self):
        import people_gator_api.schemas
        import asyncpg
        self.connection = await asyncpg.connect(host="127.0.0.1", port=int(os.environ["STAGING_TEST_DATABASE_PORT"]),
                                                user=self.username, password=self.password, database=self.database)
        self.addAsyncCleanup(self.connection.close)

    async def test_original_rows_vectors_and_relationships_are_preserved_without_media(self):
        async def rows():
            return {table: [r["row"] for r in await self.connection.fetch(
                f"SELECT row_to_json(t)::text AS row FROM {table} t ORDER BY row_to_json(t)::text")]
                for table in TABLES}
        before = await rows()
        self.assertGreater(len(before["pg_demo_face_embeddings"]), 0)
        self.assertTrue(any("SENSITIVE-PRODUCTION" in row for row in before["pg_demo_text_mentions"]))
        # No media or auth provider is passed to the validator. Database-only
        # preparation is valid even when none of the referenced objects exist.
        await snapshot.validate_data(self.connection)
        self.assertEqual(await rows(), before)
        self.assertFalse(hasattr(snapshot, "staging_filesystem"))

    async def test_candidate_migrations_and_checks_retain_staging_edits(self):
        if not self.container:
            self.skipTest("requires the disposable container fixture at an older revision")
        connection = self.connection
        self.assertEqual(await connection.fetchval("SELECT version_num FROM alembic_version"), "d34a021b0005")
        upgraded = {**self.environment, "PEOPLE_GATOR_API__PERSISTENCE": json.dumps({"postgres": {
            "host": "127.0.0.1", "port": int(os.environ["STAGING_TEST_DATABASE_PORT"]), "user": self.username,
            "password": self.password, "database": self.database, "schema_mode": "validate"}, "weaviate": None})}
        # Real candidate migrations, full check, repeat, and retain staging-only edits.
        for action in ("migrate", "check", "migrate", "check"):
            await connection.execute("UPDATE pg_demo_entities SET description='Staging-only edit' "
                                     "WHERE id=(SELECT id FROM pg_demo_entities ORDER BY id LIMIT 1)")
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "people_gator_api.cli.database", action,
                cwd=REPOSITORY / "people-gator-api", env=upgraded,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, stderr = await process.communicate()
            self.assertEqual(process.returncode, 0, stderr.decode())
            self.assertEqual(await connection.fetchval(
                "SELECT count(*) FROM pg_demo_entities WHERE description='Staging-only edit'"), 1)
        await snapshot.validate_data(connection)



if __name__ == "__main__":
    unittest.main()
