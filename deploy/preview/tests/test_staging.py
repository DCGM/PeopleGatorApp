"""Staging eligibility, ordered gates, persistence, refresh recovery and isolation."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

DIRECTORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DIRECTORY))
import staging


SHA = "a" * 40
IMAGES = {part: f"ghcr.io/dcgm/peoplegatorapp-{part}@sha256:" + "b" * 64 for part in ("frontend", "backend")}


class FakeStaging(staging.Staging):
    def __init__(self, root):
        super().__init__({"repository": "DCGM/PeopleGatorApp", "state_dir": str(root / "preview"),
                          "users_file": str(root / "preview-users.json"), "staging": {
                              "state_dir": str(root / "staging"), "private_dir": str(root / "private")}})
        self.root.mkdir()
        (self.root / "infrastructure.env").write_text("synthetic infra")
        self.staging_root.mkdir()
        self.run = {"id": 100, "run_attempt": 1, "workflow_id": 9, "head_sha": SHA,
                    "event": "push", "conclusion": "success", "head_branch": "main",
                    "head_repository": {"full_name": self.repository}}
        self.main_sha = SHA
        self.workflow_path = ".github/workflows/pr-ci.yml"
        self.events = []
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
        operation = " ".join(args[args.index("-f") + 2:]) if "-f" in args else " ".join(args)
        self.events.append(operation)
        if self.fail and self.fail in operation:
            raise RuntimeError("Injected command failure")
        return ""

    def worker(self, action, values, directory, **kwargs):
        self.events.append("worker-" + action)
        if self.fail == "worker-" + action:
            raise RuntimeError("Injected worker failure")
        return "{}"

    def prepare(self, generation, values, directory, candidate, exact_key):
        self.events.append("prepare")
        if self.fail == "prepare":
            raise RuntimeError("Injected snapshot failure")
        generation["provenance"] = {"bucket": "bucket", "key": "backup.dump", "backup_date": "2026-10-15"}

    def readiness(self):
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

    def test_explicit_init_then_deploy_retains_database_media_credentials_and_never_fetches_backup(self):
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

    def test_corrupt_newest_archive_fails_before_provision_without_fallback(self):
        controller = self.controller
        original = controller.initial()
        controller.prepare = staging.Staging.prepare.__get__(controller)
        def worker(action, values, directory, *, work=None, **kwargs):
            self.assertEqual(action, "download")
            (work / "snapshot.dump").write_bytes(b"corrupt latest archive")
        controller.worker = worker
        with self.assertRaisesRegex(ValueError, "not a PostgreSQL"):
            controller.deploy(refresh=True)
        self.assertEqual(json.loads((controller.staging_root / "state.json").read_text()), original)
        self.assertEqual(list(controller.staging_root.glob("snapshot-*")), [])
        self.assertFalse(any("CREATE" in event or "up " in event for event in controller.events))

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
        with self.assertRaisesRegex(ValueError, "retrying deploy"):
            controller.recover_activation(refresh_requested=True)

    def test_runtime_has_no_transfer_credentials_or_source_mount_and_worker_is_private(self):
        controller = self.controller
        state = {"generation": "0" * 16, "password": "1" * 64}
        values = controller.values(state, IMAGES, SHA)
        self.assertFalse(any("SOURCE" in key or "AWS" in key for key in values))
        compose = (DIRECTORY / "compose.staging.yaml").read_text()
        self.assertIn("auth:/data/peoplegator_api:ro", compose)
        self.assertIn("SCHEMA_MODE: validate", compose)
        self.assertIn("command: [check]", compose)
        self.assertNotIn("command: [seed]", compose)
        self.assertNotIn("PR_NUMBER", compose)
        private = self.root / "private"
        private.mkdir()
        (private / "backup-source.json").write_text("private")
        controller.worker = staging.Staging.worker.__get__(controller)
        controller.worker("download", values, controller.staging_root)
        call = controller.events[-1]
        self.assertIn("--log-driver none", call)
        self.assertIn("/private/backup-source.json,readonly", call)
        self.assertNotIn("--network people-gator-preview-db", call)

    def test_shared_host_lock_and_reviewed_main_workflow_guards(self):
        source = (DIRECTORY / "staging.py").read_text()
        self.assertIn('(controller.root / "controller.lock")', source)
        workflow = (DIRECTORY.parents[1] / ".github/workflows/staging.yml").read_text()
        self.assertIn("runs-on: [self-hosted, linux, x64, people-gator-staging]", workflow)
        self.assertIn("group: people-gator-preview-host", workflow)
        self.assertIn("staging.yml@refs/heads/main", workflow)
        self.assertIn("ref: ${{ github.workflow_sha }}", workflow)
        self.assertIn("if: always() && steps.registry-config.outputs.path != ''", workflow)
        ci = (DIRECTORY.parents[1] / ".github/workflows/pr-ci.yml").read_text()
        self.assertIn("push:\n    branches: [main]", ci)
        self.assertIn("github.event.pull_request.head.sha || github.sha", ci)

    def test_private_subprocess_failures_never_expose_source_values_to_logs(self):
        controller = self.controller
        controller.private_command = staging.Staging.private_command.__get__(controller)
        with self.assertRaises(RuntimeError):
            controller.private_command([sys.executable, "-c", "import sys; print('private-sentinel'); sys.exit(1)"])
        self.assertIn("private-sentinel", (controller.staging_root / "last-error.log").read_text())
        self.assertEqual((controller.staging_root / "last-error.log").stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
