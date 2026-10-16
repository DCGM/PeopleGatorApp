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
from unittest.mock import AsyncMock, Mock, patch

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

    def test_encrypted_object_identity_is_not_assumed_to_be_an_md5_checksum(self):
        raw = b"PGDMP synthetic encrypted-object archive"
        identity = {"ETag": '"' + "a" * 32 + '"', "ContentLength": len(raw), "ServerSideEncryption": "aws:kms",
                    "Metadata": {"sha256": hashlib.sha256(raw).hexdigest()}}
        client = Mock()
        client.head_object.return_value = identity
        client.get_object.return_value = {**identity, "Body": io.BytesIO(raw)}
        with tempfile.TemporaryDirectory() as directory:
            result = snapshot.download(client, "bucket", "key", Path(directory) / "dump")
            self.assertEqual(result["sha256"], hashlib.sha256(raw).hexdigest())

    def test_metadata_names_ignore_case_but_values_and_conflicts_remain_checked(self):
        raw = b"PGDMP synthetic archive"
        metadata = {"sha256": hashlib.sha256(raw).hexdigest(), "application-revision": "a" * 40}
        identity = {"ETag": '"opaque"', "ContentLength": len(raw)}
        before = {**identity, "Metadata": {k.title(): v for k, v in metadata.items()}}
        for change in ("casing", "checksum", "revision", "conflict"):
            after_metadata = dict(metadata)
            if change == "checksum":
                after_metadata["sha256"] = "b" * 64
            elif change == "revision":
                after_metadata["application-revision"] = "b" * 40
            elif change == "conflict":
                after_metadata["Sha256"] = "b" * 64
            client = Mock()
            client.head_object.side_effect = [before, {**identity, "Metadata": after_metadata}]
            client.get_object.return_value = {**identity, "Body": io.BytesIO(raw)}
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                destination = Path(directory) / "archive"
                if change == "casing":
                    result = snapshot.download(client, "bucket", "key", destination)
                    self.assertEqual(result["source_application_revision"], "a" * 40)
                    self.assertEqual(result["sha256"], metadata["sha256"])
                    self.assertEqual(destination.read_bytes(), raw)
                else:
                    with self.assertRaises(ValueError):
                        snapshot.download(client, "bucket", "key", destination)
            self.assertTrue(client.get_object.return_value["Body"].closed)

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


