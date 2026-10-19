"""Legacy controller bundle publication, retained until operators retire old bundles."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "release.py"
SPEC = importlib.util.spec_from_file_location("preview_release", MODULE_PATH)
installation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installation)


@unittest.skipUnless(shutil.which("docker"), "Docker Compose not installed")
class ReleaseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source"
        self.bundle = self.source / "deploy/preview"
        self.bundle.mkdir(parents=True)
        for name in installation.BUNDLE_FILES:
            shutil.copyfile(MODULE_PATH.parent / name, self.bundle / name)
        shutil.copyfile(MODULE_PATH, self.bundle / "release.py")
        # Operator files and untracked/dirty files must never enter releases.
        (self.bundle / "config.json").write_text('private operator config')
        (self.bundle / "users.json").write_text('private users')
        self.releases = self.root / "releases"
        self.releases.mkdir(mode=0o700)
        self.private = self.root / "operator"
        self.private.mkdir()
        (self.private / "config.json").write_text('retained repository/network settings')
        (self.private / "state.json").write_text('{"password":"retained-password"}')
        (self.private / "media").write_bytes(b"retained media")
        self.before = {p.name: p.read_bytes() for p in self.private.iterdir()}
        self.git("init", "-b", "main")
        self.git("config", "user.email", "synthetic@example.test")
        self.git("config", "user.name", "Synthetic Release Test")
        self.git("config", "core.hooksPath", "/dev/null")
        self.revision = self.commit()
        environment = patch.dict(os.environ, {"GITHUB_ACTIONS": "false"})
        environment.start()
        self.addCleanup(environment.stop)

    def tearDown(self):
        self.assertEqual({p.name: p.read_bytes() for p in self.private.iterdir()}, self.before)

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.source), *args], check=True,
                              capture_output=True, text=True, timeout=10).stdout.strip()

    def commit(self):
        self.git("add", ".")
        self.git("commit", "-m", "Synthetic reviewed release")
        revision = self.git("rev-parse", "HEAD")
        self.git("update-ref", "refs/remotes/origin/main", revision)
        return revision

    def publish(self, revision=None):
        return installation.publish(self.source, self.releases, revision or self.revision)

    def test_publishes_complete_bundle_and_reuses_it_without_copying_settings(self):
        release = self.publish()
        self.assertEqual(release, self.releases / self.revision)
        self.assertEqual({p.name for p in release.iterdir()}, {*installation.BUNDLE_FILES, "release.json"})
        original = {p.name: (p.stat().st_mtime_ns, p.read_bytes()) for p in release.iterdir()}
        # A dirty working copy does not affect committed release contents.
        (self.bundle / "preview.py").write_text("this is not Python")
        self.assertEqual(self.publish(), release)
        self.assertEqual({p.name: (p.stat().st_mtime_ns, p.read_bytes()) for p in release.iterdir()}, original)
        self.assertEqual(list(self.releases.glob(".staging-*")), [])

    def test_publication_cli_exports_the_selected_release_path(self):
        output = self.root / "github-output"
        result = subprocess.run([
            "python3", str(self.bundle / "release.py"), "--revision", self.revision,
            "--releases", str(self.releases),
        ], env={**os.environ, "GITHUB_OUTPUT": str(output)}, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output.read_text(), f"path={self.releases / self.revision}\n")
        self.assertNotIn("retained-password", result.stdout + result.stderr)

    def test_new_revision_and_old_rerun_do_not_replace_any_release(self):
        old = self.publish()
        old_bytes = (old / "preview.py").read_bytes()
        (self.bundle / "preview.py").write_bytes(old_bytes + b"\n# Next reviewed release\n")
        newer_revision = self.commit()
        new = self.publish(newer_revision)
        self.assertEqual(self.publish(self.revision), old)
        self.assertEqual((old / "preview.py").read_bytes(), old_bytes)
        self.assertNotEqual((new / "preview.py").read_bytes(), old_bytes)
        self.assertFalse((self.releases / "current").exists())
        # A retained release is usable for an explicit compatible recovery.
        result = subprocess.run(["python3", str(old / "preview.py"), "--help"],
                                check=True, capture_output=True, text=True, timeout=10)
        self.assertIn("check-access", result.stdout)

    def test_publication_failure_preserves_previous_release_and_retry_recovers(self):
        old = self.publish()
        original = (old / "release.json").read_bytes()
        (self.bundle / "preview.py").write_text((self.bundle / "preview.py").read_text() + "\n# upgrade\n")
        revision = self.commit()
        with patch.object(Path, "rename", side_effect=OSError("interrupted publication")):
            with self.assertRaisesRegex(OSError, "interrupted publication"):
                self.publish(revision)
        self.assertEqual((old / "release.json").read_bytes(), original)
        self.assertFalse((self.releases / revision).exists())
        self.assertEqual(list(self.releases.glob(".staging-*")), [])
        # Simulate a process killed before it could remove its staging directory.
        interrupted = self.releases / ".staging-interrupted"
        interrupted.mkdir()
        (interrupted / "preview.py").write_text("incomplete")
        self.assertTrue(self.publish(revision).is_dir())
        self.assertEqual((old / "release.json").read_bytes(), original)

    def test_invalid_code_and_compose_fail_before_publication(self):
        old = self.publish()
        for name, invalid in (("preview.py", "def invalid("), ("compose.pr.yaml", "services: [")):
            original = (self.bundle / name).read_bytes()
            (self.bundle / name).write_text(invalid)
            revision = self.commit()
            with self.subTest(name=name), self.assertRaises((ValueError, SyntaxError)):
                self.publish(revision)
            self.assertFalse((self.releases / revision).exists())
            self.assertTrue(old.is_dir())
            self.assertEqual(list(self.releases.glob(".staging-*")), [])
            (self.bundle / name).write_bytes(original)

    def test_missing_companion_is_rejected_without_publishing_partial_bundle(self):
        (self.bundle / "otel-collector.yaml").unlink()
        revision = self.commit()
        with self.assertRaisesRegex(ValueError, "Cannot read reviewed"):
            self.publish(revision)
        self.assertEqual(list(self.releases.iterdir()), [])

    def test_bundle_without_seed_service_cannot_be_published(self):
        compose = self.bundle / "compose.pr.yaml"
        compose.write_text(compose.read_text().replace("  seed:\n", "  obsolete-service:\n"))
        revision = self.commit()
        with self.assertRaisesRegex(ValueError, "missing required lifecycle services"):
            self.publish(revision)
        self.assertFalse((self.releases / revision).exists())
        self.assertEqual(list(self.releases.glob(".staging-*")), [])

    def test_staging_bundle_cannot_publish_local_storage_or_split_buckets(self):
        compose = self.bundle / "compose.staging.yaml"
        original = compose.read_text()
        variants = [
            original.replace("${STAGING_STORAGE:?explicit S3 storage required}",
                             "'{\"local\":{\"root\":\"/data\"},\"s3\":null}'"),
            original.replace("\n  networks: [database, web]\n", "\n  volumes: [legacy:/data]\n  networks: [database, web]\n")
                + "\nvolumes:\n  legacy: {}\n",
            original.replace("  check:\n    <<: *backend\n", "  check:\n    <<: *backend\n"
                "    environment:\n      PEOPLE_GATOR_API__STORAGE: '{\"local\":null,\"s3\":{\"bucket_name\":\"different-bucket\"}}'\n"),
            original.replace("    PEOPLE_GATOR_API__STORAGE: ${STAGING_STORAGE:?explicit S3 storage required}\n",
                "    PEOPLE_GATOR_API__STORAGE: ${STAGING_STORAGE:?explicit S3 storage required}\n"
                "    PEOPLE_GATOR_API__STORAGE__S3__BUCKET_NAME: hidden-override\n"),
        ]
        for index, value in enumerate(variants):
            with self.subTest(index=index):
                compose.write_text(value)
                revision = self.commit()
                with self.assertRaisesRegex(ValueError, "Staging release requires"):
                    self.publish(revision)
                self.assertFalse((self.releases / revision).exists())
                self.assertEqual(list(self.releases.glob(".staging-*")), [])
        compose.write_text(original)

    def test_corrupted_or_symlinked_cached_release_is_not_overwritten(self):
        release = self.publish()
        controller = release / "preview.py"
        controller.write_text("corrupted")
        with self.assertRaisesRegex(ValueError, "corrupted"):
            self.publish()
        self.assertEqual(controller.read_text(), "corrupted")
        controller.unlink()
        controller.symlink_to(self.bundle / "preview.py")
        with self.assertRaisesRegex(ValueError, "invalid file"):
            self.publish()

    def test_root_must_be_preprovisioned_private_and_owned_by_runner(self):
        for mode in (0o755, 0o777):
            self.releases.chmod(mode)
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, "mode 700"):
                self.publish()
        self.releases.chmod(0o700)
        with self.assertRaisesRegex(ValueError, "Provision"):
            installation.publish(self.source, self.root / "missing", self.revision)
        self.assertFalse((self.root / "missing").exists())
        linked = self.root / "symlink"
        linked.symlink_to(self.releases, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "Provision"):
            installation.publish(self.source, linked, self.revision)

    def test_manual_publication_rejects_pr_branch_and_unreviewed_commit(self):
        self.git("switch", "-c", "issue/7-unreviewed")
        with self.assertRaisesRegex(ValueError, "reviewed main"):
            self.publish()
        self.git("switch", "main")
        (self.bundle / "preview.py").write_text("# unreviewed commit\n")
        self.git("add", ".")
        self.git("commit", "-m", "Unreviewed")
        with self.assertRaisesRegex(ValueError, "fetch main"):
            self.publish(self.git("rev-parse", "HEAD"))
        self.assertEqual(list(self.releases.iterdir()), [])

    def test_workflow_source_checks_cover_every_lifecycle_event(self):
        base = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": "DCGM/PeopleGatorApp",
                "GITHUB_WORKFLOW_REF": "DCGM/PeopleGatorApp/.github/workflows/pr-preview.yml@refs/heads/main",
                "GITHUB_WORKFLOW_SHA": self.revision, "GITHUB_REF": "refs/heads/main"}
        for event in ("workflow_run", "pull_request_target", "schedule", "workflow_dispatch"):
            with self.subTest(event=event), patch.dict(os.environ, {**base, "GITHUB_EVENT_NAME": event}):
                self.assertTrue(self.publish().is_dir())
        for changes in (
            {"GITHUB_EVENT_NAME": "pull_request"},
            {"GITHUB_REF": "refs/heads/issue/7"},
            {"GITHUB_WORKFLOW_REF": base["GITHUB_WORKFLOW_REF"].replace("heads/main", "heads/issue/7")},
            {"GITHUB_WORKFLOW_SHA": "f" * 40},
            {"GITHUB_REPOSITORY": "attacker/fork"},
        ):
            with self.subTest(changes=changes), patch.dict(os.environ, {
                **base, "GITHUB_EVENT_NAME": "workflow_dispatch", **changes,
            }), self.assertRaisesRegex(ValueError, "main preview lifecycle"):
                self.publish()
        (self.bundle / "preview.py").write_text("# checkout HEAD differs from the workflow SHA\n")
        self.git("add", ".")
        self.git("commit", "-m", "Different checkout revision")
        with patch.dict(os.environ, {**base, "GITHUB_EVENT_NAME": "workflow_dispatch"}), \
             self.assertRaisesRegex(ValueError, "main preview lifecycle"):
            self.publish()


    def test_staging_publication_requires_reviewed_main_and_rejects_pull_request_events(self):
        base = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": "DCGM/PeopleGatorApp",
                "GITHUB_WORKFLOW_REF": "DCGM/PeopleGatorApp/.github/workflows/staging.yml@refs/heads/main",
                "GITHUB_WORKFLOW_SHA": self.revision, "GITHUB_REF": "refs/heads/main"}
        for event in ("workflow_run", "workflow_dispatch"):
            with self.subTest(event=event), patch.dict(os.environ, {**base, "GITHUB_EVENT_NAME": event}):
                self.assertTrue(self.publish().is_dir())
        for changes in ({"GITHUB_EVENT_NAME": "pull_request_target"}, {"GITHUB_EVENT_NAME": "pull_request"},
                        {"GITHUB_REF": "refs/heads/issue/16"},
                        {"GITHUB_WORKFLOW_REF": base["GITHUB_WORKFLOW_REF"].replace("heads/main", "heads/issue/16")}):
            with self.subTest(changes=changes), patch.dict(os.environ, {**base, "GITHUB_EVENT_NAME": "workflow_dispatch", **changes}), self.assertRaises(ValueError):
                self.publish()


# Workflow and registry-credential coverage moved to
# deploy/people-gator-deploy/tests/test_workflows.py with the package workflows.


if __name__ == "__main__":
    unittest.main()
