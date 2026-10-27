"""Real isolated installs from committed sources, including interrupted upgrades."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from people_gator_deploy import installer
from people_gator_deploy.core import DeployError


class InstallationTests(unittest.TestCase):
    def setUp(self):
        # Real disposable operator installs must not inherit the runner's PR-CI
        # identity. The source-policy test explicitly enables Actions for each
        # trusted/untrusted workflow case below.
        environment = patch.dict(os.environ, {"GITHUB_ACTIONS": "false"})
        environment.start()
        self.addCleanup(environment.stop)

    def test_install_reuse_upgrade_pinning_and_failed_publication(self):
        with tempfile.TemporaryDirectory(prefix="deploy test ") as directory:
            root = Path(directory)
            source = root / "source"
            package = source / installer.PACKAGE
            shutil.copytree(Path(__file__).resolve().parents[1], package,
                            ignore=shutil.ignore_patterns("build", "*.egg-info", "__pycache__"))
            def git(*args):
                return subprocess.check_output(["git", "-C", str(source), *args], stderr=subprocess.DEVNULL).decode().strip()
            git("init", "-q")
            git("config", "user.name", "Synthetic installer test")
            git("config", "user.email", "test@example.invalid")
            git("add", ".")
            git("commit", "-qm", "First utility")
            first = git("rev-parse", "HEAD")
            prefix = root / "user prefix"
            result = installer.install(source, first, prefix=prefix)
            executable = Path(result["executable"])
            invocation = subprocess.check_output([executable, "--version"], cwd="/tmp")
            self.assertEqual(json.loads(invocation)["revision"], first)
            subprocess.run([executable.parent / "python", "-I", "-B", "-c",
                            "import boto3; from people_gator_deploy import snapshots"],
                           cwd="/tmp", check=True, capture_output=True)
            default = prefix / "bin/people-gator-deploy"
            def default_revision():
                environment = {**os.environ, "PATH": str(default.parent) + os.pathsep + os.environ["PATH"]}
                return json.loads(subprocess.check_output(["people-gator-deploy", "--version"],
                                                         cwd="/tmp", env=environment))["revision"]
            self.assertEqual(default_revision(), first)
            (Path(result["config"]) / "private.json").write_text("retained")
            original = installer.integrity(executable.parent.parent)
            self.assertTrue(installer.install(source, first, prefix=prefix)["default_activated"])
            self.assertEqual(original, installer.integrity(executable.parent.parent))
            (package / "src/people_gator_deploy/next.txt").write_text("new source")
            git("add", ".")
            git("commit", "-qm", "Next utility")
            second = git("rev-parse", "HEAD")
            with patch.object(installer.venv.EnvBuilder, "create", side_effect=OSError("Interrupted")):
                with self.assertRaises(OSError):
                    installer.install(source, second, prefix=prefix)
            self.assertEqual((prefix / "bin/people-gator-deploy").resolve(), executable)
            self.assertEqual(default_revision(), first)
            updated = installer.install(source, second, prefix=prefix)
            self.assertTrue(updated["default_activated"])
            self.assertEqual(default_revision(), second)
            self.assertEqual(json.loads(subprocess.check_output([executable, "--version"]))["revision"], first)
            self.assertFalse(installer.install(source, first, prefix=prefix)["default_activated"])
            self.assertEqual(default_revision(), second)
            self.assertEqual((prefix / "bin/people-gator-deploy").resolve(), Path(updated["executable"]))
            self.assertEqual((Path(result["config"]) / "private.json").read_text(), "retained")
            self.assertEqual(git("status", "--porcelain"), "")
            (executable.parent.parent / "extra").write_text("corrupt")
            with self.assertRaisesRegex(DeployError, "corrupt"):
                installer.install(source, first, prefix=prefix)

    def test_ci_installs_only_reviewed_workflow_commits_and_tagged_commits_on_main(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            def git(*args):
                return subprocess.check_output(["git", "-C", str(source), *args], stderr=subprocess.DEVNULL).decode().strip()
            git("init", "-q")
            git("config", "user.name", "Synthetic installer test")
            git("config", "user.email", "test@example.invalid")
            git("commit", "-q", "--allow-empty", "-m", "Reviewed main")
            reviewed = git("rev-parse", "HEAD")
            git("update-ref", "refs/remotes/origin/main", reviewed)
            git("checkout", "-q", "-b", "unreviewed")
            git("commit", "-q", "--allow-empty", "-m", "Tagged outside main")
            outside = git("rev-parse", "HEAD")
            repository = "DCGM/PeopleGatorApp"
            cases = {
                f"{repository}/.github/workflows/pr-ci.yml@refs/pull/7/merge": (reviewed, "exact reviewed main"),
                f"{repository}/.github/workflows/pr-preview.yml@refs/heads/feature": (reviewed, "exact reviewed main"),
                f"{repository}/.github/workflows/release.yml@refs/tags/v1.0.0": (outside, "already reviewed on main"),
            }
            for workflow, (revision, message) in cases.items():
                environment = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": repository,
                               "GITHUB_WORKFLOW_REF": workflow, "GITHUB_WORKFLOW_SHA": revision}
                with self.subTest(workflow=workflow), patch.dict(os.environ, environment), \
                        self.assertRaisesRegex(DeployError, message):
                    installer.install(source, revision, prefix=source / "prefix")
                self.assertFalse((source / "prefix").exists())
            # A tag on main passes the policy and reaches the (interrupted) build.
            environment = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": repository,
                           "GITHUB_WORKFLOW_REF": f"{repository}/.github/workflows/release.yml@refs/tags/v1.0.0",
                           "GITHUB_WORKFLOW_SHA": reviewed}
            with patch.dict(os.environ, environment):
                original = installer.run
                def archive_stops(args, **kwargs):
                    if "archive" in args:
                        raise OSError("build reached")
                    return original(args, **kwargs)
                with patch.object(installer, "run", side_effect=archive_stops):
                    with self.assertRaisesRegex(OSError, "build reached"):
                        installer.install(source, reviewed, prefix=source / "prefix")
                with patch("os.geteuid", return_value=0), self.assertRaisesRegex(DeployError, "system installation"):
                    installer.install(source, reviewed, scope="system", run_as="nobody")

    def test_system_scope_requires_operator_and_unprivileged_run_as(self):
        with patch("os.geteuid", return_value=1000):
            with self.assertRaisesRegex(DeployError, "operator"):
                installer.install(Path("/tmp"), "a" * 40, scope="system", run_as="nobody")


if __name__ == "__main__":
    unittest.main()
