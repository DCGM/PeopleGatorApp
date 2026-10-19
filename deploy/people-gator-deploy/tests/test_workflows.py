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
        base = {"MANUAL_RUN_ID": "", "EXACT_KEY": "", "BACKUP_RECORD": "", "RUN_ID": "789"}
        cases = (
            ({"EVENT_NAME": "workflow_run", "OPERATION": "refresh"}, ["staging", "update", "--run-id", "789"]),
            ({"EVENT_NAME": "workflow_dispatch", "OPERATION": "update"}, ["staging", "update"]),
            ({"EVENT_NAME": "workflow_dispatch", "OPERATION": "snapshot-init", "EXACT_KEY": "p/k.dump"},
             ["staging", "snapshot-init", "--exact-key", "p/k.dump"]),
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


class ImageCredentialTests(unittest.TestCase):
    """Execute pr-ci image registry steps with a fake daemon and private config."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.workflow = (WORKFLOWS / "pr-ci.yml").read_text()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        docker = self.bin / "docker"
        docker.write_text(textwrap.dedent('''\
            #!/usr/bin/env python3
            import json, os, pathlib, sys
            args = sys.argv[1:]
            config = pathlib.Path(os.environ['DOCKER_CONFIG'])
            with open(os.environ['DOCKER_TEST_LOG'], 'a') as log:
                log.write(json.dumps({'args': args, 'config': str(config)}) + '\\n')
            if os.environ.get('DOCKER_TEST_FAIL') == ' '.join(args[:2]):
                sys.exit(1)
            if args == ['context', 'show']:
                print(os.environ['DOCKER_TEST_CONTEXT'])
            elif args[:2] == ['context', 'export']:
                pathlib.Path(args[3]).write_text('synthetic context')
            elif args[:2] == ['context', 'import']:
                assert pathlib.Path(args[3]).read_text() == 'synthetic context'
                (config / 'imported-context').write_text(args[2])
            elif args[:2] == ['context', 'use']:
                if args[2] != 'default':
                    assert (config / 'imported-context').read_text() == args[2]
                assert not (config / 'config.json').exists()
                (config / 'config.json').write_text(json.dumps({'currentContext': args[2]}))
            elif args[0] == 'login':
                assert sys.stdin.read() == 'synthetic-job-token'
                data = json.loads((config / 'config.json').read_text())
                assert 'auths' not in data
                data['auths'] = {'ghcr.io': {'auth': 'synthetic-job-login'}}
                (config / 'config.json').write_text(json.dumps(data))
            elif args[0] == 'pull':
                data = json.loads((config / 'config.json').read_text())
                assert data['currentContext'] == os.environ['DOCKER_TEST_CONTEXT']
                assert data['auths']['ghcr.io']['auth'] == 'synthetic-job-login'
            else:
                sys.exit('Unexpected fake Docker operation')
            '''))
        docker.chmod(0o755)
        self.ambient = self.root / "ambient"
        self.ambient.mkdir()
        (self.ambient / "config.json").write_text('{"auths":{"other":{"auth":"retained-login"}}}')

    def step(self, name):
        return self.workflow.split(f"      - name: {name}\n", 1)[1].split("      - name:", 1)[0]

    def script(self, name):
        step = self.step(name)
        run = step.split("        run: ", 1)[1]
        if run.startswith("|\n"):
            return textwrap.dedent(run[2:])
        return run.splitlines()[0]

    def shell(self, script, environment):
        return subprocess.run(["bash", "-e", "-o", "pipefail", "-c", script],
                              env=environment, text=True, capture_output=True, timeout=10)

    def test_image_matrix_jobs_cannot_remove_each_others_registry_credentials(self):
        self.workflow = (WORKFLOWS / "pr-ci.yml").read_text()
        login, build = self.step("Log into image registry"), self.step("Build and publish image")
        self.assertIn("logout: false", login)
        for step in (login, build):
            self.assertIn("DOCKER_CONFIG: ${{ steps.registry-config.outputs.path }}", step)
        self.assertIn("BUILDX_CONFIG: ${{ steps.registry-config.outputs.buildx-config }}", build)
        self.assertIn("if: always() && steps.registry-config.outputs.path != ''",
                      self.step("Remove image registry credentials"))
        for context in ("default", "rootless-ci"):
            configurations = []
            environment = {**os.environ, "PATH": f"{self.bin}:{os.environ['PATH']}",
                           "RUNNER_TEMP": str(self.root), "DOCKER_CONFIG": str(self.ambient),
                           "DOCKER_TEST_LOG": str(self.root / "image-docker-log"),
                           "DOCKER_TEST_CONTEXT": context, "DOCKER_TEST_FAIL": "",
                           "GH_TOKEN": "synthetic-job-token", "GH_ACTOR": "synthetic-actor"}
            environment.pop("BUILDX_CONFIG", None)
            try:
                for job in ("backend", "frontend"):
                    output = self.root / f"image-output-{job}"
                    output.write_text("")
                    environment["GITHUB_OUTPUT"] = str(output)
                    result = self.shell(self.script("Prepare image registry configuration"), environment)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    values = dict(line.split("=", 1) for line in output.read_text().splitlines())
                    configurations.append(values["path"])
                    self.assertEqual(values["buildx-config"], str(self.ambient / "buildx"))
                    result = self.shell('printf %s "$GH_TOKEN" | docker login ghcr.io -u "$GH_ACTOR" --password-stdin',
                                        {**environment, "DOCKER_CONFIG": values["path"]})
                    self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotEqual(*configurations)
                result = self.shell(self.script("Remove image registry credentials"),
                                    {**environment, "IMAGE_DOCKER_CONFIG": configurations[0]})
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse(Path(configurations[0]).exists())
                # The later-finishing frontend can still authenticate after
                # backend completion; the ambient context/config stays intact.
                result = self.shell("docker pull image", {**environment, "DOCKER_CONFIG": configurations[1]})
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("retained-login", (self.ambient / "config.json").read_text())
            finally:
                for configuration in configurations:
                    self.shell(self.script("Remove image registry credentials"),
                               {**environment, "IMAGE_DOCKER_CONFIG": configuration})
            self.assertEqual(list(self.root.glob("people-gator-ci-docker.*")), [])


if __name__ == "__main__":
    unittest.main()
