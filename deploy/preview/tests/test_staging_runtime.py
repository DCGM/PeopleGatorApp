"""Actual candidate Compose/worker gates with disposable PostgreSQL and TLS S3."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import staging
import test_snapshot as snapshot_tests
from s3_fixture import S3Fixture
snapshot = snapshot_tests.snapshot


@unittest.skipUnless(os.environ.get("STAGING_TEST_IMAGE") and os.environ.get("STAGING_TEST_POSTGRES_CONTAINER"),
                     "Set isolated STAGING_TEST_IMAGE/container/port/network")
class RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        snapshot_tests.SnapshotIntegrationTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        snapshot_tests.SnapshotIntegrationTests.tearDownClass()

    def test_real_s3_restore_media_auth_migration_check_and_lifespan_gates(self):
        fixture = snapshot_tests.SnapshotIntegrationTests
        image = os.environ["STAGING_TEST_IMAGE"]
        database_network = os.environ["STAGING_TEST_NETWORK"]
        egress = "staging-test-egress-" + secrets.token_hex(8)
        subprocess.run(["docker", "network", "create", egress], capture_output=True, check=True)
        try:
            with tempfile.TemporaryDirectory() as temporary, S3Fixture(egress) as s3:
                self.exercise(fixture, image, database_network, Path(temporary), s3)
        finally:
            subprocess.run(["docker", "network", "rm", egress], capture_output=True, check=True)

    def exercise(self, fixture, image, network, root, s3):
        private = root / "private"
        private.mkdir()
        (root / "preview").mkdir()
        state = root / "staging"
        state.mkdir()
        (private / "storage.json").write_text(json.dumps({"local": None, "s3": s3.staging_config}))
        source = {**s3.source_config, "bucket": s3.source_config["bucket_name"]}
        del source["bucket_name"]
        key = "production/db-backups/peoplegator-prod-2026-10-15.dump"
        s3.source.put_object(Bucket=source["bucket"], Key=key, Body=fixture.archive,
            Metadata={"sha256": hashlib.sha256(fixture.archive).hexdigest(), "application-revision": "a" * 40})
        (private / "backup-source.json").write_text(json.dumps(source))
        (private / "media-source.json").write_text(json.dumps(source))
        page = json.loads(fixture.sql("""SELECT row_to_json(p) FROM pg_demo_pages p
            WHERE EXISTS (SELECT FROM pg_demo_image_occurrences o JOIN pg_demo_face_embeddings e ON e.face_id=o.id
                WHERE o.source_id=p.id) LIMIT 1""", fixture.source))
        source_key = f"images/ndk/{page['library']}/{page['document_id']}/{page['page_id']}.jpg"
        source_root = Path(json.loads(fixture.environment["PEOPLE_GATOR_API__STORAGE"])["local"]["root"])
        for prefix in ("images", "page-layouts"):
            for path in (source_root / prefix).rglob("*"):
                if path.is_file():
                    s3.source.put_object(Bucket=source["bucket"], Key=str(path.relative_to(source_root)), Body=path.read_bytes())
        import argon2
        hasher = argon2.PasswordHasher()
        supplied = {"users": {name: {"hash": hasher.hash("private-synthetic-staging-password")} for name in snapshot.EXAMPLE_SCOPES},
                    "api_keys": {"staging-importer-key": {"hash": hasher.hash("private-staging-key"),
                        "username": "staging-importer", "display_name": "Synthetic importer",
                        "scopes": ["people-gator:browse", "people-gator:ingest"]}}}
        (private / "credential-input.json").write_text(json.dumps(supplied))
        controller = staging.Staging({"repository": "DCGM/PeopleGatorApp", "state_dir": str(root / "preview"),
            "database_network": network, "web_network": s3.network, "staging": {
                "state_dir": str(state), "private_dir": str(private), "host": "staging-fixture.example.invalid"}})
        controller.sql = fixture.sql
        controller.infra = lambda *args: ["docker", "exec", "-i", fixture.container,
            *[fixture.username if arg == "preview_admin" else arg for arg in args[3:]]]
        controller.command = s3.worker_command(controller)
        override = state / "compose.test.json"
        s3.compose_override(override)
        project = "staging-test-" + secrets.token_hex(8)
        controller.compose_staging = lambda env, *args: ["docker", "compose", "--project-name", project,
            "--env-file", str(env), "-f", str(staging.INSTALL_DIR / "compose.staging.yaml"), "-f", str(override), *args]
        generations = []
        def generation():
            value = {"generation": secrets.token_hex(8), "password": secrets.token_hex(32),
                     "storage": controller.storage_identity(controller.storage())}
            generations.append(value)
            directory = state / value["generation"]
            directory.mkdir()
            values = controller.values(value, {"backend": image, "frontend": "unused"}, "a" * 40)
            candidate = directory / "candidate.env"
            candidate.write_text(controller.dotenv(values))
            return value, values, directory, candidate
        active, values, directory, candidate = generation()
        try:
            # Actual TLS downloads, pg_restore, scan import, S3 auth and Compose.
            controller.prepare(active, values, directory, candidate, "")
            self.assertEqual(active["provenance"]["source_schema_revision"], "d34a021b0005")
            self.assertEqual(active["provenance"]["data_mode"], "original")
            self.assertGreater(active["provenance"]["media_objects"], 0)
            self.assertEqual(list(state.glob("snapshot-*")), [])
            def gate(action, success=True, env_file=candidate):
                try:
                    controller.command(controller.compose_staging(env_file, "run", "--rm", "--no-deps", action))
                except RuntimeError:
                    self.assertFalse(success, (state / "last-error.log").read_text())
                else:
                    self.assertTrue(success)
            for action in ("migrate", "check"):
                gate(action)
            fixture.sql("UPDATE pg_demo_entities SET description='Staging-only edit' WHERE id=(SELECT id FROM pg_demo_entities LIMIT 1)", values["DB_NAME"])
            for action in ("migrate", "check"):
                gate(action)
            self.assertEqual(int(fixture.sql("SELECT count(*) FROM pg_demo_entities WHERE description='Staging-only edit'", values["DB_NAME"])), 1)
            controller.worker("validate", values, directory)
            self.assertGreater(int(fixture.sql("SELECT count(*) FROM pg_demo_face_embeddings", values["DB_NAME"])), 0)
            auth_before = {k: v for k, v in s3.objects().items() if k.startswith("peoplegator_api/")}
            self.assertEqual(set(auth_before), {"peoplegator_api/users.json", "peoplegator_api/api-keys.json", "peoplegator_api/jwks.json"})
            self.assertTrue(any(k.startswith(values["MEDIA_PREFIX"] + "/images/ndk/") for k in s3.objects()))
            controller.worker("auth", values, directory)
            self.assertEqual(auth_before, {k: v for k, v in s3.objects().items() if k.startswith("peoplegator_api/")})
            s3.source.delete_object(Bucket=source["bucket"], Key=source_key)
            controller.command(controller.compose_staging(candidate, "up", "-d", "--wait", "--wait-timeout", "90", "backend"))
            backend = controller.command(controller.compose_staging(candidate, "ps", "-q", "backend")).strip()
            inspected = subprocess.check_output(["docker", "inspect", "--format", "{{json .Config.Env}}", backend], text=True)
            self.assertNotIn(s3.source_config["secret_access_key"], inspected)
            self.assertIn(s3.staging_config["secret_access_key"], inspected)
            script = '''import httpx, io, time
from PIL import Image
with httpx.Client(base_url="http://127.0.0.1:8000") as client:
    login=client.post("/token/login",data={"username":"staging-viewer","password":"private-synthetic-staging-password","scope":"people-gator:browse"})
    login.raise_for_status()
    client.headers["Authorization"]="Bearer "+login.json()["access_token"]
    entities=client.get("/api/v1/entities"); entities.raise_for_status(); assert entities.json()["items"]
    url="/api/v1/pages/PERMITTED_PAGE/image"
    client.get(url).raise_for_status()
    for _ in range(30):
        cached=client.get(url,params={"width":256}); cached.raise_for_status()
        if cached.headers.get("X-Cache")=="HIT": break
        time.sleep(.1)
    assert cached.headers.get("X-Cache")=="HIT"
    faces=client.get("/api/v1/faces"); faces.raise_for_status()
    crop_url="/api/v1/faces/"+faces.json()["items"][0]["detection_id"]+"/aligned_crop"
    client.get(crop_url).raise_for_status()
    crop=client.get(crop_url); crop.raise_for_status(); assert crop.headers.get("X-Cache")=="HIT"
    client.headers.pop("Authorization")
    client.get("/api/v1/entities",headers={"X-API-Key":"private-staging-key"}).raise_for_status()
    assert client.get("/api/v1/entities",headers={"X-API-Key":"production-key"}).status_code==401
    original=client.get(url,headers={"X-API-Key":"private-staging-key"}); original.raise_for_status()
    pixels=Image.new("RGB",Image.open(io.BytesIO(original.content)).size,"blue")
    buffer=io.BytesIO(); pixels.save(buffer,format="JPEG")
    client.put(url,headers={"X-API-Key":"private-staging-key"},files={"file":("scan.jpg",buffer.getvalue(),"image/jpeg")}).raise_for_status()
    assert client.get(url,headers={"X-API-Key":"private-staging-key"}).content==buffer.getvalue()
print("S3 login, API keys, scan replacement and both media caches passed")'''
            script = script.replace("PERMITTED_PAGE", page["id"])
            result = subprocess.run(["docker", "exec", backend, "python", "-c", script], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(any(k.startswith(values["MEDIA_PREFIX"] + "/cache/page-images/") for k in s3.objects()))
            self.assertTrue(any(k.startswith(values["MEDIA_PREFIX"] + "/cache/aligned-face-crops/") for k in s3.objects()))
            users = json.loads(auth_before["peoplegator_api/users.json"])
            users["staging-viewer"]["scopes"] = []
            s3.staging.put_object(Bucket=s3.staging_config["bucket_name"], Key="peoplegator_api/users.json", Body=json.dumps(users))
            s3.staging.put_object(Bucket=s3.staging_config["bucket_name"], Key="peoplegator_api/api-keys.json", Body=b"{}")
            controller.worker("auth", values, directory)
            retained = s3.objects()
            self.assertEqual(json.loads(retained["peoplegator_api/users.json"])["staging-viewer"]["scopes"], [])
            self.assertEqual(retained["peoplegator_api/api-keys.json"], b"{}")
            self.assertEqual(retained["peoplegator_api/jwks.json"], auth_before["peoplegator_api/jwks.json"])
            result = subprocess.run(["docker", "exec", backend, "python", "-c",
                "import httpx; assert httpx.get('http://127.0.0.1:8000/api/v1/entities', headers={'X-API-Key':'private-staging-key'}).status_code==401"], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            # Successful refresh prepares a different prefix in the same bucket
            # and retains edited credentials, revoked keys and original media.
            new, new_values, new_directory, new_candidate = generation()
            s3.source.put_object(Bucket=source["bucket"], Key=source_key, Body=(source_root / source_key).read_bytes())
            controller.prepare(new, new_values, new_directory, new_candidate, "")
            gate("migrate", env_file=new_candidate)
            gate("check", env_file=new_candidate)
            controller.worker("validate", new_values, new_directory)
            after = s3.objects()
            self.assertEqual(retained, {k: after[k] for k in retained})
            self.assertTrue(any(k.startswith(new_values["MEDIA_PREFIX"] + "/images/ndk/") for k in after))
            retained = after
            # Missing source media may leave private partial generation objects;
            # it must preserve every active/previous object and stable auth key.
            s3.source.delete_object(Bucket=source["bucket"], Key=source_key)
            failed, failed_values, failed_directory, failed_candidate = generation()
            with self.assertRaises(RuntimeError):
                controller.prepare(failed, failed_values, failed_directory, failed_candidate, "")
            after = s3.objects()
            self.assertEqual(retained, {k: after[k] for k in retained})
            # The worker independently rejects a local-only override.
            with self.assertRaises(RuntimeError):
                controller.worker("validate", {**values, "STAGING_STORAGE": '{"local":{"root":"/forbidden"},"s3":null}'}, directory)
            controller.command(controller.compose_staging(candidate, "stop", "backend"))
            empty = "staging_" + secrets.token_hex(8)
            fixture.sql(f"CREATE DATABASE {empty}; GRANT CONNECT ON DATABASE {empty} TO {values['DB_USER']};")
            try:
                wrong = directory / "wrong.env"
                wrong.write_text(controller.dotenv({**values, "DB_NAME": empty}))
                gate("check", success=False, env_file=wrong)
                with self.assertRaises(RuntimeError):
                    controller.command(controller.compose_staging(wrong, "run", "--rm", "--no-deps", "backend"))
            finally:
                fixture.sql(f"DROP DATABASE {empty} WITH (FORCE);")
            for mutation, recovery in (
                ("UPDATE alembic_version SET version_num='unknown_revision'", "UPDATE alembic_version SET version_num='d34a021b0006'"),
                ("ALTER TABLE pg_demo_entities RENAME COLUMN description TO drifted_description", "ALTER TABLE pg_demo_entities RENAME COLUMN drifted_description TO description"),
            ):
                fixture.sql(mutation, values["DB_NAME"])
                gate("check", success=False)
                with self.assertRaises(RuntimeError):
                    controller.command(controller.compose_staging(candidate, "run", "--rm", "--no-deps", "backend"))
                fixture.sql(recovery, values["DB_NAME"])
                gate("check")
            controller.command(controller.compose_staging(candidate, "up", "-d", "--wait", "--wait-timeout", "90", "backend"))
            controller.command(controller.compose_staging(candidate, "stop", "backend"))
            fixture.sql("UPDATE alembic_version SET version_num='unknown_revision'", values["DB_NAME"])
            subprocess.run(["docker", "start", backend], check=True, capture_output=True)
            result = subprocess.run(["docker", "wait", backend], timeout=40, check=True, capture_output=True)
            self.assertNotEqual(result.stdout.strip(), b"0")
        except Exception:
            diagnostic = state / "last-error.log"
            if diagnostic.exists():
                print(diagnostic.read_text(), file=sys.stderr)  # synthetic fixture only
            raise
        finally:
            controller.command(controller.compose_staging(candidate, "down", "--timeout", "10"))
            for value in generations:
                name = "staging_" + value["generation"]
                fixture.sql(f"DROP DATABASE IF EXISTS {name} WITH (FORCE); DROP ROLE IF EXISTS {name};")


if __name__ == "__main__":
    unittest.main()
