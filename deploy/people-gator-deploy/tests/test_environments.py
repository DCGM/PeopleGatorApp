"""Lifecycle API semantics: prerequisite checks, settings, preservation and actionable failures."""
from contextlib import contextmanager, redirect_stderr
from concurrent.futures import ThreadPoolExecutor
import io
import json
import os
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from people_gator_deploy import cli, environments
from people_gator_deploy.core import DeployError, write_json
from people_gator_deploy.environments import Environment

SHA = "a" * 40
DOCUMENTS = {
    "pr": {"host": "preview.example.invalid", "database": "postgresql://preview_admin:admin-pw@people-gator-postgres:5432/postgres",
           "otel": {"endpoint": "http://lgtm:4318"}},
    "staging": {"host": "staging.example.invalid", "database": "postgresql://preview_admin:admin-pw@people-gator-postgres:5432/postgres",
                "storage": {"s3": {"region": "r", "bucket_name": "staging", "access_key_id": "k", "secret_access_key": "s"}},
                "backup_source": {"endpoint_url": "https://s3.example.invalid", "region": "r", "bucket": "backups", "prefix": "p/",
                                  "access_key_id": "reader", "secret_access_key": "reader-secret"}},
    "release": {"host": "people.example.invalid", "database": "postgresql://app:app-pw@db.internal:5432/people",
                "migration_database": "postgresql://migrator:mig-pw@db.internal:5432/people",
                "storage": {"s3": {"region": "r", "bucket_name": "release", "access_key_id": "k", "secret_access_key": "s"}}},
}


class FakeDocker:
    """Records argument lists; answers only the read-only prerequisite probes."""

    def __init__(self, context=None):
        self.context = "rootless"
        self.calls = []
        self.environments = []
        self.projects = set()
        self.psql_error = None

    def run(self, args, extra_env=None, **kwargs):
        args = [str(value) for value in args]
        self.calls.append(args)
        self.environments.append(extra_env or {})
        if args[:2] == ["docker", "info"]:
            return "synthetic-host"
        if args[:3] == ["docker", "compose", "version"]:
            return "2.40.0\n"
        if args[:2] == ["docker", "run"] and "psql" in args:
            if self.psql_error:
                raise DeployError(self.psql_error)
            return "1\n"
        if args[:2] == ["docker", "ps"] and args[-1].rpartition("=")[2] in self.projects:
            return "existing-container\n"
        return ""

    @contextmanager
    def registry(self):
        yield

    def commands(self, word):
        return [call for call in self.calls if word in call]


