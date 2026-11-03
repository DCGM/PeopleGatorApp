"""The self-hosted job-started guard admits only reviewed lifecycle workflows."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

GUARD = Path(__file__).resolve().parents[2] / "runner/job-started.sh"
REPOSITORY = "Example/PeopleGatorApp"
WORKFLOWS = f"{REPOSITORY}/.github/workflows"


def git(directory, *args):
    return subprocess.run(["git", "-C", str(directory), *args], check=True, capture_output=True,
                          text=True).stdout.strip()


class RunnerGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        root = Path(cls.temporary.name)
        cls.origin = root / "origin"
        cls.origin.mkdir()
        git(cls.origin, "init", "--quiet", "--initial-branch=main")
        git(cls.origin, "config", "user.email", "guard@example.invalid")
        git(cls.origin, "config", "user.name", "Guard test")
        git(cls.origin, "commit", "--quiet", "--allow-empty", "-m", "reviewed")
        cls.reviewed = git(cls.origin, "rev-parse", "HEAD")
        git(cls.origin, "checkout", "--quiet", "-b", "unreviewed")
        git(cls.origin, "commit", "--quiet", "--allow-empty", "-m", "unreviewed release workflow")
        cls.unreviewed = git(cls.origin, "rev-parse", "HEAD")
        git(cls.origin, "checkout", "--quiet", "main")
        cls.remote = cls.origin.as_uri()

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def guard(self, workflow_ref, *, repository=REPOSITORY, sha=None, remote=None):
        cache = tempfile.TemporaryDirectory()
        self.addCleanup(cache.cleanup)
        environment = {"PATH": os.environ["PATH"], "HOME": cache.name,
                       "PEOPLE_GATOR_RUNNER_REPOSITORY": REPOSITORY,
                       "PEOPLE_GATOR_RUNNER_REMOTE": remote or self.remote,
                       "PEOPLE_GATOR_RUNNER_CACHE": cache.name,
                       "GITHUB_REPOSITORY": repository, "GITHUB_WORKFLOW_REF": workflow_ref,
                       "GITHUB_WORKFLOW_SHA": self.reviewed if sha is None else sha}
        return subprocess.run(["sh", str(GUARD)], env=environment, capture_output=True, text=True, timeout=60)

    def test_reviewed_main_lifecycle_workflows_run(self):
        for name in ("pr-preview.yml", "staging.yml", "release.yml"):
            with self.subTest(workflow=name):
                result = self.guard(f"{WORKFLOWS}/{name}@refs/heads/main")
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_release_tags_run_only_for_commits_on_main(self):
        result = self.guard(f"{WORKFLOWS}/release.yml@refs/tags/v1.2.3", sha=self.reviewed)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.guard(f"{WORKFLOWS}/release.yml@refs/tags/v1.2.4", sha=self.unreviewed)
        self.assertEqual(result.returncode, 1)
        self.assertIn("is not on main", result.stderr)
        for sha in ("", "not-a-commit"):
            with self.subTest(sha=sha):
                self.assertEqual(self.guard(f"{WORKFLOWS}/release.yml@refs/tags/v1.2.3", sha=sha).returncode, 1)

    def test_unreachable_remote_fails_closed(self):
        result = self.guard(f"{WORKFLOWS}/release.yml@refs/tags/v1.2.3",
                            remote=(Path(self.temporary.name) / "missing").as_uri())
        self.assertEqual(result.returncode, 1)
        self.assertIn("cannot read", result.stderr)

    def test_pull_request_branch_and_other_workflows_are_refused(self):
        refused = (
            f"{WORKFLOWS}/pr-ci.yml@refs/heads/main",
            f"{WORKFLOWS}/pr-preview.yml@refs/pull/7/merge",
            f"{WORKFLOWS}/staging.yml@refs/heads/feature",
            f"{WORKFLOWS}/pr-preview.yml@refs/tags/v1.0.0",
            f"{WORKFLOWS}/injected.yml@refs/heads/main",
            f"{WORKFLOWS}/pr-preview.yml@refs/heads/main-copy",
            "",
        )
        for workflow_ref in refused:
            with self.subTest(workflow_ref=workflow_ref):
                result = self.guard(workflow_ref)
                self.assertEqual(result.returncode, 1)
                self.assertIn("runner guard: refused", result.stderr)

    def test_other_repositories_are_refused(self):
        result = self.guard(f"Fork/PeopleGatorApp/.github/workflows/pr-preview.yml@refs/heads/main",
                            repository="Fork/PeopleGatorApp")
        self.assertEqual(result.returncode, 1)
        self.assertIn(f"serves only {REPOSITORY}", result.stderr)


if __name__ == "__main__":
    unittest.main()
