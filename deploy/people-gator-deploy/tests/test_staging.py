"""Staging eligibility, ordered gates, persistence, refresh recovery and isolation."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from people_gator_deploy import staging
from people_gator_deploy.core import DeployError

ASSETS = Path(staging.__file__).with_name("assets")


SHA = "a" * 40
IMAGES = {part: f"ghcr.io/dcgm/peoplegatorapp-{part}@sha256:" + "b" * 64 for part in ("frontend", "backend")}


class FakeStaging(staging.Staging):
    def __init__(self, root):
        runtime = root / "runtime.env"
        runtime.write_text('PEOPLE_GATOR_API__STORAGE=\'{"local":null,"s3":{"endpoint_url":"https://external.invalid","bucket_name":"external","access_key_id":"external-id","secret_access_key":"external-secret"}}\'\n')
        runtime.chmod(0o600)
        archive = root / "snapshot.dump"
        archive.write_bytes(b"PGDMP synthetic original database")
        archive.chmod(0o600)
        super().__init__({"repository": "DCGM/PeopleGatorApp", "state_dir": str(root / "preview"),
                          "runtime_file": str(runtime), "snapshot": {"path": str(archive),
                              "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(), "application_revision": SHA},
                          "staging": {"state_dir": str(root / "staging")}})
        self.root.mkdir()
        (self.root / "infrastructure.env").write_text("synthetic infra")
        self.staging_root.mkdir()
        self.run = {"id": 100, "run_attempt": 1, "workflow_id": 9, "head_sha": SHA,
                    "event": "push", "conclusion": "success", "head_branch": "main",
                    "head_repository": {"full_name": self.repository}}
        self.main_sha = SHA
        self.workflow_path = ".github/workflows/pr-ci.yml"
        self.events = []
        self.inputs = []
        self.fail = None

    def reap_workers(self):
        pass

    def check_access(self):
        pass

    def api(self, endpoint):
        if endpoint == "git/ref/heads/main":
            return {"object": {"sha": self.main_sha}}
        if endpoint.startswith("actions/runs/"):
            return dict(self.run)
        if endpoint.startswith("actions/workflows/pr-ci.yml/runs"):
            return {"workflow_runs": [dict(self.run)]}
        if endpoint.startswith("actions/workflows/"):
            return {"path": self.workflow_path}
        raise AssertionError(endpoint)

    def image(self, part, run):
        self.events.append("pull-" + part)
        return IMAGES[part]

    def command(self, args, *, sql=None):
        self.inputs.append(sql)
        operation = " ".join(args[args.index("-f") + 2:]) if "-f" in args else " ".join(args)
        self.events.append(operation)
        if self.fail and self.fail in operation:
            raise RuntimeError("Injected command failure")
        return ""

    def private_command(self, args, *, input_text=None, input_file=None, progress=None):
        return self.command(args, sql=input_text)

    def worker(self, action, values, directory, **kwargs):
        self.events.append("worker-" + action)
        if self.fail == "worker-" + action:
            raise RuntimeError("Injected worker failure")
        return "{}"

    def prepare(self, generation, values, directory):
        self.events.append("prepare")
        if self.fail == "prepare":
            raise RuntimeError("Injected snapshot failure")
        generation["provenance"] = {"sha256": self.config["snapshot"]["sha256"]}

    def readiness(self, attempts=30):
        self.events.append("https-readiness")
        if self.fail == "readiness":
            self.fail = None  # recovery readiness of the old service succeeds
            raise RuntimeError("Injected readiness failure")

    def initial(self):
        self.deploy(refresh=True)
        self.events.clear()
        return json.loads((self.staging_root / "state.json").read_text())


class StagingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.controller = FakeStaging(self.root)

    def test_successful_current_main_only_and_stale_builds_fail_before_mutation(self):
        controller = self.controller
        for field, value in (("event", "pull_request"), ("head_branch", "issue/16"),
                             ("conclusion", "failure"), ("head_sha", "f" * 40),
                             ("head_repository", {"full_name": "attacker/fork"})):
            old = controller.run[field]
            with self.subTest(field=field):
                controller.run[field] = value
                with self.assertRaisesRegex(ValueError, "current main"):
                    controller.deploy(refresh=True)
                self.assertEqual(controller.events, [])
                controller.run[field] = old
        controller.workflow_path = ".github/workflows/untrusted.yml"
        with self.assertRaises(ValueError):
            controller.deploy(refresh=True)

    def test_explicit_init_then_deploy_retains_database_and_never_reads_snapshot(self):
        controller = self.controller
        with self.assertRaisesRegex(ValueError, "initialization"):
            controller.deploy()
        original = controller.initial()
        controller.run.update(id=101, head_sha="c" * 40)
        controller.main_sha = controller.run["head_sha"]
        controller.deploy()
        state = json.loads((controller.staging_root / "state.json").read_text())
        for field in ("generation", "password", "provenance"):
            self.assertEqual(state[field], original[field])
        self.assertNotIn("prepare", controller.events)
        self.assertFalse(any("seed" in event or "download" in event or "auth" in event for event in controller.events))
        gates = ["run --rm --no-deps migrate", "worker-validate", "config --quiet",
                 "run --rm --no-deps check", "up -d --wait --wait-timeout 180 backend",
                 "up -d --wait --wait-timeout 180 frontend", "https-readiness"]
        indices = [controller.events.index(gate) for gate in gates]
        self.assertEqual(indices, sorted(indices))
        self.assertEqual(json.loads((controller.staging_root / "previous.json").read_text()), original)

    def test_prepare_migration_validation_check_and_readiness_failures_preserve_active_refresh_state(self):
        controller = self.controller
        original = controller.initial()
        old_env = (controller.staging_root / "compose.env").read_bytes()
        for failure in ("prepare", "run --rm --no-deps migrate", "worker-validate", "run --rm --no-deps check", "readiness"):
            controller.events.clear()
            controller.fail = failure
            with self.subTest(failure=failure), self.assertRaises(RuntimeError):
                controller.deploy(refresh=True)
            self.assertEqual(json.loads((controller.staging_root / "state.json").read_text()), original)
            self.assertEqual((controller.staging_root / "compose.env").read_bytes(), old_env)
            self.assertFalse((controller.staging_root / "activation.json").exists())
            if failure != "readiness":
                self.assertFalse(any(event.startswith("up ") for event in controller.events))
        controller.fail = None
        controller.deploy(refresh=True)
        self.assertNotEqual(json.loads((controller.staging_root / "state.json").read_text())["generation"], original["generation"])

    def test_new_main_during_migration_blocks_replacement(self):
        controller = self.controller
        controller.initial()
        original_command = controller.command
        def command(args, **kwargs):
            result = original_command(args, **kwargs)
            if args[-1] == "migrate":
                controller.main_sha = "f" * 40
            return result
        controller.command = command
        with self.assertRaisesRegex(ValueError, "current main"):
            controller.deploy()
        self.assertFalse(any(event.startswith("up ") for event in controller.events))
        self.assertNotIn("run --rm --no-deps check", controller.events)

    def test_local_archive_is_verified_before_provision_and_changes_fail_closed(self):
        controller = self.controller
        original = controller.initial()
        controller.prepare = staging.Staging.prepare.__get__(controller)
        archive = Path(controller.config["snapshot"]["path"])
        for raw, checksum, message in ((b"corrupt", "0" * 64, "not a PostgreSQL"),
                                        (b"PGDMP changed", "0" * 64, "SHA-256")):
            archive.write_bytes(raw)
            controller.config["snapshot"]["sha256"] = checksum
            controller.events.clear()
            with self.subTest(message=message), self.assertRaisesRegex(DeployError, message):
                controller.deploy(refresh=True)
            self.assertEqual(json.loads((controller.staging_root / "state.json").read_text()), original)
            self.assertFalse(any("CREATE" in event or "up " in event for event in controller.events))

    def test_refresh_restores_only_database_without_storage_operations(self):
        controller = self.controller
        controller.prepare = staging.Staging.prepare.__get__(controller)
        controller.provision = lambda values: controller.events.append("provision")
        def private(args, **kwargs):
            stream = kwargs["input_file"]
            self.assertTrue(stream.read().startswith(b"PGDMP"))
            controller.events.append("inspect" if args[-1] == "--list" else "restore")
        controller.private_command = private
        controller.deploy(refresh=True)
        state = json.loads((controller.staging_root / "state.json").read_text())
        self.assertEqual(state["provenance"]["sha256"], controller.config["snapshot"]["sha256"])
        self.assertLess(controller.events.index("inspect"), controller.events.index("provision"))
        self.assertLess(controller.events.index("provision"), controller.events.index("restore"))
        self.assertFalse(any(word in event for event in controller.events for word in ("copy", "auth", "download")))
        self.assertEqual(list(controller.staging_root.glob("snapshot-*")), [])

    def test_snapshot_writes_during_restore_are_rejected(self):
        controller = self.controller
        original = controller.initial()
        controller.prepare = staging.Staging.prepare.__get__(controller)
        controller.provision = lambda values: None
        def private(args, **kwargs):
            if "--single-transaction" in args:
                with Path(controller.config["snapshot"]["path"]).open("ab") as stream:
                    stream.write(b"changed during restore")
        controller.private_command = private
        with self.assertRaisesRegex(DeployError, "changed during"):
            controller.deploy(refresh=True)
        self.assertEqual(json.loads((controller.staging_root / "state.json").read_text()), original)

    def test_new_main_during_full_check_blocks_startup(self):
        controller = self.controller
        controller.initial()
        original_command = controller.command
        def command(args, **kwargs):
            result = original_command(args, **kwargs)
            if args[-1] == "check":
                controller.main_sha = "f" * 40
            return result
        controller.command = command
        with self.assertRaisesRegex(ValueError, "current main"):
            controller.deploy()
        self.assertFalse(any(event.startswith("up ") for event in controller.events))

    def test_older_attempt_cannot_overwrite_newer_and_changed_attempt_is_rejected(self):
        controller = self.controller
        controller.initial()
        controller.run["run_attempt"] = 2
        controller.deploy()
        controller.events.clear()
        controller.run["run_attempt"] = 1
        with self.assertRaisesRegex(ValueError, "newer staging"):
            controller.deploy()
        self.assertNotIn("run --rm --no-deps migrate", controller.events)
        run = dict(controller.run)
        controller.run["run_attempt"] = 3
        with self.assertRaisesRegex(ValueError, "attempt changed"):
            controller.fence(run)

    def test_interrupted_activation_recovers_pair_and_committed_state_recovers_env(self):
        controller = self.controller
        state = controller.initial()
        journal = controller.staging_root / "activation.json"
        journal.write_text(json.dumps({"activation": "uncommitted", "refresh": True}))
        controller.recover_activation()
        self.assertFalse(journal.exists())
        self.assertIn("up -d --wait --wait-timeout 180 backend frontend", controller.events)
        journal.write_text(json.dumps({"activation": state["activation"], "refresh": True}))
        (controller.staging_root / "compose.env").write_text("interrupted env write")
        controller.recover_activation()
        self.assertIn("DB_NAME='staging_" + state["generation"], (controller.staging_root / "compose.env").read_text())
        journal.write_text(json.dumps({"activation": "uncommitted", "refresh": False}))
        controller.events.clear()
        controller.recover_activation()
        self.assertEqual(controller.events, [])
        with self.assertRaisesRegex(DeployError, "retrying update"):
            controller.recover_activation(refresh_requested=True)

    def test_snapshot_is_required_only_for_explicit_database_replacement(self):
        controller = self.controller
        controller.initial()
        del controller.config["snapshot"]
        controller.deploy()
        self.assertNotIn("prepare", controller.events)
        controller.events.clear()
        with self.assertRaisesRegex(DeployError, "needs snapshot for snapshot-init/refresh"):
            controller.deploy(refresh=True)
        self.assertEqual(controller.events, [])

    def test_backend_consumes_external_storage_while_database_tools_do_not(self):
        controller = self.controller
        state = controller.initial()
        values = controller.values(state, IMAGES, SHA)
        self.assertNotIn("MEDIA_PREFIX", values)
        self.assertNotIn("STAGING_STORAGE", values)
        controller.command = staging.Staging.command.__get__(controller)
        rendered = json.loads(controller.command(controller.compose_staging(controller.staging_root / "compose.env", "--profile", "tools", "config", "--format", "json")))
        for service in ("migrate", "check"):
            config = rendered["services"][service]
            self.assertIsNone(json.loads(config["environment"]["PEOPLE_GATOR_API__STORAGE"])["s3"])
            self.assertNotIn("external-secret", json.dumps(config))
            self.assertEqual(set(config["networks"]), {"database"})
        backend = rendered["services"]["backend"]
        self.assertIn("external-secret", backend["environment"]["PEOPLE_GATOR_API__STORAGE"])
        self.assertFalse(any("KEY_PREFIX" in key for key in backend["environment"]))
        self.assertEqual(set(backend["networks"]), {"database", "web"})
        self.assertNotIn("storage-init", rendered["services"])
        self.assertNotIn("seed", rendered["services"])

    def test_database_validator_has_no_external_settings_or_egress(self):
        controller = self.controller
        state = controller.initial()
        values = controller.values(state, IMAGES, SHA)
        controller.worker = staging.Staging.worker.__get__(controller)
        controller.worker("validate", values, controller.staging_root)
        command = controller.events[-1]
        self.assertIn("--network " + values["DATABASE_NETWORK"], command)
        self.assertNotIn("--network web", command)
        self.assertIn("--memory 512m", command)
        self.assertIn("--log-driver none", command)
        environment = (controller.staging_root / "worker.env").read_text()
        self.assertIn('"s3":null', environment)
        self.assertNotIn("external-secret", environment)
        for unsupported in ("copy", "auth", "download"):
            with self.assertRaisesRegex(DeployError, "databases only"):
                controller.worker(unsupported, values, controller.staging_root)

    def test_external_runtime_file_cannot_override_database_ownership(self):
        controller = self.controller
        Path(controller.config["runtime_file"]).write_text("PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__DATABASE=external\n")
        with self.assertRaisesRegex(DeployError, "persistence settings are managed"):
            controller.deploy(refresh=True)
        self.assertEqual(controller.events, [])

    def test_disposable_ci_workers_are_outside_live_staging_recovery_scope(self):
        controller = self.controller
        other_root = self.root / "ci-fixture"
        other_root.mkdir()
        other = FakeStaging(other_root)
        self.assertNotEqual(controller.worker_label, other.worker_label)
        staging.Staging.reap_workers(controller)
        self.assertIn("label=" + controller.worker_label, controller.events[-1])
        self.assertNotIn(other.worker_label, controller.events[-1])

    def test_private_subprocess_failures_never_expose_source_values_to_logs(self):
        controller = self.controller
        controller.private_command = staging.Staging.private_command.__get__(controller)
        with self.assertRaises(DeployError) as raised:
            controller.private_command([sys.executable, "-c", "import sys; print('private-sentinel'); sys.exit(1)"])
        self.assertNotIn("private-sentinel", str(raised.exception))
        self.assertIn("private-sentinel", (controller.staging_root / "last-error.log").read_text())
        self.assertEqual((controller.staging_root / "last-error.log").stat().st_mode & 0o777, 0o600)

    def test_missing_staging_settings_report_safe_guidance_before_github_or_docker(self):
        with self.assertRaises(staging.StagingConfigurationError) as raised:
            staging.Staging({"repository": "DCGM/PeopleGatorApp", "state_dir": str(self.root),
                             "private_operator_value": "private-sentinel"})
        self.assertIn("staging configure", str(raised.exception))
        self.assertNotIn("private-sentinel", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