class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="environment test ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        docker = patch.object(environments, "Docker", FakeDocker)
        docker.start()
        self.addCleanup(docker.stop)
        self.environment_patch = None
        self.stderr = io.StringIO()

    def configure(self, name="pr", document=None, **changes):
        """Export one environment's configuration as the deploy job would (DEPLOY_CONFIG)."""
        document = {**(DOCUMENTS[name] if document is None else document), **changes}
        document = {k: v for k, v in document.items() if v is not None}
        values = {"GITHUB_REPOSITORY": "DCGM/PeopleGatorApp", "DEPLOY_STATE_DIR": str(self.root / "state" / name),
                  "DEPLOY_CONFIG": json.dumps(document)}
        if self.environment_patch:
            self.environment_patch.stop()
        self.environment_patch = patch.dict(os.environ, values, clear=False)
        self.environment_patch.start()
        self.addCleanup(self.environment_patch.stop)

    def environment(self, name="pr"):
        return Environment(name)

    def preflight(self, environment):
        with redirect_stderr(self.stderr):
            return environment.preflight()

    def test_missing_setting_fails_with_secret_name_and_field_without_side_effects(self):
        self.configure("staging", host=None)
        for operation in ("status", "preflight", "update", "stop"):
            stderr = io.StringIO()
            with self.subTest(operation=operation), redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
                cli.main(["staging", operation])
            self.assertEqual(raised.exception.code, 1)
            self.assertIn("STAGING_CONFIG: host:", stderr.getvalue())
            self.assertIn("deploy/GITHUB-SETUP.md", stderr.getvalue())
            self.assertNotIn("Traceback", stderr.getvalue())
            self.assertNotIn("admin-pw", stderr.getvalue())
        self.assertFalse((self.root / "state").exists())
        for removed in ("install", "uninstall", "infra-upgrade", "configure"):
            with self.subTest(operation=removed), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                cli.main(["pr", removed])
            self.assertEqual(raised.exception.code, 2)

    def test_preflight_checks_the_database_through_the_url_and_renders_the_files(self):
        self.configure()
        environment = self.environment()
        result = environment.preflight()
        self.assertEqual(result["host"], "preview.example.invalid")
        self.assertEqual(result["database"], {"database": "people-gator-postgres:5432/postgres as preview_admin", "network": "people-gator-db"})
        docker = environment.docker
        for network in ("web", "people-gator-db", "logging"):
            self.assertIn(["docker", "network", "inspect", network], docker.calls)
        psql = docker.commands("psql")[0]
        self.assertEqual(psql[:8], ["docker", "run", "--rm", "-i", "--network", "people-gator-db", "-e", "PGPASSWORD"])
        self.assertEqual(psql[8], "pgvector/pgvector:pg16")
        self.assertEqual(psql[psql.index("-h") + 1], "people-gator-postgres")
        self.assertEqual(psql[psql.index("-U") + 1], "preview_admin")
        self.assertNotIn("admin-pw", " ".join(psql))  # the password only travels through the environment
        self.assertEqual(docker.environments[docker.calls.index(psql)], {"PGPASSWORD": "admin-pw"})
        self.assertEqual(docker.commands("compose"), [["docker", "compose", "version", "--short"]])
        root = environment.root
        self.assertEqual(json.loads((root / "users.json").read_text())["test"]["scopes"][0], "people-gator:browse")
        self.assertEqual((root / "users.json").stat().st_mode & 0o777, 0o644)
        self.assertEqual((root / "runtime.env").read_text(), 'PEOPLE_GATOR_API__STORAGE={"local": {"root": "/data"}, "s3": null}\n')
        self.assertIn("PEOPLE_GATOR_API__OTEL__LOGS_ENDPOINT=http://lgtm:4318/v1/logs", (root / "telemetry.env").read_text())
        self.assertFalse((root / "owned.json").exists())
        # Without otel no telemetry file is rendered (a stale one is removed); the
        # stacks still declare the logging network, so it is still checked.
        self.configure(otel=None)
        environment = self.environment()
        environment.preflight()
        self.assertIn(["docker", "network", "inspect", "logging"], environment.docker.calls)
        self.assertFalse((environment.root / "telemetry.env").exists())

    def test_unreachable_database_fails_before_any_compose_command(self):
        self.configure()
        environment = self.environment()
        environment.docker.psql_error = "FATAL"
        with self.assertRaisesRegex(DeployError, "Cannot connect to people-gator-postgres:5432/postgres as preview_admin") as raised:
            environment.update(sha=SHA, pr=7)
        self.assertNotIn("admin-pw", str(raised.exception))
        self.assertEqual([call for call in environment.docker.commands("compose") if "version" not in call], [])
        self.assertFalse((environment.root / "operation.json").exists())
        environment = self.environment()
        environment.docker.psql_error = "FATAL"
        with self.assertRaisesRegex(DeployError, "Cannot connect"):
            environment.cleanup(7)
        self.assertEqual(environment.docker.commands("down"), [])

    def test_missing_network_names_the_convention(self):
        self.configure()
        environment = self.environment()
        original = environment.docker.run
        def run(args, **kwargs):
            if args[:3] == ["docker", "network", "inspect"] and args[3] == "logging":
                raise DeployError("no such network")
            return original(args, **kwargs)
        environment.docker.run = run
        with self.assertRaisesRegex(DeployError, "'logging' does not exist in context 'rootless'"):
            environment.preflight()

    def test_staging_renders_storage_backup_source_and_requires_a_commit(self):
        self.configure("staging")
        environment = self.environment("staging")
        result = environment.preflight()
        self.assertEqual(result["database"]["database"], "people-gator-postgres:5432/postgres as preview_admin")
        root = environment.root
        self.assertIn('"bucket_name": "staging"', (root / "runtime.env").read_text())
        self.assertIn("PEOPLE_GATOR_API__JWK__ISSUER=https://staging.example.invalid", (root / "runtime.env").read_text())
        self.assertEqual(json.loads((root / "snapshot-source.json").read_text())["bucket"], "backups")
        self.assertEqual((root / "snapshot-source.json").stat().st_mode & 0o777, 0o600)
        self.assertFalse((root / "users.json").exists())
        for operation in (environment.update, environment.snapshot_init,
                          lambda: environment.refresh(backup_record="/private/record")):
            with self.subTest(operation=operation), self.assertRaisesRegex(DeployError, "--sha"):
                operation()

    def test_operations_require_build_identity_and_an_active_application(self):
        self.configure()
        environment = self.environment()
        with self.assertRaisesRegex(DeployError, "--pr .* --sha"):
            environment.update(sha=SHA)
        with self.assertRaisesRegex(DeployError, "--pr .* --sha"):
            environment.update(pr=5)
        for operation in (lambda: environment.stop(1), lambda: environment.logs(1), lambda: environment.start(1)):
            with self.subTest(operation=operation), self.assertRaisesRegex(DeployError, "no active application.*pr update"):
                with redirect_stderr(self.stderr):
                    operation()
        status = environment.status()
        self.assertEqual((status["configured"], status["instances"]), (True, []))
        self.assertEqual(environment.docker.commands("up"), [])

    def test_release_checks_both_roles_and_renders_their_files(self):
        self.configure("release")
        environment = self.environment("release")
        with self.assertRaisesRegex(DeployError, "--tag"):
            environment.update()
        result = environment.preflight()
        self.assertEqual(result["database"]["database"], "db.internal:5432/people as app")
        self.assertEqual(result["migration_database"]["database"], "db.internal:5432/people as migrator")
        self.assertIn(["docker", "network", "inspect", "people-gator-db"], environment.docker.calls)
        passwords = [env.get("PGPASSWORD") for env in environment.docker.environments if env]
        self.assertEqual(passwords, ["app-pw", "mig-pw"])
        root = environment.root
        self.assertIn("PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__USER=app\n", (root / "runtime.env").read_text())
        self.assertIn("PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__USER=migrator\n", (root / "migration.env").read_text())
        self.assertNotIn("mig-pw", (root / "runtime.env").read_text())
        self.assertEqual((root / "migration.env").stat().st_mode & 0o777, 0o600)
        # A changed secret is republished on the next operation; a loosened mode is restored.
        (root / "runtime.env").chmod(0o644)
        self.configure("release", extra_env={"PEOPLE_GATOR_API__OPENROUTER__API_KEY": "sk-2"})
        self.environment("release").preflight()
        self.assertEqual((root / "runtime.env").stat().st_mode & 0o777, 0o600)
        self.assertIn("sk-2", (root / "runtime.env").read_text())
        # One role: no second check, no separate password.
        self.configure("release", migration_database=None)
        environment = self.environment("release")
        self.assertNotIn("migration_database", environment.preflight())

    def test_release_refuses_an_existing_application_project_without_claiming_it(self):
        self.configure("release")
        environment = self.environment("release")
        environment.docker.projects.add("people-gator-release")
        with self.assertRaisesRegex(DeployError, "without owned application state"):
            environment.update(tag="v1.0.0")
        self.assertEqual(environment.docker.commands("pull"), [])
        self.assertFalse((environment.root / "operation.json").exists())
        self.assertFalse((environment.root / "compose.env").exists())

    def test_simultaneous_snapshot_initializations_cannot_replace_committed_data(self):
        self.configure("staging")
        environment = self.environment("staging")
        calls = []
        def deploy(sha, *, refresh):
            calls.append((sha, refresh))
            write_json(environment.root / "state.json", {"generation": "first", "reviewed_edit": "keep"})
        controller = SimpleNamespace(deploy=deploy, check_database=lambda role="postgres": {})
        barrier = threading.Barrier(2)
        original_lock = Environment.environment_lock
        @contextmanager
        def synchronized_lock(instance):
            barrier.wait(timeout=10)
            with original_lock(instance):
                yield
        def initialize():
            try:
                with redirect_stderr(io.StringIO()):
                    environment.snapshot_init(sha=SHA)
            except DeployError as error:
                return str(error)
            return "initialized"
        with patch.object(Environment, "environment_lock", synchronized_lock), \
                patch.object(environment, "controller", return_value=controller), ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(initialize) for _ in range(2)]
            outcomes = [future.result(timeout=15) for future in futures]
        self.assertEqual(outcomes.count("initialized"), 1)
        self.assertTrue(any("refresh" in result and "backup-record" in result for result in outcomes))
        self.assertEqual(calls, [(SHA, True)])
        self.assertEqual(json.loads((environment.root / "state.json").read_text())["reviewed_edit"], "keep")
        journal = json.loads((environment.root / "operation.json").read_text())
        self.assertEqual((journal["operation"], journal["phase"]), ("snapshot-init", "complete"))

    def test_configuration_secrets_never_reach_docker_subprocess_environments(self):
        from people_gator_deploy.docker import Docker
        with patch.dict(os.environ, {"DEPLOY_CONFIG": "{}", "PGPASSWORD": "ambient", "DEPLOY_STATE_DIR": "/x"}):
            environment = Docker("rootless").environment({"PGPASSWORD": "explicit"})
        self.assertFalse(any(key.startswith("DEPLOY_") for key in environment))
        self.assertEqual(environment["PGPASSWORD"], "explicit")
        self.assertNotIn("PGPASSWORD", Docker("rootless").environment())


if __name__ == "__main__":
    unittest.main()