class MediaCopyTests(unittest.IsolatedAsyncioTestCase):
    async def test_copy_preserves_bytes_names_and_layouts_but_excludes_auth_and_duplicate_scan_paths(self):
        objects = {"images/hash.jpg": b"original image", "images/ndk/library/document/page.jpg": b"original scan",
                   "page-layouts/library/document/page.json": b'{"original":"OCR"}',
                   "peoplegator_api/users.json": b"source credentials"}
        client = Mock()
        def listing(**kwargs):
            rows = [{"Key": k, "Size": len(v), "ETag": '"identity"'} for k, v in objects.items() if k.startswith(kwargs["Prefix"])]
            return [{"Contents": rows[:1]}, {"Contents": rows[1:]}]
        client.get_paginator.return_value.paginate.side_effect = listing
        bodies = []
        def get(**kwargs):
            self.assertEqual(kwargs["IfMatch"], '"identity"')
            body = io.BytesIO(objects[kwargs["Key"]])
            bodies.append(body)
            return {"Body": body, "ETag": '"identity"'}
        client.get_object.side_effect = get
        filesystem = Mock(write_bytes=AsyncMock())
        mappings = [("images", "generations/new/images"), ("images/ndk", "generations/new/images/ndk"),
                    ("page-layouts", "generations/new/page-layouts")]
        with patch.object(snapshot, "s3_client", return_value=client):
            self.assertEqual(await snapshot.copy_media(filesystem, {"bucket": "source"}, mappings), 3)
        copied = {call.args[0]: call.args[1] for call in filesystem.write_bytes.await_args_list}
        self.assertEqual(copied, {"generations/new/" + k: v for k, v in objects.items() if not k.startswith("peoplegator_api/")})
        self.assertEqual(client.get_object.call_count, 3)
        self.assertTrue(all(body.closed for body in bodies))

    async def test_bad_prefix_changed_or_missing_media_fails_without_writing_auth(self):
        filesystem = Mock(write_bytes=AsyncMock())
        with self.assertRaisesRegex(ValueError, "prefix"):
            await snapshot.copy_media(filesystem, {"bucket": "source"}, [("../images", "generation/images")])
        with self.assertRaisesRegex(ValueError, "Authentication"):
            await snapshot.copy_media(filesystem, {"bucket": "source"}, [("peoplegator_api", "generation/images")])
        for failure in ("key", "size", "identity", "missing"):
            client = Mock()
            key = "images/../../peoplegator_api/users.json" if failure == "key" else "images/image.jpg"
            client.get_paginator.return_value.paginate.return_value = [{"Contents": [{"Key": key, "Size": 8, "ETag": '"identity"'}]}]
            body = io.BytesIO(b"too short" if failure == "size" else b"original")
            client.get_object.return_value = {"Body": body, "ETag": '"changed"' if failure == "identity" else '"identity"'}
            if failure == "missing":
                client.get_object.side_effect = FileNotFoundError
            with self.subTest(failure=failure), patch.object(snapshot, "s3_client", return_value=client):
                with self.assertRaises((ValueError, FileNotFoundError)):
                    await snapshot.copy_media(filesystem, {"bucket": "source"}, [("images", "generation/images")])
            filesystem.write_bytes.assert_not_awaited()


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

    async def test_original_copy_preserves_all_rows_vectors_and_media_bytes(self):
        from people_gator_api.filesystem.local import LocalFilesystem
        from people_gator_api.media.page_image import page_image_key
        from people_gator_api.media.page_layout import page_layout_key
        connection = self.connection
        async def rows():
            return {table: [r["row"] for r in await connection.fetch(
                f"SELECT row_to_json(t)::text AS row FROM {table} t ORDER BY row_to_json(t)::text")]
                for table in snapshot.SANITIZED_COLUMNS}
        before = await rows()
        source_root = Path(json.loads(self.environment["PEOPLE_GATOR_API__STORAGE"])["local"]["root"])
        objects = {str(path.relative_to(source_root)): path.read_bytes()
                   for prefix in ("images", "page-layouts") for path in (source_root / prefix).rglob("*") if path.is_file()}
        objects["peoplegator_api/users.json"] = b"source authentication must not be copied"
        client = Mock()
        client.get_paginator.return_value.paginate.side_effect = lambda **kwargs: [{"Contents": [
            {"Key": k, "Size": len(v), "ETag": '"fixture"'} for k, v in objects.items() if k.startswith(kwargs["Prefix"])]}]
        client.get_object.side_effect = lambda **kwargs: {"Body": io.BytesIO(objects[kwargs["Key"]]), "ETag": '"fixture"'}
        with tempfile.TemporaryDirectory() as directory, patch.object(snapshot, "s3_client", return_value=client):
            filesystem = LocalFilesystem(directory)
            result = await snapshot.preserve(connection, filesystem, {"bucket": "source-fixture"})
            self.assertEqual(result["data_mode"], "original")
            self.assertEqual(await rows(), before)
            for page in await connection.fetch("SELECT * FROM pg_demo_pages"):
                for key in (page_image_key(page["library"], page["document_id"], page["page_id"]),
                            page_layout_key(page["library"], page["document_id"], page["page_id"])):
                    if key in objects:
                        self.assertEqual(await filesystem.read_bytes(key), objects[key])
                    else:
                        with self.assertRaises(FileNotFoundError):
                            await filesystem.read_bytes(key)
            self.assertFalse((Path(directory) / "peoplegator_api").exists())
            self.assertEqual(result["media_objects"], len(objects) - 1)

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
        # Landmark order is supplied by the API caller, not fixed by the enum.
        # Shuffle both arrays together to retain a valid face in a different order.
        face = await connection.fetchrow("""SELECT f.* FROM pg_demo_faces f
            JOIN pg_demo_image_occurrences o ON o.id=f.id WHERE o.source_id=$1 LIMIT 1""", page["id"])
        self.assertIsNotNone(face, "The permitted seeded page must contain a face")
        expected_types = list(reversed(face["keypoint_types"]))
        expected_points = list(reversed(face["keypoints"]))
        await connection.execute("UPDATE pg_demo_faces SET keypoint_types=$1, keypoints=$2 WHERE id=$3",
                                 expected_types, expected_points, face["id"])
        image = io.BytesIO()
        Image.new("RGB", (1200, 1600), "gray").save(image, format="JPEG")
        client = Mock()
        client.get_object.side_effect = lambda **kw: {"Body": io.BytesIO(image.getvalue())}
        with tempfile.TemporaryDirectory() as directory, patch.object(snapshot, "s3_client", return_value=client):
            filesystem = LocalFilesystem(directory)
            result = await snapshot.sanitize(connection, filesystem, {"bucket": "test"}, {"permitted_page_ids": [str(page["id"])]})
            self.assertEqual(result["permitted_pages"], 1)
            self.assertEqual(await connection.fetchval("SELECT count(*) FROM pg_demo_face_embeddings"), expected_vectors)
            retained_face = await connection.fetchrow("SELECT keypoint_types, keypoints FROM pg_demo_faces WHERE id=$1", face["id"])
            self.assertEqual(retained_face["keypoint_types"], expected_types)
            self.assertEqual(retained_face["keypoints"], expected_points)
            # Invalid labels must fail closed instead of being silently relabeled.
            for invalid_types in (expected_types[:-1] + ["unclassified-landmark"], [expected_types[0]] * 5):
                with self.subTest(keypoint_types=invalid_types):
                    await connection.execute("UPDATE pg_demo_faces SET keypoint_types=$1 WHERE id=$2", invalid_types, face["id"])
                    try:
                        with self.assertRaisesRegex(ValueError, "each known keypoint type exactly once"):
                            await snapshot.sanitize(connection, filesystem, {"bucket": "test"}, {"permitted_page_ids": [str(page["id"])]})
                    finally:
                        await connection.execute("UPDATE pg_demo_faces SET keypoint_types=$1 WHERE id=$2", expected_types, face["id"])
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
        from botocore.exceptions import ClientError
        hasher = argon2.PasswordHasher()
        supplied = {"users": {name: {"hash": hasher.hash("private-staging-password")} for name in snapshot.EXAMPLE_SCOPES},
                    "api_keys": {"staging-importer-key": {"hash": hasher.hash("private-staging-key"),
                        "username": "staging-importer", "display_name": "Staging importer",
                        "scopes": ["people-gator:browse", "people-gator:ingest"]}}}
        class MemoryS3:
            def __init__(self):
                self.objects = {}
            async def read_bytes(self, key):
                if key not in self.objects:
                    raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
                return self.objects[key]
            async def write_bytes(self, key, value):
                self.objects[key] = value
        filesystem = MemoryS3()
        await snapshot.provision_auth(filesystem, supplied)
        files = dict(filesystem.objects)
        self.assertNotIn(b"private-staging-password", files["peoplegator_api/users.json"])
        await snapshot.provision_auth(filesystem, {"users": {}, "api_keys": {}})
        self.assertEqual(files, filesystem.objects)
        with patch.object(api_key_service, "get_filesystem", return_value=filesystem), patch.object(auth_service, "get_filesystem", return_value=filesystem):
            identifier, record = await api_key_service.verify_api_key("private-staging-key")
            self.assertEqual(identifier, "staging-importer-key")
            users = await auth_service.get_users()
            self.assertTrue(hasher.verify(users["staging-viewer"]["hash"], "private-staging-password"))
            from fastapi import HTTPException
            with self.assertRaises(HTTPException):
                await api_key_service.verify_api_key("production-key")
            await filesystem.write_bytes("peoplegator_api/api-keys.json", b"{}")
            with self.assertRaises(HTTPException):
                await api_key_service.verify_api_key("private-staging-key")
        users = json.loads(await filesystem.read_bytes("peoplegator_api/users.json"))
        users["staging-viewer"]["scopes"] = []
        await filesystem.write_bytes("peoplegator_api/users.json", json.dumps(users).encode())
        await snapshot.provision_auth(filesystem, {"users": {}, "api_keys": {}})
        self.assertEqual(json.loads(await filesystem.read_bytes("peoplegator_api/users.json"))["staging-viewer"]["scopes"], [])
        await filesystem.write_bytes("peoplegator_api/users.json", b"null")
        with self.assertRaisesRegex(ValueError, "Malformed"):
            await snapshot.provision_auth(filesystem, supplied)
        self.assertEqual(await filesystem.read_bytes("peoplegator_api/users.json"), b"null")


if __name__ == "__main__":
    unittest.main()
