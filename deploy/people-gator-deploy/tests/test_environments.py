"""Lifecycle API semantics: ownership, idempotence, preservation and actionable failures."""
from contextlib import contextmanager, redirect_stderr
from concurrent.futures import ThreadPoolExecutor
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from people_gator_deploy import cli, config
from people_gator_deploy.core import DeployError, write_json
from people_gator_deploy.environments import Environment

SHA = "a" * 40


class FakeDocker:
    """Records argument lists; answers only the read-only prerequisite probes."""

    def __init__(self):
        self.context = "rootless"
        self.calls = []
        self.projects = set()

    def run(self, args, **kwargs):
        args = [str(value) for value in args]
        self.calls.append(args)
        if args[:2] == ["docker", "info"]:
            return "synthetic-host"
        if args[:3] == ["docker", "compose", "version"]:
            return "2.40.0\n"
        if args[:2] == ["docker", "ps"] and args[-1].rpartition("=")[2] in self.projects:
            return "existing-container\n"
        return ""

    @contextmanager
    def registry(self):
        yield

    def commands(self, word):
        return [call for call in self.calls if word in call]


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*"))
            if p.is_file() and not p.name.endswith(".lock")}


class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="environment test ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.infra = self.root / "state/infrastructure"
        # Every GitHub Environment variable the deploy jobs pass, for all three environments.
        self.variables = {
            "GITHUB_REPOSITORY": "DCGM/PeopleGatorApp", "DEPLOY_DOCKER_CONTEXT": "rootless", "DEPLOY_WEB_NETWORK": "web",
            "DEPLOY_DATABASE_NETWORK": "people-gator-preview-db", "DEPLOY_INFRASTRUCTURE_STATE_DIR": str(self.infra),
            "DEPLOY_INFRASTRUCTURE_PROJECT": "people-gator-preview-infra", "DEPLOY_DOMAIN": "preview.example.invalid",
            "DEPLOY_HOST": "staging.example.invalid", "DEPLOY_USERS_JSON": "{}",
            "DEPLOY_RUNTIME_ENV": "# External application storage and auth settings\n",
        }
        self.environment_patch = None

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

    def test_missing_setting_fails_with_variable_name_and_remedy_without_side_effects(self):
        self.configure("staging", DEPLOY_HOST=None)
        for operation in ("status", "install", "update", "uninstall"):
            stderr = io.StringIO()
            with self.subTest(operation=operation), redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
                cli.main(["staging", operation])
            self.assertEqual(raised.exception.code, 1)
            self.assertIn("staging configuration: DEPLOY_HOST", stderr.getvalue())
            self.assertIn("GitHub Environment", stderr.getvalue())
            self.assertNotIn("Traceback", stderr.getvalue())
        self.assertFalse((self.root / "state").exists())

    def test_invalid_secret_fails_before_docker_or_writes(self):
        self.configure(DEPLOY_USERS_JSON="not json")
        environment = self.environment()
        with self.assertRaisesRegex(DeployError, "DEPLOY_USERS_JSON"):
            environment.install()
        self.assertEqual(environment.docker.calls, [])
        self.assertFalse((self.root / "state").exists())

    def test_install_is_idempotent_and_preserves_generated_credentials(self):
        self.configure()
        environment = self.environment()
        self.assertTrue(environment.install()["changed"])
        owner = json.loads((self.infra / "infrastructure-owned.json").read_text())
        self.assertEqual(owner["environment"], "pr")
        credentials = (self.infra / "infrastructure.env").read_bytes()
        self.assertEqual(len(environment.docker.commands("up")), 1)
        # Secret contents became private files the Compose stacks can reference.
        users = environment.root / "users.json"
        self.assertEqual(users.read_text(), "{}")
        self.assertEqual(users.stat().st_mode & 0o777, 0o644)
        environment.docker.calls.clear()
        self.assertFalse(environment.install()["changed"])
        self.assertEqual(environment.docker.commands("up"), [])
        self.assertEqual((self.infra / "infrastructure.env").read_bytes(), credentials)
        self.assertTrue(all(isinstance(call, list) for call in environment.docker.calls))

    def test_markers_written_by_descriptor_based_releases_remain_valid(self):
        self.configure()
        environment = self.environment()
        environment.root.mkdir(parents=True)
        write_json(environment.root / "owned.json", {"schema_version": 1, "owner": "f" * 64, "environment": "pr", "phase": "installed"})
        self.infra.mkdir(parents=True)
        write_json(self.infra / "infrastructure-owned.json", {"owner": "f" * 64, "environment": "pr", "project": "people-gator-preview-infra", "schema_version": 1})
        (self.infra / "infrastructure.env").write_text("POSTGRES_ADMIN_PASSWORD='retained'\n")
        self.assertTrue(environment.preflight()["provisioned"])
        self.assertFalse(environment.install()["changed"])
        environment.infra_upgrade()
        self.assertIn("retained", (self.infra / "infrastructure.env").read_text())
        write_json(environment.root / "owned.json", {"schema_version": 1, "environment": "staging", "phase": "installed"})
        with self.assertRaisesRegex(DeployError, "belong to the 'staging' environment"):
            environment.status()

    def test_installation_is_fresh_only_and_never_takes_over_unowned_state(self):
        self.configure()
        state = self.root / "state/pr"
        state.mkdir(parents=True)
        (state / "pr-7").mkdir()
        (state / "pr-7/state.json").write_text("{}")
        before = snapshot(state)
        environment = self.environment()
        with self.assertRaisesRegex(DeployError, "not empty and not owned"):
            environment.install()
        self.assertEqual({k: v for k, v in snapshot(state).items() if k != "users.json"}, before)
        self.assertEqual(environment.docker.commands("up"), [])
        self.infra.mkdir(parents=True, exist_ok=True)  # the lock file already created it
        (self.infra / "infrastructure.env").write_text("POSTGRES_ADMIN_PASSWORD='unowned'\n")
        shutil.rmtree(state / "pr-7")
        with self.assertRaisesRegex(DeployError, "without an owner"):
            environment.install()
        self.assertEqual((self.infra / "infrastructure.env").read_text(), "POSTGRES_ADMIN_PASSWORD='unowned'\n")

    def test_staging_shares_but_cannot_change_preview_infrastructure(self):
        self.configure()
        self.environment().install()
        credentials = (self.infra / "infrastructure.env").read_bytes()
        self.configure("staging")
        external = self.environment("staging")
        self.assertEqual(external.settings["infrastructure"]["mode"], "external")
        self.assertTrue(external.install()["changed"])
        with self.assertRaisesRegex(DeployError, "managed infrastructure owner"):
            external.infra_upgrade()
        with self.assertRaisesRegex(DeployError, "Unsupported staging operation"):
            external.execute("infra-upgrade")
        self.assertEqual((self.infra / "infrastructure.env").read_bytes(), credentials)
        self.assertEqual(external.docker.commands("up"), [])
        # Without the preview infrastructure, staging cannot be installed at all.
        (self.infra / "infrastructure.env").unlink()
        self.configure("staging", DEPLOY_STATE_DIR=str(self.root / "state/staging-2"))
        with self.assertRaisesRegex(DeployError, "pr install first"):
            self.environment("staging").install()

    def test_uninstall_stops_only_owned_instances_and_preserves_data(self):
        self.configure()
        environment = self.environment()
        environment.install()
        preview = environment.root / "pr-12"
        preview.mkdir()
        (preview / "state.json").write_text('{"password":"' + "c" * 64 + '"}')
        (preview / "compose.env").write_text("retained")
        before = snapshot(preview)
        result = environment.uninstall()
        self.assertTrue(result["data_preserved"])
        downs = environment.docker.commands("down")
        self.assertEqual(len(downs), 1)
        self.assertIn("people-gator-pr-12", downs[0])
        self.assertNotIn("--volumes", downs[0])
        self.assertFalse(any("people-gator-preview-infra" in call for call in downs))
        self.assertEqual(snapshot(preview), before)
        self.assertTrue((self.infra / "infrastructure.env").exists())
        with self.assertRaisesRegex(DeployError, "not installed.*pr install"):
            environment.update(sha=SHA, pr=5)
        self.assertTrue(environment.install()["changed"])

    def test_operations_require_installation_and_build_identity(self):
        self.configure()
        environment = self.environment()
        for operation in (lambda: environment.stop(1), lambda: environment.cleanup(1), environment.reconcile,
                          lambda: environment.logs(1)):
            with self.subTest(operation=operation), self.assertRaisesRegex(DeployError, "install"):
                operation()
        with self.assertRaisesRegex(DeployError, "--pr .* --sha"):
            environment.update(sha=SHA)
        with self.assertRaisesRegex(DeployError, "--pr .* --sha"):
            environment.update(pr=5)
        status = environment.status()
        self.assertEqual((status["configured"], status["provisioned"]), (True, False))
        self.assertFalse((self.root / "state").exists())
        self.configure("staging")
        staging = self.environment("staging")
        for operation in (staging.update, staging.snapshot_init, lambda: staging.refresh(backup_record="/private/record")):
            with self.subTest(operation=operation), self.assertRaisesRegex(DeployError, "--sha"):
                operation()

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
        self.assertTrue(environment.install()["changed"])
        self.assertIn(["docker", "network", "inspect", "production-db"], environment.docker.calls)
        self.assertEqual(environment.preflight()["provisioned"], True)
        self.assertFalse(environment.install()["changed"])
        runtime = environment.root / "runtime.env"
        self.assertEqual(runtime.stat().st_mode & 0o777, 0o600)
        self.assertIn("runtime", runtime.read_text())
        self.assertNotIn("migrator", runtime.read_text())
        # A changed secret is republished on the next operation; a loosened mode is restored.
        runtime.chmod(0o644)
        os.environ["DEPLOY_RUNTIME_ENV"] = "PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__USER=runtime2\n"
        environment.preflight()
        self.assertEqual(runtime.stat().st_mode & 0o777, 0o600)
        self.assertIn("runtime2", runtime.read_text())
        os.environ["DEPLOY_RUNTIME_ENV"] = "PEOPLE_GATOR_API__DEBUG=true\n"
        with self.assertRaisesRegex(DeployError, "DEBUG"):
            self.environment("release").update(tag="v1.0.0")

    def test_release_refuses_an_existing_application_project_without_claiming_it(self):
        self.configure_release()
        environment = self.environment("release")
        environment.docker.projects.add("people-gator-release")
        with self.assertRaisesRegex(DeployError, "Compose project people-gator-release already exist"):
            environment.install()
        self.assertFalse((environment.root / "owned.json").exists())
        self.assertEqual(environment.docker.commands("up"), [])
        # A project that appears between installation and first deployment is
        # refused too, before login, image pulls, migrations or activation.
        environment.docker.projects.clear()
        environment.install()
        environment.docker.projects.add("people-gator-release")
        environment.docker.calls.clear()
        with self.assertRaisesRegex(DeployError, "without owned application state"):
            environment.update(tag="v1.0.0")
        self.assertEqual(environment.docker.commands("pull"), [])
        self.assertFalse((environment.root / "operation.json").exists())

    def test_simultaneous_snapshot_initializations_cannot_replace_committed_data(self):
        self.configure()
        self.environment().install()
        self.configure("staging")
        environment = self.environment("staging")
        environment.install()
        calls = []
        def deploy(sha, *, refresh):
            calls.append((sha, refresh))
            write_json(environment.root / "state.json", {"generation": "first", "reviewed_edit": "keep"})
        controller = SimpleNamespace(deploy=deploy)
        barrier = threading.Barrier(2)
        original_lock = Environment.environment_lock
        @contextmanager
        def synchronized_lock(instance, **kwargs):
            barrier.wait(timeout=10)
            with original_lock(instance, **kwargs):
                yield
        def initialize():
            try:
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
