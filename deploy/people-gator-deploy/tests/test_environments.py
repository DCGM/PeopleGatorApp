"""Lifecycle API semantics: ownership, idempotence, preservation and actionable failures."""
from contextlib import contextmanager, redirect_stderr
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from people_gator_deploy import cli, config
from people_gator_deploy.core import DeployError, write_json
from people_gator_deploy.environments import Environment


class FakeDocker:
    """Records argument lists; answers only the read-only prerequisite probes."""

    def __init__(self):
        self.context = "rootless"
        self.calls = []

    def run(self, args, **kwargs):
        args = [str(value) for value in args]
        self.calls.append(args)
        if args[:2] == ["docker", "info"]:
            return "synthetic-host"
        if args[:3] == ["docker", "compose", "version"]:
            return "2.40.0\n"
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
        environment = patch.dict(os.environ, {"GITHUB_REPOSITORY": "DCGM/PeopleGatorApp"})
        environment.start()
        self.addCleanup(environment.stop)
        self.users = self.root / "private/users.json"
        self.users.parent.mkdir()
        self.users.write_text("{}")
        self.users.chmod(0o644)
        self.infra = self.root / "state/preview"

    def descriptor(self, name="pr", **changes):
        path = self.root / f"environments/{name}/config.json"
        value = {"repository": "DCGM/PeopleGatorApp", "state_dir": str(self.infra), "docker_context": "rootless",
                 "web_network": "web", "database_network": "people-gator-preview-db",
                 "infrastructure": {"mode": "managed", "project": "people-gator-preview-infra",
                                    "state_dir": str(self.infra)}}
        if name == "pr":
            value.update(domain="preview.example.invalid", users_file=str(self.users))
        else:
            value.update(host="staging.example.invalid", state_dir=str(self.root / "state/staging"),
                         storage={"endpoint_url": "https://s3.example.invalid", "region": "synthetic", "bucket_name": "staging-bucket",
                                  "access_key_id": "synthetic", "secret_access_key": "synthetic"})
        config.configure(name, path, {**value, **changes})
        return path

    def environment(self, path, name="pr"):
        environment = Environment(name, path)
        environment.docker = FakeDocker()
        return environment

    def test_missing_descriptor_fails_with_path_field_and_command_without_side_effects(self):
        path = self.root / "environments/staging/config.json"
        for operation in ("status", "install", "update", "uninstall"):
            stderr = io.StringIO()
            with self.subTest(operation=operation), redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
                cli.main(["staging", operation, "--config", str(path)])
            self.assertEqual(raised.exception.code, 1)
            self.assertIn(str(path), stderr.getvalue())
            self.assertIn("people-gator-deploy staging configure", stderr.getvalue())
            self.assertNotIn("Traceback", stderr.getvalue())
        self.assertFalse((self.root / "state").exists())
        self.assertFalse(path.parent.exists())

    def test_incomplete_private_inputs_fail_before_docker_or_writes(self):
        path = self.descriptor()
        self.users.chmod(0o666)
        environment = self.environment(path)
        with self.assertRaisesRegex(DeployError, "users_file"):
            environment.install()
        self.assertEqual(environment.docker.calls, [])
        self.assertFalse(self.infra.exists())

    def test_install_is_idempotent_and_preserves_generated_credentials(self):
        environment = self.environment(self.descriptor())
        self.assertTrue(environment.install()["changed"])
        owner = json.loads((self.infra / "infrastructure-owned.json").read_text())
        self.assertEqual(owner["owner"], environment.identity)
        credentials = (self.infra / "infrastructure.env").read_bytes()
        self.assertEqual(len(environment.docker.commands("up")), 1)
        environment.docker.calls.clear()
        self.assertFalse(environment.install()["changed"])
        self.assertEqual(environment.docker.commands("up"), [])
        self.assertEqual((self.infra / "infrastructure.env").read_bytes(), credentials)
        # Every Docker command selects the descriptor's explicit context.
        self.assertTrue(all(isinstance(call, list) for call in environment.docker.calls))

    def test_installation_is_fresh_only_and_never_takes_over_unowned_state(self):
        self.infra.mkdir(parents=True)
        (self.infra / "infrastructure.env").write_text("POSTGRES_ADMIN_PASSWORD='unowned'\n")
        (self.infra / "pr-7").mkdir()
        before = snapshot(self.infra)
        environment = self.environment(self.descriptor())
        with self.assertRaisesRegex(DeployError, "not empty and not owned"):
            environment.install()
        self.assertEqual(snapshot(self.infra), before)
        self.assertEqual(environment.docker.commands("up"), [])

    def test_second_environment_cannot_claim_or_change_shared_infrastructure(self):
        self.environment(self.descriptor()).install()
        credentials = (self.infra / "infrastructure.env").read_bytes()
        claimed = self.environment(self.descriptor("staging"), "staging")
        with self.assertRaisesRegex(DeployError, "belongs to another environment"):
            claimed.install()
        self.assertEqual(claimed.docker.commands("up"), [])
        external = self.environment(self.descriptor("staging", infrastructure={"mode": "external"}), "staging")
        self.assertTrue(external.install()["changed"])
        with self.assertRaisesRegex(DeployError, "managed infrastructure owner"):
            external.infra_upgrade()
        self.assertEqual((self.infra / "infrastructure.env").read_bytes(), credentials)
        self.assertEqual(external.docker.commands("up"), [])

    def test_uninstall_stops_only_owned_instances_and_preserves_data(self):
        environment = self.environment(self.descriptor())
        environment.install()
        preview = self.infra / "pr-12"
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
            environment.update(run_id=5)
        self.assertTrue(environment.install()["changed"])

    def test_operations_require_installation_and_identity(self):
        environment = self.environment(self.descriptor())
        for operation in (lambda: environment.stop(1), lambda: environment.cleanup(1), environment.reconcile,
                          lambda: environment.logs(1)):
            with self.subTest(operation=operation), self.assertRaisesRegex(DeployError, "install"):
                operation()
        with self.assertRaisesRegex(DeployError, "--run-id"):
            environment.update()
        status = environment.status()
        self.assertEqual((status["configured"], status["provisioned"]), (True, False))
        self.assertFalse(self.infra.exists())

    def test_release_descriptor_requires_reviewed_access_and_private_role_files(self):
        private = self.root / "private/release"
        private.mkdir(mode=0o700)
        files = {}
        for name, line in (("runtime_file", "PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__USER=runtime\n"
                                            "PEOPLE_GATOR_API__STORAGE__S3__BUCKET_NAME=release\n"),
                           ("migration_file", "PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__USER=migrator\n")):
            files[name] = private / f"{name}.env"
            files[name].write_text(line)
            files[name].chmod(0o600)
        path = self.root / "environments/release/config.json"
        value = {"repository": "DCGM/PeopleGatorApp", "state_dir": str(self.root / "state/release"),
                 "docker_context": "rootless", "host": "people.example.invalid", "web_network": "web",
                 "database_network": "production-db", **{k: str(v) for k, v in files.items()}}
        with self.assertRaisesRegex(DeployError, "access_reviewed"):
            config.configure("release", path, value)
        config.configure("release", path, {**value, "access_reviewed": True})
        environment = self.environment(path, "release")
        with self.assertRaisesRegex(DeployError, "--tag"):
            environment.update()
        self.assertTrue(environment.install()["changed"])
        self.assertIn(["docker", "network", "inspect", "production-db"], environment.docker.calls)
        self.assertEqual(environment.preflight()["provisioned"], True)
        self.assertFalse(environment.install()["changed"])
        files["runtime_file"].chmod(0o644)
        with self.assertRaisesRegex(DeployError, "runtime_file"):
            environment.preflight()


if __name__ == "__main__":
    unittest.main()
