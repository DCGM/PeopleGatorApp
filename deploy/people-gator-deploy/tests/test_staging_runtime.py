"""Real local snapshot restore, migration/check and startup gates without S3."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import unittest

from people_gator_deploy import staging
from people_gator_deploy.core import DeployError
import test_snapshot as snapshot_tests


@unittest.skipUnless(os.environ.get("STAGING_TEST_IMAGE") and os.environ.get("STAGING_TEST_POSTGRES_CONTAINER"),
                     "Set isolated STAGING_TEST_IMAGE/container/port/network")
class RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        snapshot_tests.SnapshotIntegrationTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        snapshot_tests.SnapshotIntegrationTests.tearDownClass()

    def test_real_local_restore_and_database_gates_without_media_or_auth_objects(self):
        network = "staging-test-web-" + secrets.token_hex(8)
        subprocess.run(["docker", "network", "create", "--internal", network], capture_output=True, check=True)
        try:
            with tempfile.TemporaryDirectory() as temporary:
                self.exercise(Path(temporary), network)
        finally:
            subprocess.run(["docker", "network", "rm", network], capture_output=True, check=True)

    def exercise(self, root, network):
        fixture = snapshot_tests.SnapshotIntegrationTests
        state = root / "staging"
        state.mkdir()
        (root / "preview").mkdir()
        archive = root / "operator-snapshot.dump"
        archive.write_bytes(fixture.archive)
        archive.chmod(0o600)
        # The operator, not staging tooling, supplies storage settings. No S3
        # server, objects, credentials provisioner or media copy exists here.
        storage = {"local": None, "s3": {"endpoint_url": "https://externally-managed.invalid", "region": "test",
                   "bucket_name": "external", "access_key_id": "external-id", "secret_access_key": "external-secret"}}
        runtime = root / "runtime.env"
        runtime.write_text("PEOPLE_GATOR_API__STORAGE=" + json.dumps(storage) + "\n")
        runtime.chmod(0o600)
        context = os.environ.get("STAGING_TEST_DOCKER_CONTEXT") or subprocess.check_output(
            ["docker", "context", "show"], text=True).strip()
        controller = staging.Staging({"repository": "DCGM/PeopleGatorApp", "state_dir": str(root / "preview"),
            "docker_context": context, "database_network": os.environ["STAGING_TEST_NETWORK"], "web_network": network,
            "runtime_file": str(runtime), "snapshot": {"path": str(archive),
                "sha256": hashlib.sha256(fixture.archive).hexdigest(), "application_revision": "a" * 40},
            "staging": {"state_dir": str(state), "host": "staging-fixture.example.invalid"}})
        controller.sql = fixture.sql
        controller.infra = lambda *args: ["docker", "exec", "-i", fixture.container,
            *[fixture.username if arg == "preview_admin" else arg for arg in args[3:]]]
        override = state / "compose.test.json"
        override.write_text(json.dumps({"services": {name: {"logging": {"driver": "json-file", "options": {}},
            "environment": {"PEOPLE_GATOR_API__OTEL__ENABLED": "false"}, "restart": "no"}
            for name in ("backend", "migrate", "check")}}))
        project = "staging-test-" + secrets.token_hex(8)
        controller.compose_staging = lambda env, *args: ["docker", "compose", "--project-name", project,
            "--env-file", str(env), "-f", str(staging.INSTALL_DIR / "compose.staging.yaml"), "-f", str(override), *args]
        generation = {"generation": secrets.token_hex(8), "password": secrets.token_hex(32)}
        values = controller.values(generation, {"backend": os.environ["STAGING_TEST_IMAGE"], "frontend": "unused"}, "a" * 40)
        candidate = state / "candidate.env"
        candidate.write_text(controller.dotenv(values))
        try:
            controller.prepare(generation, values, state)
            self.assertEqual(generation["provenance"]["source_schema_revision"], "d34a021b0005")
            self.assertEqual(generation["provenance"]["sha256"], hashlib.sha256(fixture.archive).hexdigest())
            self.assertEqual(generation["provenance"]["data_mode"], "original")
            self.assertEqual(archive.read_bytes(), fixture.archive)
            self.assertNotIn("external-secret", (state / "worker.env").read_text())
            def gate(action, success=True, env_file=candidate):
                if success:
                    controller.command(controller.compose_staging(env_file, "run", "--rm", "--no-deps", action))
                else:
                    with self.assertRaises(DeployError):
                        controller.command(controller.compose_staging(env_file, "run", "--rm", "--no-deps", action))
            for action in ("migrate", "check"):
                gate(action)
            fixture.sql("UPDATE pg_demo_entities SET description='Staging-only edit' WHERE id=(SELECT id FROM pg_demo_entities LIMIT 1)", values["DB_NAME"])
            for action in ("migrate", "check"):
                gate(action)
            self.assertEqual(int(fixture.sql("SELECT count(*) FROM pg_demo_entities WHERE description='Staging-only edit'", values["DB_NAME"])), 1)
            controller.worker("validate", values, state)
            self.assertGreater(int(fixture.sql("SELECT count(*) FROM pg_demo_face_embeddings", values["DB_NAME"])), 0)
            self.assertIn("SENSITIVE-PRODUCTION", fixture.sql("SELECT context FROM pg_demo_text_mentions LIMIT 1", values["DB_NAME"]))
            controller.command(controller.compose_staging(candidate, "up", "-d", "--wait", "--wait-timeout", "90", "backend"))
            backend = controller.command(controller.compose_staging(candidate, "ps", "-q", "backend")).strip()
            inspected = subprocess.check_output(["docker", "inspect", "--format", "{{json .Config.Env}}", backend], text=True)
            self.assertIn("external-secret", inspected)
            script = "import httpx; assert httpx.get('http://127.0.0.1:8000/api/v1/health').json()['status']=='ok'"
            result = subprocess.run(["docker", "exec", backend, "python", "-c", script], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            controller.command(controller.compose_staging(candidate, "stop", "backend"))
            head = fixture.sql("SELECT version_num FROM alembic_version", values["DB_NAME"]).strip()
            for mutation, recovery in (
                ("UPDATE alembic_version SET version_num='unknown_revision'", f"UPDATE alembic_version SET version_num='{head}'"),
                ("ALTER TABLE pg_demo_entities RENAME COLUMN description TO drifted_description", "ALTER TABLE pg_demo_entities RENAME COLUMN drifted_description TO description"),
            ):
                fixture.sql(mutation, values["DB_NAME"])
                gate("check", success=False)
                with self.assertRaises(DeployError):
                    controller.command(controller.compose_staging(candidate, "run", "--rm", "--no-deps", "backend"))
                fixture.sql(recovery, values["DB_NAME"])
                gate("check")
            controller.command(controller.compose_staging(candidate, "up", "-d", "--wait", "--wait-timeout", "90", "backend"))
            self.assertEqual(runtime.read_text(), "PEOPLE_GATOR_API__STORAGE=" + json.dumps(storage) + "\n")
        except Exception:
            diagnostic = state / "last-error.log"
            if diagnostic.exists():
                print(diagnostic.read_text(), file=sys.stderr)  # synthetic fixture only
            raise
        finally:
            controller.command(controller.compose_staging(candidate, "down", "--timeout", "10"))
            fixture.sql(f"DROP DATABASE IF EXISTS {values['DB_NAME']} WITH (FORCE); DROP ROLE IF EXISTS {values['DB_USER']};")


if __name__ == "__main__":
    unittest.main()
