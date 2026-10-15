"""Backup selection/pinning, private credentials and opt-in snapshot integration."""
import asyncio
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import secrets
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

MODULE = Path(__file__).resolve().parents[1] / "snapshot.py"
spec = importlib.util.spec_from_file_location("snapshot", MODULE)
snapshot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshot)


class BackupTests(unittest.TestCase):
    prefix = "production/db-backups/"

    def client(self, pages):
        client = Mock()
        client.get_paginator.return_value.paginate.return_value = pages
        return client

    def test_paginated_unsorted_exact_dates_ignore_upload_time_and_temporary_keys(self):
        keys = ["peoplegator-prod-2026-10-14.dump", "peoplegator-prod-2026-10-15.dump.partial",
                "peoplegator-prod-2026-02-30.dump", "peoplegator-prod-2026-1-16.dump",
                "sub/peoplegator-prod-2027-10-15.dump", "peoplegator-prod-2026-10-15.dump",
                "peoplegator-prod-2026-09-30.dump"]
        pages = [{"Contents": [{"Key": self.prefix + k} for k in keys[:3]]},
                 {"Contents": [{"Key": self.prefix + k} for k in keys[3:]]}]
        pages[1]["Contents"].append({"Key": "other/peoplegator-prod-2030-01-01.dump"})
        client = self.client(pages)
        self.assertEqual(snapshot.select_backup(client, "bucket", self.prefix),
                         self.prefix + "peoplegator-prod-2026-10-15.dump")
        client.get_paginator.return_value.paginate.assert_called_once_with(Bucket="bucket", Prefix=self.prefix)

    def test_no_backups_access_denied_and_exact_override(self):
        client = self.client([{}, {"Contents": []}])
        with self.assertRaisesRegex(ValueError, "No completed"):
            snapshot.select_backup(client, "bucket", self.prefix)
        client.get_paginator.return_value.paginate.side_effect = PermissionError("denied")
        with self.assertRaises(PermissionError):
            snapshot.select_backup(client, "bucket", self.prefix)
        key = self.prefix + "peoplegator-prod-2025-01-01.dump"
        self.assertEqual(snapshot.select_backup(client, "bucket", self.prefix, key), key)
        for key in ("other/peoplegator-prod-2025-01-01.dump", self.prefix + "../secret", self.prefix + "peoplegator-prod-2025-02-29.dump"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                snapshot.select_backup(client, "bucket", self.prefix, key)

    def test_download_pins_identity_streams_and_records_integrity(self):
        raw = b"PGDMP synthetic archive"
        identity = {"ETag": '"' + hashlib.md5(raw).hexdigest() + '"', "ContentLength": len(raw),
                    "VersionId": "pinned-version", "Metadata": {"sha256": hashlib.sha256(raw).hexdigest()}}
        client = Mock()
        client.head_object.return_value = identity
        client.get_object.return_value = {**identity, "Body": io.BytesIO(raw)}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dump"
            result = snapshot.download(client, "bucket", "key", path)
            self.assertEqual(path.read_bytes(), raw)
            self.assertEqual(result["sha256"], hashlib.sha256(raw).hexdigest())
            client.get_object.assert_called_once_with(Bucket="bucket", Key="key", IfMatch=identity["ETag"], VersionId="pinned-version")

    def test_changed_disappeared_truncated_and_corrupt_object_fail_without_fallback(self):
        identity = {"ETag": '"opaque-etag"', "ContentLength": 5, "VersionId": "v1"}
        for change in ("changed", "disappeared", "truncated", "checksum", "get_identity"):
            client = Mock()
            before = {**identity}
            after = {**identity}
            raw = b"12345"
            response = {**identity}
            if change == "changed":
                after["VersionId"] = "v2"
            elif change == "truncated":
                raw = b"123"
            elif change == "checksum":
                before["Metadata"] = {"sha256": "0" * 64}
            elif change == "get_identity":
                response["ETag"] = '"new"'
            client.head_object.side_effect = [before, FileNotFoundError() if change == "disappeared" else after]
            client.get_object.return_value = {**response, "Body": io.BytesIO(raw)}
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory, self.assertRaises((ValueError, FileNotFoundError)):
                snapshot.download(client, "bucket", "key", Path(directory) / "dump")
            client.get_paginator.assert_not_called()


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
        api = MODULE.parents[2] / "people-gator-api"
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

    @classmethod
    def tearDownClass(cls):
        if cls.container:
            cls.sql(f"DROP DATABASE {cls.source} WITH (FORCE); DROP DATABASE {cls.database} WITH (FORCE);")
            cls.workspace.cleanup()

    async def asyncSetUp(self):
        import people_gator_api.schemas
        import asyncpg
        self.connection = await asyncpg.connect(host="127.0.0.1", port=int(os.environ["STAGING_TEST_DATABASE_PORT"]),
                                                user=self.username, password=self.password, database=self.database)
        self.addAsyncCleanup(self.connection.close)

    async def test_sanitize_real_seed_preserves_graph_vectors_and_rejects_unclassified_schema(self):
        from people_gator_api.filesystem.local import LocalFilesystem
        from PIL import Image
        connection = self.connection
        page = await connection.fetchrow("SELECT * FROM pg_demo_pages ORDER BY id LIMIT 1")
        source_id = page["id"]
        # Select a page with actual embedded faces, so retained vectors are verified.
        face_page = await connection.fetchrow("""SELECT p.* FROM pg_demo_pages p JOIN pg_demo_image_occurrences o ON o.source_id=p.id
            JOIN pg_demo_faces f ON f.id=o.id JOIN pg_demo_face_embeddings e ON e.face_id=f.id LIMIT 1""")
        page = face_page or page
        counts = {table: await connection.fetchval(f"SELECT count(*) FROM {table}") for table in
                  ("pg_demo_entities", "pg_demo_text_mentions", "pg_demo_sources")}
        expected_vectors = await connection.fetchval("""SELECT count(*) FROM pg_demo_face_embeddings e
            JOIN pg_demo_image_occurrences o ON o.id=e.face_id WHERE o.source_id=$1""", page["id"])
        image = io.BytesIO()
        Image.new("RGB", (1200, 1600), "gray").save(image, format="JPEG")
        client = Mock()
        client.get_object.side_effect = lambda **kw: {"Body": io.BytesIO(image.getvalue())}
        with tempfile.TemporaryDirectory() as directory, patch.object(snapshot, "s3_client", return_value=client):
            filesystem = LocalFilesystem(directory)
            result = await snapshot.sanitize(connection, filesystem, {"bucket": "test"}, {"permitted_page_ids": [str(page["id"])]})
            self.assertEqual(result["permitted_pages"], 1)
            self.assertEqual(await connection.fetchval("SELECT count(*) FROM pg_demo_face_embeddings"), expected_vectors)
            for table, count in counts.items():
                self.assertEqual(await connection.fetchval(f"SELECT count(*) FROM {table}"), count)
            self.assertEqual(await connection.fetchval("SELECT count(*) FROM pg_demo_users WHERE email IS NOT NULL OR is_active"), 0)
            self.assertEqual(await connection.fetchval("SELECT count(*) FROM pg_demo_entities WHERE description IS NOT NULL"), 0)
            self.assertEqual(await connection.fetchval("SELECT count(*) FROM pg_demo_text_mentions WHERE context IS NOT NULL"), 0)
            self.assertTrue(await connection.fetchval("SELECT bool_and(identifier LIKE 'historical-%') FROM pg_demo_api_keys"))
            from people_gator_api.media.page_image import page_image_key
            from people_gator_api.media.page_layout import page_layout_key
            for row in await connection.fetch("SELECT * FROM pg_demo_pages"):
                self.assertTrue(row["library"].startswith("staging-"))
                raw = await filesystem.read_bytes(page_image_key(row["library"], row["document_id"], row["page_id"]))
                self.assertEqual(Image.open(io.BytesIO(raw)).size, (1200, 1600))
                layout = json.loads(await filesystem.read_bytes(page_layout_key(row["library"], row["document_id"], row["page_id"])))
                self.assertEqual(layout["regions"], [])
            self.assertFalse((Path(directory) / "peoplegator_api").exists())
            if self.container:
                self.assertEqual(result["source_schema_revision"], "d34a021b0005")
                upgraded = {**self.environment, "PEOPLE_GATOR_API__PERSISTENCE": json.dumps({"postgres": {
                    "host": "127.0.0.1", "port": int(os.environ["STAGING_TEST_DATABASE_PORT"]), "user": self.username,
                    "password": self.password, "database": self.database, "schema_mode": "validate"}, "weaviate": None})}
                # Real candidate migrations, full check, repeat, and retain staging-only edits.
                for action in ("migrate", "check", "migrate", "check"):
                    await connection.execute("UPDATE pg_demo_entities SET description='Staging-only edit' WHERE id=(SELECT id FROM pg_demo_entities ORDER BY id LIMIT 1)")
                    process = await asyncio.create_subprocess_exec(sys.executable, "-m", "people_gator_api.cli.database", action,
                        cwd=MODULE.parents[2] / "people-gator-api", env=upgraded,
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                    stdout, stderr = await process.communicate()
                    self.assertEqual(process.returncode, 0, stderr.decode())
                    self.assertEqual(await connection.fetchval("SELECT count(*) FROM pg_demo_entities WHERE description='Staging-only edit'"), 1)
                await snapshot.validate_data(connection)
            await connection.execute("CREATE TABLE unclassified_private_data (secret text)")
            try:
                with self.assertRaisesRegex(ValueError, "Unclassified"):
                    await snapshot.sanitize(connection, filesystem, {}, {})
            finally:
                await connection.execute("DROP TABLE unclassified_private_data")
            await connection.execute("CREATE SCHEMA pgsecrets")
            try:
                with self.assertRaisesRegex(ValueError, "Unclassified snapshot schema"):
                    await snapshot.sanitize(connection, filesystem, {}, {})
            finally:
                await connection.execute("DROP SCHEMA pgsecrets")

    async def test_credentials_use_private_hashes_and_preserve_operator_edits(self):
        import argon2
        from people_gator_api.services import api_key_service, auth_service
        from people_gator_api.filesystem.local import LocalFilesystem
        hasher = argon2.PasswordHasher()
        supplied = {"users": {name: {"hash": hasher.hash("private-staging-password")} for name in snapshot.EXAMPLE_SCOPES},
                    "api_keys": {"staging-importer-key": {"hash": hasher.hash("private-staging-key"),
                        "username": "staging-importer", "display_name": "Staging importer",
                        "scopes": ["people-gator:browse", "people-gator:ingest"]}}}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "peoplegator_api"
            snapshot.provision_auth(root, supplied)
            files = {p.name: p.read_bytes() for p in root.iterdir()}
            self.assertNotIn(b"private-staging-password", files["users.json"])
            snapshot.provision_auth(root, {"users": {}, "api_keys": {}})
            self.assertEqual(files, {p.name: p.read_bytes() for p in root.iterdir()})
            filesystem = LocalFilesystem(directory)
            with patch.object(api_key_service, "get_filesystem", return_value=filesystem), patch.object(auth_service, "get_filesystem", return_value=filesystem):
                identifier, record = await api_key_service.verify_api_key("private-staging-key")
                self.assertEqual(identifier, "staging-importer-key")
                users = await auth_service.get_users()
                self.assertTrue(hasher.verify(users["staging-viewer"]["hash"], "private-staging-password"))
                from fastapi import HTTPException
                with self.assertRaises(HTTPException):
                    await api_key_service.verify_api_key("production-key")
                (root / "api-keys.json").write_text("{}")
                with self.assertRaises(HTTPException):
                    await api_key_service.verify_api_key("private-staging-key")
            users = json.loads((root / "users.json").read_text())
            users["staging-viewer"]["scopes"] = []
            (root / "users.json").write_text(json.dumps(users))
            snapshot.provision_auth(root, {"users": {}, "api_keys": {}})
            self.assertEqual(json.loads((root / "users.json").read_text())["staging-viewer"]["scopes"], [])


if __name__ == "__main__":
    unittest.main()
