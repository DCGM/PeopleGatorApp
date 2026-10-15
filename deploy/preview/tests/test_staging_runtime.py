"""Opt-in candidate-image gates on an entirely disposable PostgreSQL server.

Requires the backend venv, STAGING_TEST_IMAGE, STAGING_TEST_POSTGRES_CONTAINER,
STAGING_TEST_DATABASE_PORT and an isolated Docker network with alias
preview-postgres. Never point this suite at shared infrastructure.
"""
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

    def test_real_restore_sanitize_image_migration_check_and_lifespan_gates(self):
        fixture = snapshot_tests.SnapshotIntegrationTests
        image = os.environ["STAGING_TEST_IMAGE"]
        network = os.environ["STAGING_TEST_NETWORK"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            private = root / "private"
            private.mkdir()
            (root / "preview").mkdir()
            state = root / "staging"
            state.mkdir()
            controller = staging.Staging({"repository": "DCGM/PeopleGatorApp", "state_dir": str(root / "preview"),
                "database_network": network, "staging": {"state_dir": str(state), "private_dir": str(private),
                    "auth_volume": "people-gator-staging-test-" + secrets.token_hex(8) + "-auth"}})
            controller.sql = fixture.sql
            def infra(*args):
                return ["docker", "exec", "-i", fixture.container,
                        *[fixture.username if arg == "preview_admin" else arg for arg in args[3:]]]
            controller.infra = infra
            generation = {"generation": secrets.token_hex(8), "password": secrets.token_hex(32)}
            values = controller.values(generation, {"backend": image, "frontend": "unused"}, "a" * 40)
            candidate = state / "candidate.env"
            candidate.write_text(controller.dotenv(values))
            import argon2
            hasher = argon2.PasswordHasher()
            supplied = {"users": {name: {"hash": hasher.hash("private-synthetic-staging-password")} for name in snapshot.EXAMPLE_SCOPES},
                        "api_keys": {}}
            (private / "credential-input.json").write_text(json.dumps(supplied))
            (private / "media-policy.json").write_text('{"permitted_page_ids":[]}')
            real_worker = controller.worker
            def worker(action, values, directory, *, work=None, **kwargs):
                if action == "download":
                    (work / "snapshot.dump").write_bytes(fixture.archive)
                    (work / "provenance.json").write_text(json.dumps({"bucket": "synthetic", "key": "synthetic.dump"}))
                    return ""
                return real_worker(action, values, directory, **kwargs)
            controller.worker = worker
            # Replace only Compose storage initialization; actual worker performs ownership.
            controller.compose_staging = lambda env, *args: ["true"]
            names = []
            try:
                controller.prepare(generation, values, state, candidate, "")
                self.assertEqual(generation["provenance"]["source_schema_revision"], "d34a021b0005")
                self.assertEqual(list(state.glob("snapshot-*")), [])
                # Worker contains the same isolated runtime DB/storage configuration.
                env_file = state / "worker.env"
                # Runtime image gate uses the deployed unprivileged database role.
                common = ["docker", "run", "--rm", "--log-driver", "none", "--network", network,
                          "--env-file", str(env_file)]
                def run_gate(action, success=True, environment_file=None):
                    name = "staging-test-api-" + secrets.token_hex(6)
                    names.append(name)
                    args = common.copy()
                    if environment_file:
                        args[args.index("--env-file") + 1] = str(environment_file)
                    result = subprocess.run([*args, "--name", name, image, action], capture_output=True, timeout=40)
                    self.assertEqual(result.returncode == 0, success, result.stderr.decode()[-1500:])
                run_gate("migrate")
                run_gate("check")
                run_gate("migrate")
                run_gate("check")
                controller.worker("validate", values, state)
                for failure, mutation, recovery in (
                    ("stale", "UPDATE alembic_version SET version_num='unknown_revision'", "UPDATE alembic_version SET version_num='d34a021b0006'"),
                    ("drift", "ALTER TABLE pg_demo_entities RENAME COLUMN description TO drifted_description", "ALTER TABLE pg_demo_entities RENAME COLUMN drifted_description TO description"),
                ):
                    with self.subTest(failure=failure):
                        fixture.sql(mutation, values["DB_NAME"])
                        run_gate("check", success=False)
                        run_gate("api", success=False)  # real lifespan independently rejects it
                        fixture.sql(recovery, values["DB_NAME"])
                        run_gate("check")
                # Configured wrong existing database: full check and lifespan both fail.
                empty = "staging_" + secrets.token_hex(8)
                fixture.sql(f"CREATE DATABASE {empty};")
                try:
                    wrong = state / "wrong.env"
                    content = env_file.read_text().replace(values["DB_NAME"], empty)
                    # Replacing the user too would test auth rather than missing schema.
                    config = json.loads(content.splitlines()[0].split("=", 1)[1])
                    config["postgres"]["user"] = values["DB_USER"]
                    fixture.sql(f"GRANT CONNECT ON DATABASE {empty} TO {values['DB_USER']};")
                    content = "PEOPLE_GATOR_API__PERSISTENCE=" + json.dumps(config) + "\n" + "\n".join(content.splitlines()[1:])
                    wrong.write_text(content)
                    run_gate("check", success=False, environment_file=wrong)
                    run_gate("api", success=False, environment_file=wrong)
                finally:
                    fixture.sql(f"DROP DATABASE {empty} WITH (FORCE);")
                # Actual healthy API, then a later container restart rechecks revision.
                name = "staging-test-api-" + secrets.token_hex(6)
                names.append(name)
                args = common.copy()
                args.remove("--rm")
                subprocess.run([*args, "-d", "--name", name, image, "api"], capture_output=True, check=True)
                import time
                for attempt in range(40):
                    health = subprocess.run(["docker", "exec", name, "python", "-c",
                        "import urllib.request; assert urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health').status == 200"], capture_output=True)
                    if health.returncode == 0:
                        break
                    time.sleep(0.25)
                self.assertEqual(health.returncode, 0)
                subprocess.run(["docker", "stop", "-t", "10", name], check=True, capture_output=True)
                fixture.sql("UPDATE alembic_version SET version_num='unknown_revision'", values["DB_NAME"])
                subprocess.run(["docker", "start", name], check=True, capture_output=True)
                result = subprocess.run(["docker", "wait", name], timeout=40, check=True, capture_output=True)
                self.assertNotEqual(result.stdout.strip(), b"0")
            except Exception:
                # Synthetic fixture diagnostics only; this suite never uses production inputs.
                diagnostic = state / "last-error.log"
                if diagnostic.exists():
                    print(diagnostic.read_text(), file=sys.stderr)
                raise
            finally:
                for name in names:
                    subprocess.run(["docker", "rm", "-f", name], capture_output=True)
                fixture.sql(f"DROP DATABASE IF EXISTS {values['DB_NAME']} WITH (FORCE); DROP ROLE IF EXISTS {values['DB_USER']};")
                for volume in (values["MEDIA_VOLUME"], values["AUTH_VOLUME"]):
                    subprocess.run(["docker", "volume", "rm", volume], capture_output=True)


if __name__ == "__main__":
    unittest.main()
