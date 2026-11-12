"""The self-hosted job-started guard admits only this repository's events for the runner's environment."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

GUARD = Path(__file__).resolve().parents[2] / "runner/job-started.sh"
REPOSITORY = "Example/PeopleGatorApp"


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
        git(cls.origin, "commit", "--quiet", "--allow-empty", "-m", "unreviewed release")
        cls.unreviewed = git(cls.origin, "rev-parse", "HEAD")
        git(cls.origin, "checkout", "--quiet", "main")
        cls.remote = cls.origin.as_uri()

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def guard(self, environment, event, ref, *, repository=REPOSITORY, sha=None, head_repository=REPOSITORY, remote=None,
              action="synchronize"):
        cache = tempfile.TemporaryDirectory()
        self.addCleanup(cache.cleanup)
        payload = Path(cache.name) / "event.json"
        payload.write_text(json.dumps({"action": action,
                                       "pull_request": {"head": {"repo": {"full_name": head_repository} if head_repository else None}}}))
        variables = {"PATH": os.environ["PATH"], "HOME": cache.name,
                     "PEOPLE_GATOR_RUNNER_REPOSITORY": REPOSITORY, "PEOPLE_GATOR_RUNNER_REMOTE": remote or self.remote,
                     "PEOPLE_GATOR_RUNNER_CACHE": cache.name, "GITHUB_REPOSITORY": repository,
                     "GITHUB_EVENT_NAME": event, "GITHUB_REF": ref, "GITHUB_EVENT_PATH": str(payload),
                     "GITHUB_SHA": self.reviewed if sha is None else sha}
        if environment is not None:
            variables["PEOPLE_GATOR_RUNNER_ENVIRONMENT"] = environment
        return subprocess.run(["sh", str(GUARD)], env=variables, capture_output=True, text=True, timeout=60)

    def assertAdmitted(self, *args, **kwargs):
        result = self.guard(*args, **kwargs)
        self.assertEqual(result.returncode, 0, result.stderr)

    def assertRefused(self, *args, message="runner guard: refused", **kwargs):
        result = self.guard(*args, **kwargs)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn(message, result.stderr)
        return result

    def test_preview_runner_serves_same_repository_pull_requests_and_main_pruning(self):
        self.assertAdmitted("preview", "pull_request", "refs/pull/7/merge")
        for event in ("push", "schedule", "workflow_dispatch"):
            with self.subTest(event=event):
                self.assertAdmitted("preview", event, "refs/heads/main")
        self.assertRefused("preview", "push", "refs/heads/feature")
        self.assertRefused("preview", "push", "refs/tags/v1.0.0")

    def test_preview_runner_removes_closed_pull_requests_on_their_base_branch(self):
        # A closed pull request's GITHUB_REF is its base branch, not refs/pull/<N>/merge.
        self.assertAdmitted("preview", "pull_request", "refs/heads/main", action="closed")
        self.assertRefused("preview", "pull_request", "refs/heads/main", action="synchronize")
        self.assertRefused("preview", "pull_request", "refs/heads/main", action="closed",
                           head_repository="Fork/PeopleGatorApp", message="other repositories never run here")
        self.assertRefused("staging", "pull_request", "refs/heads/main", action="closed")

    def test_fork_pull_requests_are_refused_whatever_their_workflow_says(self):
        for head in ("Fork/PeopleGatorApp", None):
            with self.subTest(head=head):
                self.assertRefused("preview", "pull_request", "refs/pull/7/merge", head_repository=head,
                                   message="other repositories never run here")
        self.assertRefused("preview", "pull_request_target", "refs/heads/main", head_repository="Fork/PeopleGatorApp",
                           message="other repositories never run here")
        self.assertRefused("staging", "pull_request", "refs/pull/7/merge")

    def test_staging_runner_serves_only_main(self):
        self.assertAdmitted("staging", "push", "refs/heads/main")
        self.assertAdmitted("staging", "workflow_dispatch", "refs/heads/main")
        for event, ref in (("push", "refs/heads/feature"), ("push", "refs/tags/v1.0.0"), ("schedule", "refs/heads/main")):
            with self.subTest(event=event, ref=ref):
                self.assertRefused("staging", event, ref)

    def test_release_runner_serves_only_tags_whose_commit_is_on_main(self):
        self.assertAdmitted("release", "push", "refs/tags/v1.2.3", sha=self.reviewed)
        self.assertAdmitted("release", "workflow_dispatch", "refs/tags/v1.2.3", sha=self.reviewed)
        self.assertRefused("release", "push", "refs/tags/v1.2.4", sha=self.unreviewed, message="is not on main")
        self.assertRefused("release", "push", "refs/heads/main")
        self.assertRefused("release", "push", "refs/tags/release-1")
        for sha in ("", "not-a-commit"):
            with self.subTest(sha=sha):
                self.assertRefused("release", "push", "refs/tags/v1.2.3", sha=sha, message="missing tagged commit")

    def test_unreachable_remote_fails_closed(self):
        self.assertRefused("release", "push", "refs/tags/v1.2.3", remote=(Path(self.temporary.name) / "missing").as_uri(),
                           message="cannot read")

    def test_runners_with_several_labels_serve_every_listed_environment(self):
        self.assertAdmitted("preview,staging", "pull_request", "refs/pull/7/merge")
        self.assertAdmitted("preview,staging", "push", "refs/heads/main")
        self.assertAdmitted("staging, release", "workflow_dispatch", "refs/heads/main")
        self.assertAdmitted("staging,release", "push", "refs/tags/v1.2.3", sha=self.reviewed)
        self.assertRefused("preview,staging", "push", "refs/tags/v1.2.3")
        self.assertRefused("preview,staging", "pull_request", "refs/pull/7/merge", head_repository="Fork/PeopleGatorApp",
                           message="other repositories never run here")
        self.assertRefused("preview,ci", "push", "refs/heads/main", message="unknown environment 'ci'")

    def test_misconfigured_runner_and_other_repositories_are_refused(self):
        self.assertRefused(None, "push", "refs/heads/main", message="PEOPLE_GATOR_RUNNER_ENVIRONMENT")
        self.assertRefused("ci", "push", "refs/heads/main", message="PEOPLE_GATOR_RUNNER_ENVIRONMENT")
        self.assertRefused("preview", "push", "refs/heads/main", repository="Fork/PeopleGatorApp", message=f"serves only {REPOSITORY}")


if __name__ == "__main__":
    unittest.main()
