"""Staging eligibility, ordered gates, persistence, refresh recovery and isolation."""
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
STORAGE = {"local": None, "s3": {"endpoint_url": "https://staging-s3.example.invalid",
    "region": "test", "bucket_name": "staging-fixture", "access_key_id": "synthetic", "secret_access_key": "synthetic"}}
SOURCE = {"endpoint_url": "https://source.example.invalid", "region": "test", "bucket": "synthetic-source",
          "access_key_id": "synthetic-reader", "secret_access_key": "synthetic-reader-secret"}
ACCOUNTS = {"users": {name: {"hash": "$argon2id$v=19$synthetic"} for name in staging.ACCOUNTS}}
# One private descriptor: staging bucket plus snapshot-only sources and accounts.
DESCRIPTOR = {"storage": STORAGE["s3"], "backup_source": {**SOURCE, "prefix": "production/db-backups/"},
              "media_source": SOURCE, "accounts": ACCOUNTS}


class FakeStaging(staging.Staging):
    def __init__(self, root):
        super().__init__({"repository": "DCGM/PeopleGatorApp", "state_dir": str(root / "preview"),
                          **json.loads(json.dumps(DESCRIPTOR)), "staging": {"state_dir": str(root / "staging")}})
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

    def prepare(self, generation, values, directory, exact_key):
        self.events.append("prepare")
        if self.fail == "prepare":
            raise RuntimeError("Injected snapshot failure")
        generation["provenance"] = {"bucket": "bucket", "key": "backup.dump", "backup_date": "2026-10-15"}

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

    def test_explicit_init_then_deploy_retains_database_media_credentials_and_never_fetches_backup(self):
        controller = self.controller
        with self.assertRaisesRegex(ValueError, "initialization"):
            controller.deploy()
        original = controller.initial()
        controller.run.update(id=101, head_sha="c" * 40)
        controller.main_sha = controller.run["head_sha"]
        controller.deploy()
        state = json.loads((controller.staging_root / "state.json").read_text())
        for field in ("generation", "password", "provenance", "storage"):
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

    def test_refresh_copies_original_data_and_media_without_invoking_sanitizer(self):
        controller = self.controller
        controller.prepare = staging.Staging.prepare.__get__(controller)
        controller.provision = lambda values: controller.events.append("provision")
        controller.private_command = lambda *args, **kwargs: controller.events.append("private-restore")
        def worker(action, values, directory, *, work=None, **kwargs):
            controller.events.append("worker-" + action)
            if action == "download":
                (work / "snapshot.dump").write_bytes(b"PGDMP synthetic original data")
                (work / "provenance.json").write_text(json.dumps({"bucket": "backup", "key": "archive", "backup_date": "2026-10-16"}))
            return json.dumps({"data_mode": "original", "media_objects": 3})
        controller.worker = worker
        controller.deploy(refresh=True)
        state = json.loads((controller.staging_root / "state.json").read_text())
        self.assertEqual(state["provenance"]["data_mode"], "original")
        self.assertLess(controller.events.index("worker-copy"), controller.events.index("worker-auth"))
        self.assertNotIn("worker-sanitize", controller.events)
        self.assertEqual(list(controller.staging_root.glob("snapshot-*")), [])

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

    def test_runtime_has_no_transfer_credentials_or_source_mount_and_worker_is_private(self):
        controller = self.controller
        state = {"generation": "0" * 16, "password": "1" * 64, "storage": controller.storage_identity(STORAGE)}
        values = controller.values(state, IMAGES, SHA)
        self.assertFalse(any("SOURCE" in key or "AWS" in key for key in values))
        compose = (ASSETS / "compose.staging.yaml").read_text()
        self.assertIn("PEOPLE_GATOR_API__STORAGE: ${STAGING_STORAGE:?", compose)
        self.assertNotIn("/data", compose)
        self.assertNotIn("storage-init", compose)
        self.assertIn("SCHEMA_MODE: validate", compose)
        self.assertIn("command: [check]", compose)
        self.assertNotIn("command: [seed]", compose)
        self.assertNotIn("PR_NUMBER", compose)
        controller.worker = staging.Staging.worker.__get__(controller)
        controller.worker("download", values, controller.staging_root)
        call = controller.events[-1]
        self.assertIn("--log-driver none", call)
        self.assertNotIn("synthetic-reader-secret", call)
        self.assertEqual(set(json.loads(controller.inputs[-1])), {"backup-source.json"})
        self.assertEqual(json.loads(controller.inputs[-1])["backup-source.json"]["bucket"], "synthetic-source")
        self.assertNotIn("--network people-gator-preview-db", call)

    def test_s3_configuration_is_required_and_bucket_identity_cannot_change(self):
        controller = self.controller
        original = controller.initial()
        for invalid in (None, {}, {**STORAGE["s3"], "endpoint_url": ""},
                        {**STORAGE["s3"], "endpoint_url": "http://storage.example.invalid"},
                        {**STORAGE["s3"], "timeout_seconds": 0}, {**STORAGE["s3"], "root": "/data"},
                        {**STORAGE["s3"], "bucket_name": "different-bucket"}):
            with self.subTest(config=invalid):
                controller.config["storage"] = invalid
                controller.events.clear()
                with self.assertRaises(ValueError):
                    controller.deploy()
                self.assertEqual(controller.events, [])
                self.assertEqual(json.loads((controller.staging_root / "state.json").read_text()), original)
        controller.config["storage"] = dict(STORAGE["s3"], secret_access_key="rotated")
        controller.deploy()  # credentials rotate within the same bucket
        del controller.config["storage"]
        controller.events.clear()
        with self.assertRaisesRegex(staging.StagingConfigurationError, "needs storage"):
            controller.deploy()
        self.assertEqual(controller.events, [])

    def test_snapshot_sections_are_needed_only_by_snapshot_operations(self):
        controller = self.controller
        original = controller.initial()
        for name in ("backup_source", "media_source", "accounts"):
            del controller.config[name]
        controller.deploy()  # retained-data update needs no source credentials
        self.assertNotIn("prepare", controller.events)
        controller.events.clear()
        with self.assertRaisesRegex(staging.StagingConfigurationError, "needs backup_source for snapshot-init/refresh"):
            controller.deploy(refresh=True)
        self.assertEqual(controller.events, [])
        controller.config.update(json.loads(json.dumps(DESCRIPTOR)))
        controller.config["accounts"]["users"].pop("staging-admin")
        with self.assertRaisesRegex(DeployError, "accounts.users must define exactly"):
            controller.deploy(refresh=True)
        self.assertEqual(controller.events, [])
        self.assertEqual(json.loads((controller.staging_root / "state.json").read_text())["generation"],
                         original["generation"])

    def test_snapshot_source_cannot_be_the_staging_destination(self):
        controller = self.controller
        state = controller.initial()
        values = controller.values(state, IMAGES, SHA)
        controller.config["backup_source"] = {**SOURCE, "bucket": STORAGE["s3"]["bucket_name"],
                                              "endpoint_url": STORAGE["s3"]["endpoint_url"]}
        controller.worker = staging.Staging.worker.__get__(controller)
        controller.events.clear()
        with self.assertRaisesRegex(ValueError, "separate"):
            controller.worker("download", values, controller.staging_root)
        self.assertEqual(controller.events, [])

    def test_compose_and_preparation_use_same_s3_bucket_and_generation_prefixes(self):
        controller = self.controller
        state = controller.initial()
        values = controller.values(state, IMAGES, SHA)
        environment = controller.runtime_environment(values)
        self.assertEqual(json.loads(environment["PEOPLE_GATOR_API__STORAGE"]), STORAGE)
        self.assertTrue(environment["PEOPLE_GATOR_API__PAGE_IMAGE__KEY_PREFIX"].startswith("generations/" + state["generation"]))
        controller.command = staging.Staging.command.__get__(controller)
        rendered = json.loads(controller.command(controller.compose_staging(controller.staging_root / "compose.env", "--profile", "tools", "config", "--format", "json")))
        for service in ("backend", "migrate", "check"):
            config = rendered["services"][service]
            for key, value in environment.items():
                if key != "PEOPLE_GATOR_API__PERSISTENCE" and key != "PEOPLE_GATOR_API__OTEL__ENABLED":
                    self.assertEqual(config["environment"][key], value, key)
            self.assertNotIn("volumes", config)
            self.assertEqual(set(config["networks"]), {"database", "web"})
        self.assertNotIn("volumes", rendered)
        self.assertNotIn("storage-init", rendered["services"])

    def test_copy_worker_is_bounded_private_and_reachable_without_source_mounts(self):
        controller = self.controller
        state = controller.initial()
        values = controller.values(state, IMAGES, SHA)
        source = SOURCE
        controller.transfer = {"concurrency": 4, "max_object_mib": 64}
        controller.worker = staging.Staging.worker.__get__(controller)
        controller.worker("copy", values, controller.staging_root)
        command = controller.events[-1]
        self.assertIn("--network web", command)
        self.assertIn("--network " + values["DATABASE_NETWORK"], command)
        self.assertIn("--memory 768m", command)
        self.assertNotIn("type=volume", command)
        self.assertNotIn("--cap-add", command)
        self.assertNotIn("synthetic-reader-secret", command)
        self.assertIn("--user 10001:10001", command)
        self.assertEqual(json.loads(controller.inputs[-1]), {"media-source.json": source,
                                                             "transfer": {"concurrency": 4, "max_object_mib": 64}})
        with self.assertRaisesRegex(DeployError, "media_transfer"):
            staging.Staging({**controller.config, "media_transfer": {"concurrency": 0}})

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
