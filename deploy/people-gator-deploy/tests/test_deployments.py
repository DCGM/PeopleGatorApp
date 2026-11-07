"""Only the current GitHub Deployment of each environment (per PR branch for previews) stays active."""
import os
import unittest
from unittest.mock import patch

from people_gator_deploy import deployments
from people_gator_deploy.core import DeployError


class FakeGitHub:
    def __init__(self, listing, statuses=None, pulls=()):
        self.listing = listing          # environment -> [(id, ref)] newest first
        self.statuses = statuses or {}  # id -> state
        self.pulls = list(pulls)
        self.posts = []

    def __call__(self, repository, endpoint, *, method="GET", data=None):
        assert repository == "DCGM/PeopleGatorApp"
        if method == "POST":
            self.posts.append((endpoint, data))
            return {"state": data["state"]}
        path, _, query = endpoint.partition("?")
        params = dict(part.split("=") for part in query.split("&") if part)
        page = int(params.get("page", 1))
        if path == "deployments":
            items = [{"id": i, "ref": r} for i, r in self.listing.get(params["environment"], [])
                     if "ref" not in params or r == params["ref"]]
            return items[(page - 1) * 100:page * 100]
        if path == "pulls":
            return self.pulls[(page - 1) * 100:page * 100]
        if path.startswith("deployments/") and path.endswith("/statuses"):
            state = self.statuses.get(int(path.split("/")[1]))
            return [{"state": state}] if state else []
        raise AssertionError(endpoint)


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {"GITHUB_REPOSITORY": "DCGM/PeopleGatorApp"})
        environment.start()
        self.addCleanup(environment.stop)

    def run_with(self, github, *args, **kwargs):
        with patch.object(deployments, "github_api", github):
            return deployments.Deployments().execute(*args, **kwargs)

    def test_supersede_keeps_the_newest_and_skips_already_inactive(self):
        github = FakeGitHub({"staging": [(30, "main"), (20, "main"), (10, "main")]}, statuses={10: "inactive", 20: "success"})
        result = self.run_with(github, "supersede", environment="staging")
        self.assertEqual(result["inactive"], [20])
        self.assertEqual(github.posts, [("deployments/20/statuses", {"state": "inactive"})])

    def test_preview_supersede_and_retire_are_scoped_to_the_branch(self):
        listing = {"preview": [(5, "issue/9"), (4, "issue/7"), (3, "issue/9"), (2, "issue/7")]}
        github = FakeGitHub(listing)
        self.assertEqual(self.run_with(github, "supersede", environment="preview", ref="issue/7")["inactive"], [2])
        github = FakeGitHub(listing)
        self.assertEqual(self.run_with(github, "retire", ref="issue/9")["inactive"], [5, 3])
        with self.assertRaisesRegex(DeployError, "Invalid deployment ref"):
            self.run_with(github, "retire", ref="bad ref\n")

    def test_prune_keeps_one_active_preview_per_open_same_repository_pr(self):
        pulls = [{"head": {"ref": "issue/7", "repo": {"full_name": "dcgm/peoplegatorapp"}}},
                 {"head": {"ref": "fork-branch", "repo": {"full_name": "Fork/PeopleGatorApp"}}}]
        github = FakeGitHub({"preview": [(6, "fork-branch"), (5, "issue/9"), (4, "issue/7"), (2, "issue/7")],
                             "staging": [(30, "main"), (20, "main")], "production": [(40, "v1.0.0")]}, pulls=pulls)
        result = self.run_with(github, "prune")
        self.assertEqual(result["inactive"], {"staging": [20], "production": [], "preview": [6, 5, 2]})

    def test_listing_pages_through_large_histories(self):
        github = FakeGitHub({"production": [(1000 - i, "v1") for i in range(250)]})
        result = self.run_with(github, "supersede", environment="production")
        self.assertEqual(len(result["inactive"]), 249)
        self.assertNotIn(1000, result["inactive"])

    def test_repository_identity_is_required(self):
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": ""}), self.assertRaisesRegex(DeployError, "GITHUB_REPOSITORY"):
            deployments.Deployments()


if __name__ == "__main__":
    unittest.main()
