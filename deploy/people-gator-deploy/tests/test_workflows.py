"""Workflows only select/install/check the trusted utility and invoke its lifecycle operations."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest

from people_gator_deploy import cli

REPOSITORY = Path(__file__).resolve().parents[3]
WORKFLOWS = REPOSITORY / ".github/workflows"
LIFECYCLES = {"pr-preview.yml": "pr", "staging.yml": "staging", "release.yml": "release"}


def step(workflow, name):
    return workflow.split(f"      - name: {name}\n", 1)[1].split("      - name:", 1)[0]


def script(workflow, name):
    run = step(workflow, name).split("        run: ", 1)[1]
    if run.startswith("|\n"):
        return textwrap.dedent(run[2:])
    line = run.splitlines()[0]
    return line[1:-1] if line.startswith("'") else line


def shell(command, environment):
    return subprocess.run(["bash", "-e", "-o", "pipefail", "-c", command],
                          env=environment, text=True, capture_output=True, timeout=10)


class LifecycleWorkflowTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.deploy = self.root / "versions/reviewed/bin/people-gator-deploy"
        self.deploy.parent.mkdir(parents=True)
        self.output = self.root / "invocations"
        self.deploy.write_text("#!/usr/bin/env python3\nimport json, os, sys\n"
                               "open(os.environ['DEPLOY_TEST_OUTPUT'], 'a').write(json.dumps(sys.argv[1:]) + '\\n')\n")
        self.deploy.chmod(0o755)

    def invocations(self, workflow, name, **environment):
        self.output.write_text("")
        result = shell(script(workflow, name), {**os.environ, "DEPLOY": str(self.deploy),
                                                "DEPLOY_TEST_OUTPUT": str(self.output), **environment})
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = [json.loads(line) for line in self.output.read_text().splitlines()]
        for call in calls:
            # Every workflow command must be accepted by the real installed CLI.
            cli.parser().parse_args(call)
        return calls

    def test_trusted_utility_is_installed_from_the_workflow_commit_before_any_lifecycle(self):
        for name, environment in LIFECYCLES.items():
            workflow = (WORKFLOWS / name).read_text()
            with self.subTest(workflow=name):
                checkout = step(workflow, "Read trusted deployment utility")
                self.assertIn("ref: ${{ github.workflow_sha }}", checkout)
                self.assertIn("persist-credentials: false", checkout)
                # Installer activation compares ancestry with the previous default.
                self.assertIn("fetch-depth: 0", checkout)
                self.assertIn("sparse-checkout: deploy", checkout)
                self.assertIn('deploy/install.py --user --revision "$GITHUB_WORKFLOW_SHA"',
                              step(workflow, "Select trusted deployment utility"))
                preflight = next(n for n in re.findall(r"      - name: (.+)\n", workflow) if n.startswith("Check "))
                self.assertEqual(script(workflow, preflight), f'"$DEPLOY" {environment} preflight')
                names = re.findall(r"      - name: (.+)\n", workflow)
                self.assertEqual(names[:3], ["Read trusted deployment utility", "Select trusted deployment utility", preflight])
                self.assertEqual(len(names), 4)
                self.assertIn(f".github/workflows/{name}@", workflow)
                self.assertIn("github.workflow_ref == format(", workflow)
                # No second deployment implementation, privilege escalation or PR head code.
                for forbidden in ("sudo", "docker ", "release.py", "preview.py", "staging.py",
                                  "pull_request.head", "/opt/people-gator-preview", "DOCKER_CONFIG"):
                    self.assertNotIn(forbidden, workflow)
                self.assertIn("cancel-in-progress: false", workflow)

    def test_backup_roundtrip_imports_the_shared_fixture_without_opt_in(self):
        suite = REPOSITORY / "deploy/backup/tests/test_roundtrip.py"
        # The trusted workflow's sparse checkout includes deploy, including this
        # consumer. Import it even when the opt-in Docker test is disabled.
        result = subprocess.run([sys.executable, "-B", str(suite)], capture_output=True, text=True,
                                env={k: v for k, v in os.environ.items() if k != "BACKUP_TEST_IMAGE"},
                                timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("skipped=", result.stderr)

    def test_preview_events_map_to_package_operations(self):
        workflow = (WORKFLOWS / "pr-preview.yml").read_text()
        for event, expected in (("workflow_run", ["pr", "update", "--run-id", "456"]),
                                ("pull_request_target", ["pr", "cleanup", "--pr", "123"]),
                                ("schedule", ["pr", "reconcile"]), ("workflow_dispatch", ["pr", "reconcile"])):
            with self.subTest(event=event):
                self.assertEqual(self.invocations(workflow, "Apply preview lifecycle", EVENT_NAME=event,
                                                  RUN_ID="456", PR_NUMBER="123"), [expected])
        result = shell(script(workflow, "Apply preview lifecycle"), {**os.environ, "EVENT_NAME": "push",
                                                                     "DEPLOY": str(self.deploy)})
        self.assertEqual(result.returncode, 2)

    def test_staging_events_retain_data_unless_snapshot_operations_are_explicit(self):
        workflow = (WORKFLOWS / "staging.yml").read_text()
        base = {"MANUAL_RUN_ID": "", "BACKUP_RECORD": "", "RUN_ID": "789"}
        cases = (
            ({"EVENT_NAME": "workflow_run", "OPERATION": "refresh"}, ["staging", "update", "--run-id", "789"]),
            ({"EVENT_NAME": "workflow_dispatch", "OPERATION": "update"}, ["staging", "update"]),
            ({"EVENT_NAME": "workflow_dispatch", "OPERATION": "snapshot-init"},
             ["staging", "snapshot-init"]),
            ({"EVENT_NAME": "workflow_dispatch", "OPERATION": "refresh", "MANUAL_RUN_ID": "790",
              "BACKUP_RECORD": "/private/record"},
             ["staging", "refresh", "--run-id", "790", "--backup-record", "/private/record"]),
        )
        for environment, expected in cases:
            with self.subTest(environment=environment):
                self.assertEqual(self.invocations(workflow, "Apply staging lifecycle", **{**base, **environment}), [expected])
        self.assertIn("options: [update, snapshot-init, refresh]", workflow)
        self.assertIn("event == 'push'", workflow)
        self.assertIn("head_branch == 'main'", workflow)

    def test_release_tag_and_manual_delivery_pin_the_tagged_commit(self):
        workflow = (WORKFLOWS / "release.yml").read_text()
        self.assertIn("tags: ['v*']", workflow)
        self.assertIn("fetch-depth: 0", step(workflow, "Read trusted deployment utility"))
        self.assertIn("TAG_COMMIT: ${{ github.event_name == 'push' && github.sha || '' }}", workflow)
        base = {"RELEASE_TAG": "v1.2.3", "TAG_COMMIT": "", "RUN_ID": "", "BACKUP_RECORD": ""}
        for environment, expected in (
                ({"TAG_COMMIT": "a" * 40}, ["release", "update", "--tag", "v1.2.3", "--commit", "a" * 40]),
                ({"RUN_ID": "55", "BACKUP_RECORD": "/private/backup"},
                 ["release", "update", "--tag", "v1.2.3", "--run-id", "55", "--backup-record", "/private/backup"])):
            with self.subTest(environment=environment):
                self.assertEqual(self.invocations(workflow, "Deliver release", **{**base, **environment}), [expected])


class RunnerPlacementTests(unittest.TestCase):
    """PR code runs on ephemeral hosted runners; self-hosted runners serve only lifecycles."""

    @staticmethod
    def placements(workflow):
        return re.findall(r"^    runs-on: (.+)$", (WORKFLOWS / workflow).read_text(), re.MULTILINE)

    def test_pull_request_code_runs_only_on_github_hosted_runners(self):
        workflow = (WORKFLOWS / "pr-ci.yml").read_text()
        self.assertEqual(self.placements("pr-ci.yml"), ["ubuntu-24.04"] * 3)
        for forbidden in ("people-gator-ci", "runner.tool_cache", "keep-state"):
            self.assertNotIn(forbidden, workflow)

    def test_pull_request_ci_needs_no_secrets_or_external_services(self):
        workflow = (WORKFLOWS / "pr-ci.yml").read_text()
        self.assertEqual(set(re.findall(r"secrets\.([A-Za-z_]+)", workflow)), {"GITHUB_TOKEN"})
        # S3 suites need a disposable MinIO image or real storage credentials; run them locally.
        for opt_in in ("BACKUP_TEST_IMAGE", "STAGING_TEST_IMAGE", "test_roundtrip.py", "test_staging_runtime.py"):
            self.assertNotIn(opt_in, workflow)

    def test_each_lifecycle_uses_only_its_deployment_runner(self):
        labels = {"pr-preview.yml": "people-gator-preview", "staging.yml": "people-gator-staging",
                  "release.yml": "people-gator-release"}
        for name, label in labels.items():
            with self.subTest(workflow=name):
                self.assertEqual(self.placements(name), [f"[self-hosted, linux, x64, {label}]"])
        configured = re.findall(r"^    - (.+)$", (REPOSITORY / ".github/actionlint.yaml").read_text(), re.MULTILINE)
        self.assertEqual(sorted(configured), sorted(labels.values()))


if __name__ == "__main__":
    unittest.main()
