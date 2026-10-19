"""Release tag provenance, idempotent/stale delivery, migration gates, activation and recovery."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from people_gator_deploy import release
from people_gator_deploy.core import DeployError

FIRST, SECOND, OLD = "1" * 40, "2" * 40, "0" * 40
IMAGES = {part: f"ghcr.io/dcgm/peoplegatorapp-{part}@sha256:" + "b" * 64 for part in ("frontend", "backend")}


class FakeRelease(release.Release):
    """GitHub, images and Docker are scripted; files and ordering are real."""

    def __init__(self, root: Path):
        private = root / "private"
        private.mkdir(mode=0o700)
        for name, keys in (("runtime.env", ["PERSISTENCE__POSTGRES__USER=runtime", "STORAGE__S3__BUCKET_NAME=release"]),
                           ("migration.env", ["PERSISTENCE__POSTGRES__USER=migrator"])):
            path = private / name
            path.write_text("".join(f"PEOPLE_GATOR_API__{key}\n" for key in keys))
            path.chmod(0o600)
        super().__init__({"repository": "DCGM/PeopleGatorApp", "state_dir": str(root / "state"),
                          "docker_context": "rootless", "host": "people.example.invalid", "web_network": "web",
                          "database_network": "production-db", "runtime_file": str(private / "runtime.env"),
                          "migration_file": str(private / "migration.env")})
        self.install()
        self.tags = {"v1.0.0": {"type": "commit", "sha": FIRST},
                     "v1.1.0": {"type": "tag", "sha": "a" * 40},
                     "v0.9.0": {"type": "commit", "sha": OLD}}
        self.annotated = {"a" * 40: {"type": "commit", "sha": SECOND}}
        self.on_main = {FIRST, SECOND, OLD}
        self.history = {(FIRST, SECOND), (OLD, FIRST), (OLD, SECOND)}  # (ancestor, descendant)
        self.runs = {FIRST: 200, SECOND: 300, OLD: 100}
        self.schema = {"current": True}
        self.events = []
        self.fail = None

    def check_access(self):
        pass

    def api(self, endpoint):
        if endpoint.startswith("git/ref/tags/"):
            return {"object": self.tags[endpoint.rsplit("/", 1)[1]]}
        if endpoint.startswith("git/tags/"):
            return {"object": self.annotated[endpoint.rsplit("/", 1)[1]]}
        if endpoint.startswith("compare/"):
            base, head = endpoint[len("compare/"):].split("...")
            if head == "main":
                return {"status": "ahead" if base in self.on_main else "diverged"}
            return {"status": "identical" if base == head else "ahead" if (base, head) in self.history else "behind"}
        if endpoint.startswith("actions/workflows/pr-ci.yml/runs?head_sha="):
            sha = endpoint.split("head_sha=")[1].split("&")[0]
            return {"workflow_runs": [{"id": self.runs[sha]}] if sha in self.runs else []}
        if endpoint.startswith("actions/runs/"):
            run_id = int(endpoint.rsplit("/", 1)[1])
            sha = next(sha for sha, value in self.runs.items() if value == run_id)
            return {"id": run_id, "run_attempt": 1, "workflow_id": 9, "conclusion": "success", "event": "push",
                    "head_branch": "main", "head_sha": sha, "head_repository": {"full_name": self.repository}}
        if endpoint.startswith("actions/workflows/"):
            return {"path": ".github/workflows/pr-ci.yml"}
        raise AssertionError(endpoint)

    def image(self, component, run):
        self.events.append(f"pull-{component}-{run['head_sha'][:1]}")
        return IMAGES[component]

    def command(self, args, *, sql=None):
        operation = " ".join(args[args.index("-f") + 2:])
        self.events.append(operation)
        if operation.endswith("check") and not self.schema["current"]:
            raise DeployError("schema check failed")
        if operation.endswith("migrate"):
            self.schema["current"] = True
        if self.fail and self.fail in operation:
            raise DeployError("Injected failure")
        return ""

    def readiness(self, attempts=30):
        self.events.append("routed-readiness")
        if self.fail == "readiness":
            raise DeployError("Injected readiness failure")


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.release = FakeRelease(self.root)
        self.record = self.root / "private/backup-record"
        self.record.write_text("pg_dump verified before v1.1.0")
        self.record.chmod(0o600)

    def state(self):
        return json.loads((self.release.root / "state.json").read_text())

    def test_tags_resolve_annotated_and_lightweight_commits_and_reject_moved_or_unreviewed_tags(self):
        self.assertEqual(self.release.tag_commit("v1.0.0"), FIRST)
        self.assertEqual(self.release.tag_commit("v1.1.0"), SECOND)
        for tag in ("main", "v1.0.0;rm", "../v1", "release-1"):
            with self.subTest(tag=tag), self.assertRaisesRegex(DeployError, "pattern"):
                self.release.tag_commit(tag)
        with self.assertRaisesRegex(DeployError, "moved"):
            self.release.eligible("v1.0.0", commit=SECOND)
        self.release.on_main.discard(FIRST)
        with self.assertRaisesRegex(DeployError, "not on main"):
            self.release.eligible("v1.0.0")
        self.release.on_main.add(FIRST)
        del self.release.runs[FIRST]
        with self.assertRaisesRegex(DeployError, "No successful main-push"):
            self.release.eligible("v1.0.0")
        self.release.runs[FIRST] = 200
        with self.assertRaisesRegex(DeployError, "not tagged commit"):
            self.release.eligible("v1.0.0", run_id=300)
        self.assertEqual(self.release.events, [])

    def test_first_release_gates_order_and_repeated_delivery_is_idempotent(self):
        result = self.release.deploy("v1.0.0", commit=FIRST)
        self.assertTrue(result["changed"])
        gates = ["config --quiet", "run --rm --no-deps check",
                 "up -d --wait --wait-timeout 300 backend", "up -d --wait --wait-timeout 180 frontend", "routed-readiness"]
        indices = [self.release.events.index(gate) for gate in gates]
        self.assertEqual(indices, sorted(indices))
        self.assertNotIn("run --rm --no-deps migrate", self.release.events)
        self.assertFalse(any("seed" in event for event in self.release.events))
        state = self.state()
        self.assertEqual((state["tag"], state["commit"], state["images"]), ("v1.0.0", FIRST, IMAGES))
        environment = (self.release.root / "compose.env").read_text()
        self.assertIn(f"COMMIT_SHA='{FIRST}'", environment)
        self.assertNotIn("migrator", environment)  # private files are referenced, never copied
        self.release.events.clear()
        self.assertFalse(self.release.deploy("v1.0.0")["changed"])
        self.assertEqual(self.release.events, [])
        self.release.tags["v1.0.0"] = {"type": "commit", "sha": SECOND}
        with self.assertRaisesRegex(DeployError, "moved tags are rejected"):
            self.release.deploy("v1.0.0")

    def test_migration_requires_backup_record_and_older_retries_cannot_replace_newer(self):
        self.release.deploy("v1.0.0")
        before = self.state()
        self.release.schema["current"] = False  # v1.1.0 needs a migration
        self.release.events.clear()
        with self.assertRaisesRegex(DeployError, "backup-record"):
            self.release.deploy("v1.1.0")
        self.assertNotIn("run --rm --no-deps migrate", self.release.events)
        self.assertFalse(any(event.startswith("up ") for event in self.release.events))
        self.assertEqual(self.state(), before)
        self.release.events.clear()
        self.release.deploy("v1.1.0", backup_record=self.record)
        order = [self.release.events.index(event) for event in
                 ("run --rm --no-deps migrate", "up -d --wait --wait-timeout 300 backend")]
        self.assertEqual(order, sorted(order))
        self.assertEqual(self.state()["tag"], "v1.1.0")
        self.assertEqual(json.loads((self.release.root / "previous.json").read_text())["tag"], "v1.0.0")
        self.release.events.clear()
        for stale in ("v1.0.0", "v0.9.0"):
            with self.subTest(tag=stale), self.assertRaisesRegex(DeployError, "older or diverged"):
                self.release.deploy(stale)
        self.assertEqual(self.release.events, [])
        self.assertEqual(len((self.release.root / "history.jsonl").read_text().splitlines()), 2)

    def test_failed_activation_keeps_state_and_only_the_same_tag_can_retry(self):
        self.release.deploy("v1.0.0")
        before, environment = self.state(), (self.release.root / "compose.env").read_bytes()
        self.release.fail = "readiness"
        with self.assertRaisesRegex(DeployError, "readiness"):
            self.release.deploy("v1.1.0")
        self.assertEqual(self.state(), before)
        self.assertEqual((self.release.root / "compose.env").read_bytes(), environment)
        self.assertTrue((self.release.root / "activation.json").exists())
        self.release.tags["v1.2.0"] = {"type": "commit", "sha": SECOND}
        with self.assertRaisesRegex(DeployError, "interrupted activation"):
            self.release.deploy("v1.2.0")
        self.release.fail = None
        self.release.deploy("v1.1.0")
        self.assertEqual(self.state()["tag"], "v1.1.0")
        self.assertFalse((self.release.root / "activation.json").exists())

    def test_recovery_reuses_previous_images_only_when_the_schema_check_accepts_them(self):
        self.assertRaisesRegex(DeployError, "No retained", self.release.recover)
        self.release.deploy("v1.0.0")
        self.release.deploy("v1.1.0")
        self.release.schema["current"] = False  # previous image rejects the migrated schema
        self.release.events.clear()
        with self.assertRaisesRegex(DeployError, "rejects the current database schema"):
            self.release.recover()
        self.assertFalse(any(event.startswith("up ") for event in self.release.events))
        self.assertEqual(self.state()["tag"], "v1.1.0")
        self.release.schema["current"] = True
        self.assertTrue(self.release.recover()["recovered"])
        state = self.state()
        self.assertEqual((state["tag"], state["recovered"]), ("v1.0.0", True))
        # After explicit recovery, the newer release can be delivered again.
        self.release.deploy("v1.1.0")
        self.assertEqual(self.state()["tag"], "v1.1.0")

    def test_private_inputs_keep_roles_separate_and_cannot_override_production_settings(self):
        runtime = Path(self.release.config["runtime_file"])
        original = runtime.read_text()
        for content, mode, message in (
                (original, 0o644, "mode-600"),
                (original + "PEOPLE_GATOR_API__DEBUG=true\n", 0o600, "DEBUG"),
                (original + "PEOPLE_GATOR_API__RELOAD=true\n", 0o600, "RELOAD"),
                ("PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__USER=runtime\n", 0o600, "STORAGE"),
                ("export AWS_SECRET_ACCESS_KEY=ambient\n", 0o600, "only PEOPLE_GATOR_API")):
            runtime.write_text(content)
            runtime.chmod(mode)
            with self.subTest(message=message), self.assertRaisesRegex(DeployError, message):
                self.release.validate_inputs()
        runtime.write_text(original)
        runtime.chmod(0o600)
        self.release.config["migration_file"] = str(runtime)
        with self.assertRaisesRegex(DeployError, "separate"):
            self.release.validate_inputs()

    @unittest.skipUnless(shutil.which("docker"), "Docker Compose not installed")
    def test_production_stack_has_no_development_mounts_and_separates_roles(self):
        env = self.release.root / "render.env"
        env.write_text(self.release.dotenv(self.release.values("v1.0.0", FIRST, IMAGES)))
        with patch.dict(os.environ, {"PEOPLE_GATOR_API__DEBUG": "true", "RELEASE_HOST": "ambient.invalid"}):
            rendered = json.loads(subprocess.run(
                [part for part in release.Release.compose_release(self.release, env, "--profile", "tools", "config",
                                                                   "--format", "json")],
                capture_output=True, text=True, check=True, env={k: v for k, v in os.environ.items()
                                                               if k != "RELEASE_HOST"}).stdout)
        for name in ("backend", "migrate", "check"):
            service = rendered["services"][name]
            self.assertEqual(service["environment"]["PEOPLE_GATOR_API__DEBUG"], "false")
            self.assertEqual(service["environment"]["PEOPLE_GATOR_API__RELOAD"], "false")
            self.assertEqual(service["environment"]["PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__SCHEMA_MODE"], "validate")
            self.assertNotIn("volumes", service)
            self.assertTrue(service["read_only"])
            self.assertEqual(service["user"], "10001:10001")
        self.assertEqual(rendered["services"]["migrate"]["environment"]["PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__USER"], "migrator")
        for name in ("backend", "check"):
            self.assertEqual(rendered["services"][name]["environment"]["PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__USER"], "runtime")
            self.assertNotIn("migrator", json.dumps(rendered["services"][name]))
        self.assertEqual(rendered["services"]["backend"]["command"], ["api"])
        self.assertNotIn("seed", rendered["services"])
        self.assertNotIn("storage-init", rendered["services"])
        self.assertFalse(rendered["services"]["backend"].get("ports"))
        labels = rendered["services"]["frontend"]["labels"]
        self.assertIn("people.example.invalid", labels["traefik.http.routers.pg-release-app.rule"])
        self.assertTrue(rendered["networks"]["database"]["external"])


if __name__ == "__main__":
    unittest.main()
