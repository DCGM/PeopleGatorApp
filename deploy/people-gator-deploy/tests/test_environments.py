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

from people_gator_deploy import cli
from people_gator_deploy.core import DeployError, write_json
from people_gator_deploy.environments import Environment

SHA = "a" * 40
POSTGRES = {"State": {"Running": True},
            "NetworkSettings": {"Networks": {"people-gator-preview-db": {"Aliases": ["preview-postgres", "abc123"]}}}}


class FakeDocker:
    """Records argument lists; answers only the read-only prerequisite probes."""

    def __init__(self):
        self.context = "rootless"
        self.calls = []
        self.projects = set()
        self.postgres = json.loads(json.dumps(POSTGRES))  # inspected shared PostgreSQL container
        self.psql_error = None

    def run(self, args, **kwargs):
        args = [str(value) for value in args]
        self.calls.append(args)
        if args[:2] == ["docker", "info"]:
            return "synthetic-host"
        if args[:3] == ["docker", "compose", "version"]:
            return "2.40.0\n"
        if args[:3] == ["docker", "container", "inspect"]:
            if self.postgres is None:
                raise DeployError("inspect failed")
            return json.dumps([self.postgres])
        if args[:2] == ["docker", "exec"]:
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
        # Every GitHub variable the deploy jobs pass, for all three environments.
        self.variables = {
            "GITHUB_REPOSITORY": "DCGM/PeopleGatorApp", "DEPLOY_DOCKER_CONTEXT": "rootless", "DEPLOY_WEB_NETWORK": "web",
            "DEPLOY_DATABASE_NETWORK": "people-gator-preview-db", "DEPLOY_POSTGRES_CONTAINER": "people-gator-postgres",
            "DEPLOY_DOMAIN": "preview.example.invalid", "DEPLOY_HOST": "staging.example.invalid", "DEPLOY_USERS_JSON": "{}",
            "DEPLOY_RUNTIME_ENV": "# External application storage and auth settings\n",
        }
        self.environment_patch = None
        self.stderr = io.StringIO()

    def configure(self, name="pr", **changes):
        """Export one environment's settings as the deploy job would."""
        values = {**self.variables, "DEPLOY_STATE_DIR": str(self.root / "state" / name), **changes}
        if self.environment_patch:
            self.environment_patch.stop()
        self.environment_patch = patch.dict(os.environ, {k: v for k, v in values.items() if v is not None}, clear=False)
        self.environment_patch.start()
        for removed in [k for k, v in changes.items() if v is None]:
            os.environ.pop(removed, None)
        self.addCleanup(self.environment_patch.stop)

    def environment(self, name="pr"):
        environment = Environment(name)
        environment.docker = FakeDocker()
        return environment

    def preflight(self, environment):
        with redirect_stderr(self.stderr):
            return environment.preflight()

    def test_missing_setting_fails_with_variable_name_and_remedy_without_side_effects(self):
        self.configure("staging", DEPLOY_HOST=None)
        for operation in ("status", "preflight", "update", "stop"):
            stderr = io.StringIO()
            with self.subTest(operation=operation), redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
                cli.main(["staging", operation])
            self.assertEqual(raised.exception.code, 1)
            self.assertIn("staging configuration: DEPLOY_HOST", stderr.getvalue())
            self.assertIn("GitHub Environment", stderr.getvalue())
            self.assertNotIn("Traceback", stderr.getvalue())
        self.assertFalse((self.root / "state").exists())
        for removed in ("install", "uninstall", "infra-upgrade", "configure"):
            with self.subTest(operation=removed), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                cli.main(["pr", removed])
            self.assertEqual(raised.exception.code, 2)

    def test_invalid_secret_fails_before_docker_or_writes(self):
        self.configure(DEPLOY_USERS_JSON="not json")
        environment = self.environment()
        with self.assertRaisesRegex(DeployError, "DEPLOY_USERS_JSON"):
            environment.preflight()
        self.assertEqual(environment.docker.calls, [])
        self.assertFalse((self.root / "state").exists())

    def test_preflight_checks_the_operator_run_infrastructure_and_publishes_secret_files(self):
        self.configure()
        environment = self.environment()
        result = self.preflight(environment)
        self.assertEqual(result["infrastructure"], {"postgres_container": "people-gator-postgres",
                                                    "database_network": "people-gator-preview-db"})
        inspected = environment.docker.commands("inspect")
        self.assertIn(["docker", "network", "inspect", "people-gator-preview-db"], inspected)
        self.assertIn(["docker", "network", "inspect", "logging"], inspected)
        self.assertIn(["docker", "container", "inspect", "people-gator-postgres"], inspected)
        psql = environment.docker.commands("psql")[0]
        self.assertEqual(psql[:5], ["docker", "exec", "-i", "people-gator-postgres", "psql"])
        self.assertIn("preview_admin", psql)
        self.assertEqual(environment.docker.commands("compose"), [["docker", "compose", "version", "--short"]])
        # Secret contents became private files the Compose stacks can reference.
        users = environment.root / "users.json"
        self.assertEqual(users.read_text(), "{}")
        self.assertEqual(users.stat().st_mode & 0o777, 0o644)
        self.assertFalse((environment.root / "owned.json").exists())

    def test_missing_or_broken_shared_postgres_fails_before_any_compose_command(self):
        self.configure()
        cases = (
            (lambda docker: setattr(docker, "postgres", None), "does not exist"),
            (lambda docker: docker.postgres["State"].update(Running=False), "is not running"),
            (lambda docker: docker.postgres["NetworkSettings"]["Networks"].clear(), "alias preview-postgres"),
            (lambda docker: docker.postgres["NetworkSettings"]["Networks"]["people-gator-preview-db"].update(Aliases=["pg"]),
             "alias preview-postgres"),
            (lambda docker: setattr(docker, "psql_error", "FATAL"), "DEPLOY_POSTGRES_ADMIN_USER"),
        )
        for change, message in cases:
            environment = self.environment()
            change(environment.docker)
            with self.subTest(message=message), self.assertRaisesRegex(DeployError, message) as raised:
                environment.update(sha=SHA, pr=7)
            self.assertIn("people-gator-postgres", str(raised.exception))
            self.assertEqual([call for call in environment.docker.commands("compose") if "version" not in call], [])
            self.assertFalse((environment.root / "operation.json").exists())
        environment = self.environment()
        environment.docker.psql_error = "FATAL"
        with self.assertRaisesRegex(DeployError, "psql"):
            environment.cleanup(7)
        self.assertEqual(environment.docker.commands("down"), [])

    def test_missing_network_names_its_setting(self):
        self.configure(DEPLOY_OTEL_NETWORK="observability")
        environment = self.environment()
        original = environment.docker.run
        def run(args, **kwargs):
            if args[:3] == ["docker", "network", "inspect"] and args[3] == "observability":
                raise DeployError("no such network")
            return original(args, **kwargs)
        environment.docker.run = run
        with self.assertRaisesRegex(DeployError, "'observability'.*DEPLOY_OTEL_NETWORK"):
            environment.preflight()

    def test_staging_shares_the_preview_postgres_and_validates_its_runtime_secret(self):
        self.configure("staging", DEPLOY_POSTGRES_CONTAINER="shared-pg", DEPLOY_POSTGRES_ADMIN_USER="dba")
        environment = self.environment("staging")
        result = self.preflight(environment)
        self.assertEqual(result["infrastructure"]["postgres_container"], "shared-pg")
        self.assertIn(["docker", "container", "inspect", "shared-pg"], environment.docker.calls)
        self.assertIn("dba", environment.docker.commands("psql")[0])
        runtime = environment.root / "runtime.env"
        self.assertEqual(runtime.stat().st_mode & 0o777, 0o600)
        os.environ["DEPLOY_RUNTIME_ENV"] = "PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__DATABASE=mine\n"
        with self.assertRaisesRegex(DeployError, "persistence settings are managed"):
            self.environment("staging").preflight()
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

    def configure_release(self):
        self.configure("release", DEPLOY_HOST="people.example.invalid", DEPLOY_DATABASE_NETWORK="production-db",
                       DEPLOY_RUNTIME_ENV="PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__USER=runtime\n"
                                          "PEOPLE_GATOR_API__STORAGE__S3__BUCKET_NAME=release\n",
                       DEPLOY_MIGRATION_ENV="PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__USER=migrator\n",
                       DEPLOY_ACCESS_REVIEWED="true")

    def test_release_requires_reviewed_access_and_publishes_private_role_files(self):
        self.configure_release()
        os.environ.pop("DEPLOY_ACCESS_REVIEWED")
        with self.assertRaisesRegex(DeployError, "DEPLOY_ACCESS_REVIEWED"):
            Environment("release")
        self.configure_release()
        environment = self.environment("release")
        with self.assertRaisesRegex(DeployError, "--tag"):
            environment.update()
        result = environment.preflight()
        self.assertNotIn("infrastructure", result)  # the external production PostgreSQL is checked by the stack's check service
        self.assertIn(["docker", "network", "inspect", "production-db"], environment.docker.calls)
        self.assertEqual(environment.docker.commands("exec"), [])
        runtime = environment.root / "runtime.env"
        self.assertEqual(runtime.stat().st_mode & 0o777, 0o600)
        self.assertIn("runtime", runtime.read_text())
        self.assertNotIn("migrator", runtime.read_text())
        # A changed secret is republished on the next operation; a loosened mode is restored.
        runtime.chmod(0o644)
        os.environ["DEPLOY_RUNTIME_ENV"] = ("PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__USER=runtime2\n"
                                            "PEOPLE_GATOR_API__STORAGE__S3__BUCKET_NAME=release\n")
        environment.preflight()
        self.assertEqual(runtime.stat().st_mode & 0o777, 0o600)
        self.assertIn("runtime2", runtime.read_text())
        os.environ["DEPLOY_RUNTIME_ENV"] = "PEOPLE_GATOR_API__DEBUG=true\n"
        with self.assertRaisesRegex(DeployError, "DEBUG"):
            self.environment("release").preflight()

    def test_release_refuses_an_existing_application_project_without_claiming_it(self):
        self.configure_release()
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
        controller = SimpleNamespace(deploy=deploy, check_infrastructure=lambda: {}, validate_inputs=lambda: None)
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

    def test_settings_never_reach_docker_subprocess_environments(self):
        self.assertTrue(all(name.startswith("DEPLOY_") for name in self.variables if name != "GITHUB_REPOSITORY"))
        from people_gator_deploy.docker import Docker
        with patch.dict(os.environ, {**self.variables, "DEPLOY_STATE_DIR": "/x"}):
            self.assertFalse(any(key.startswith("DEPLOY_") for key in Docker("rootless").environment()))


if __name__ == "__main__":
    unittest.main()
