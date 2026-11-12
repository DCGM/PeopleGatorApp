"""One CI workflow: hosted tests/images, self-hosted deploy jobs only for same-repository events."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

import yaml

from people_gator_deploy import cli, config

REPOSITORY = Path(__file__).resolve().parents[3]
WORKFLOWS = REPOSITORY / ".github/workflows"
WORKFLOW = WORKFLOWS / "ci.yml"
TOOLS = "./.github/actions/deploy-tools"
HOSTED = ("frontend", "backend", "images")
# job -> (runner label, GitHub Environment, deploy environment of the utility)
DEPLOY_JOBS = {
    "deploy-preview": ("people-gator-preview", "preview", "pr"),
    "remove-preview": ("people-gator-preview", None, "pr"),
    "prune-previews": ("people-gator-preview", None, "pr"),
    "deploy-staging": ("people-gator-staging", "staging", "staging"),
    "deploy-release": ("people-gator-release", "production", "release"),
}
FORK_GUARD = "github.event.pull_request.head.repo.full_name == github.repository"
SHA = "a" * 40
PREFIXES = {"pr": "PREVIEW", "staging": "STAGING", "release": "PRODUCTION"}
SAMPLES = {"HOST": "app.example.invalid", "DATABASE_URL": "postgresql://u:p@db:5432/d", "MIGRATION_DATABASE_URL": "postgresql://m:p@db:5432/d",
           "STORAGE_DIR": "", "S3_ENDPOINT_URL": "https://s3.example.invalid", "S3_REGION": "r", "S3_BUCKET": "b",
           "S3_ACCESS_KEY_ID": "k", "S3_SECRET_ACCESS_KEY": "s", "BACKUP_S3_ENDPOINT_URL": "https://s3.example.invalid",
           "BACKUP_S3_REGION": "r", "BACKUP_S3_BUCKET": "backups", "BACKUP_S3_PREFIX": "p/", "BACKUP_S3_ACCESS_KEY_ID": "rk",
           "BACKUP_S3_SECRET_ACCESS_KEY": "rs", "OTEL_ENDPOINT": "http://lgtm:4318", "OTEL_HEADERS": "Authorization=Basic x",
           "RUM_CLIENT_TOKEN": "t", "RUM_SITE": "o2.example", "USERS_JSON": '{"test": {"hash": "h", "scopes": []}}'}


def workflow():
    return yaml.safe_load(WORKFLOW.read_text())


def triggers(document):
    return document.get("on", document.get(True))  # PyYAML reads the bare key `on` as a boolean


def scripts(job):
    return [step["run"] for step in job["steps"] if "run" in step]


class WorkflowStructureTests(unittest.TestCase):
    def test_single_workflow_replaces_the_chained_lifecycle_workflows(self):
        self.assertEqual([path.name for path in WORKFLOWS.iterdir()], ["ci.yml"])
        document = workflow()
        events = triggers(document)
        self.assertEqual(events["push"], {"branches": ["main"], "tags": ["v*"]})
        self.assertEqual(set(events["pull_request"]["types"]), {"opened", "synchronize", "reopened", "ready_for_review", "closed"})
        self.assertEqual(events["workflow_dispatch"]["inputs"]["operation"]["options"], ["update", "snapshot-init", "refresh"])
        self.assertIn("backup_record", events["workflow_dispatch"]["inputs"])
        self.assertEqual(len(events["schedule"]), 1)
        text = WORKFLOW.read_text()
        for forbidden in ("workflow_run", "pull_request_target", "install.py", "sudo", "workflow_sha", "run-id", " install",
                          "versions/", "docker/login-action@v3\n        with:\n          registry: ghcr.io\n          username: ${{ github.actor }}\n          password: ${{ secrets.GITHUB_TOKEN }}\n      - uses: ./.github"):
            self.assertNotIn(forbidden, text)
        expected = {"GITHUB_TOKEN"}
        for environment, prefix in PREFIXES.items():
            expected |= {f"{prefix}_{name}" for name in config.names(environment) if config.VARIABLES[name][1]}
        self.assertEqual(set(re.findall(r"secrets\.([A-Za-z0-9_]+)", text)), expected)
        self.assertEqual(document["permissions"], {"contents": "read"})

    def test_pipeline_concurrency_isolates_events_and_pull_requests(self):
        document = workflow()
        group = document["concurrency"]["group"]
        self.assertIn("github.event_name", group)
        self.assertIn("github.event.pull_request.number || github.ref", group)
        self.assertEqual(document["concurrency"]["cancel-in-progress"], "${{ github.event_name == 'pull_request' }}")
        self.assertEqual(document["env"]["COMMIT_SHA"], "${{ github.event.pull_request.head.sha || github.sha }}")

    def test_pull_request_code_runs_only_on_github_hosted_runners(self):
        jobs = workflow()["jobs"]
        for name in HOSTED:
            with self.subTest(job=name):
                self.assertEqual(jobs[name]["runs-on"], "ubuntu-24.04")
        for name in ("frontend", "backend"):
            self.assertIn("github.event.action != 'closed'", jobs[name]["if"])
            self.assertIn("github.event_name != 'schedule'", jobs[name]["if"])
        images = jobs["images"]
        self.assertEqual(images["needs"], ["frontend", "backend"])
        self.assertEqual(images["permissions"], {"contents": "read", "packages": "write"})
        publish = next(step for step in images["steps"] if step.get("name") == "Build and publish image")
        self.assertIn(FORK_GUARD, publish["with"]["push"])
        self.assertTrue(publish["with"]["tags"].endswith(":sha-${{ env.COMMIT_SHA }}"))
        self.assertEqual(publish["with"]["labels"], "org.opencontainers.image.revision=${{ env.COMMIT_SHA }}")
        login = next(step for step in images["steps"] if step.get("name") == "Log into image registry")
        self.assertIn(FORK_GUARD, login["if"])
        backend = "\n".join(scripts(jobs["backend"]))
        self.assertIn("unittest discover -s ../deploy/people-gator-deploy/tests", backend)
        self.assertIn("people_gator_api.cli.seed", backend)
        # The pytest shards together run the whole suite exactly once.
        parts = jobs["backend"]["strategy"]["matrix"]["part"]
        shards = [part for part in parts if part != "tools"]
        self.assertEqual(shards, [f"{index}/{len(shards)}" for index in range(1, len(shards) + 1)])
        self.assertIn("tools", parts)
        self.assertIn("pytest tests -n 4 --dist=worksteal --shard=${{ matrix.part }}", backend)
        for opt_in in ("BACKUP_TEST_IMAGE", "STAGING_TEST_IMAGE", "test_roundtrip.py", "test_staging_runtime.py"):
            self.assertNotIn(opt_in, WORKFLOW.read_text())

    def test_deploy_jobs_run_on_their_runner_as_github_deployments(self):
        jobs = workflow()["jobs"]
        self.assertEqual(set(jobs), {*HOSTED, *DEPLOY_JOBS})
        for name, (label, environment, _) in DEPLOY_JOBS.items():
            job = jobs[name]
            with self.subTest(job=name):
                self.assertEqual(job["runs-on"], ["self-hosted", "linux", "x64", label])
                self.assertEqual(job["permissions"]["deployments"], "write")
                self.assertEqual(job["permissions"]["contents"], "read")
                self.assertEqual(job["concurrency"]["cancel-in-progress"], False)
                if environment:
                    self.assertEqual(job["environment"]["name"], environment)
                    self.assertTrue(job["environment"]["url"].startswith("https://"))
                else:
                    self.assertNotIn("environment", job)
                uses = [step.get("uses", "") for step in job["steps"]]
                self.assertIn(TOOLS, uses)
                checkout = next(step for step in job["steps"] if step.get("uses", "").startswith("actions/checkout"))
                self.assertEqual(checkout["with"]["persist-credentials"], False)
                self.assertNotIn("docker/login-action", " ".join(uses))  # the utility logs in with a disposable config
                self.assertEqual(job["env"]["GH_TOKEN"], "${{ secrets.GITHUB_TOKEN }}")
        self.assertEqual(jobs["deploy-preview"]["environment"]["url"], "https://pr-${{ github.event.number }}.${{ steps.preflight.outputs.host }}")
        for name in ("deploy-staging", "deploy-release"):
            self.assertEqual(jobs[name]["environment"]["url"], "https://${{ steps.preflight.outputs.host }}")
            self.assertEqual(next(step["id"] for step in jobs[name]["steps"] if step.get("name", "").startswith("Check ")), "preflight")
        for name in ("deploy-preview", "remove-preview"):
            self.assertIn(FORK_GUARD, jobs[name]["if"])
            self.assertIn("github.event_name == 'pull_request'", jobs[name]["if"])
            self.assertEqual(jobs[name]["concurrency"]["group"], "deploy-preview-${{ github.event.number }}")
            self.assertEqual(jobs[name]["steps"][0]["with"]["ref"], "${{ github.event.pull_request.head.sha }}")
        self.assertIn("github.event.action != 'closed'", jobs["deploy-preview"]["if"])
        self.assertIn("github.event.action == 'closed'", jobs["remove-preview"]["if"])
        self.assertNotIn("needs", jobs["remove-preview"])  # tests and images are skipped for closed PRs
        for name in ("deploy-preview", "deploy-staging", "deploy-release"):
            self.assertEqual(jobs[name]["needs"], "images")
        self.assertIn("github.ref == 'refs/heads/main'", jobs["deploy-staging"]["if"])
        self.assertIn("startsWith(github.ref, 'refs/tags/v')", jobs["deploy-release"]["if"])
        self.assertEqual(jobs["deploy-release"]["steps"][0]["with"]["fetch-depth"], 0)
        self.assertIn("git merge-base --is-ancestor \"$COMMIT_SHA\" origin/main", scripts(jobs["deploy-release"])[0])
        prune = jobs["prune-previews"]
        self.assertEqual(prune["needs"], "deploy-staging")
        self.assertIn("always() && !cancelled()", prune["if"])
        self.assertIn("needs.deploy-staging.result == 'success'", prune["if"])
        self.assertIn("github.event_name == 'schedule'", prune["if"])
        configured = yaml.safe_load((REPOSITORY / ".github/actionlint.yaml").read_text())["self-hosted-runner"]["labels"]
        self.assertEqual(sorted(configured), sorted({label for label, _, _ in DEPLOY_JOBS.values()}))

    def test_each_deploy_job_passes_exactly_its_environment_variables(self):
        jobs = workflow()["jobs"]
        for name, (_, github_environment, environment) in DEPLOY_JOBS.items():
            job = jobs[name]
            prefix = PREFIXES[environment]
            with self.subTest(job=name):
                settings = {key: value for key, value in job["env"].items() if key.startswith("DEPLOY_")}
                expected = {f"DEPLOY_{variable}": f"${{{{ {'secrets' if config.VARIABLES[variable][1] else 'vars'}.{prefix}_{variable} }}}}"
                            for variable in config.names(environment)}
                self.assertEqual(settings, expected)
                self.assertEqual(job["env"]["GH_TOKEN"], "${{ secrets.GITHUB_TOKEN }}")
                if name.startswith("deploy-"):
                    self.assertEqual(job["env"]["GH_ACTOR"], "${{ github.actor }}")
                # Exactly the passed names, with plausible values, configure the environment.
                passed = {key: SAMPLES[key[len("DEPLOY_"):]] for key in settings}
                loaded = config.load(environment, {**passed, "GITHUB_REPOSITORY": "DCGM/PeopleGatorApp"})
                self.assertEqual(loaded["environment"], environment)
                self.assertTrue(config.files(environment, loaded))

    def test_deploy_tools_action_installs_only_into_the_job_temporary_directory(self):
        action = yaml.safe_load((REPOSITORY / ".github/actions/deploy-tools/action.yml").read_text())
        script = action["runs"]["steps"][0]["run"]
        self.assertIn('python3 -m venv "$venv"', script)
        self.assertIn("$RUNNER_TEMP", script)
        self.assertIn("/deploy/people-gator-deploy", script)
        self.assertIn('>> "$GITHUB_PATH"', script)
        for forbidden in ("sudo", "--user", "~/.local", "/opt/"):
            self.assertNotIn(forbidden, script)


class DeployStepTests(unittest.TestCase):
    """Deploy steps are executed against a stub executable; every call must parse with the real CLI."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.bin = Path(temporary.name) / "bin"
        self.bin.mkdir()
        self.output = Path(temporary.name) / "invocations"
        stub = self.bin / "people-gator-deploy"
        stub.write_text(f"#!{sys.executable}\nimport json, os, sys\n"
                        "open(os.environ['DEPLOY_TEST_OUTPUT'], 'a').write(json.dumps(sys.argv[1:]) + '\\n')\n")
        stub.chmod(0o755)

    def invocations(self, job, **environment):
        self.output.write_text("")
        for script in scripts(workflow()["jobs"][job]):
            if "people-gator-deploy" not in script:
                continue
            result = subprocess.run(["bash", "-e", "-o", "pipefail", "-c", script], text=True, capture_output=True, timeout=30,
                                    env={"PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}", "DEPLOY_TEST_OUTPUT": str(self.output),
                                         "COMMIT_SHA": SHA, "PR_NUMBER": "123", "HEAD_REF": "issue/122-ci", "RELEASE_TAG": "v1.2.3",
                                         "OPERATION": "update", "BACKUP_RECORD": "", **environment})
            self.assertEqual(result.returncode, 0, result.stderr)
        calls = [json.loads(line) for line in self.output.read_text().splitlines()]
        for call in calls:
            cli.parser().parse_args(call)
        return calls

    def test_preview_jobs_deploy_the_tested_commit_and_keep_deployments_current(self):
        self.assertEqual(self.invocations("deploy-preview"), [
            ["pr", "preflight"], ["pr", "update", "--pr", "123", "--sha", SHA],
            ["deployments", "supersede", "preview", "--ref", "issue/122-ci"]])
        self.assertEqual(self.invocations("remove-preview"), [
            ["pr", "cleanup", "--pr", "123"], ["deployments", "retire", "--ref", "issue/122-ci"]])
        self.assertEqual(self.invocations("prune-previews"), [["pr", "reconcile"], ["deployments", "prune"]])

    def test_staging_retains_data_unless_snapshot_operations_are_explicit(self):
        cases = (
            ({"OPERATION": "update"}, ["staging", "update", "--sha", SHA]),
            ({"OPERATION": "update", "BACKUP_RECORD": "/private/record"}, ["staging", "update", "--sha", SHA]),
            ({"OPERATION": "snapshot-init"}, ["staging", "snapshot-init", "--sha", SHA]),
            ({"OPERATION": "refresh", "BACKUP_RECORD": "/private/record"},
             ["staging", "refresh", "--sha", SHA, "--backup-record", "/private/record"]),
        )
        for environment, expected in cases:
            with self.subTest(environment=environment):
                self.assertEqual(self.invocations("deploy-staging", **environment),
                                 [["staging", "preflight"], expected, ["deployments", "supersede", "staging"]])

    def test_release_delivers_the_tagged_commit(self):
        self.assertEqual(self.invocations("deploy-release"), [
            ["release", "preflight"], ["release", "update", "--tag", "v1.2.3", "--sha", SHA],
            ["deployments", "supersede", "production"]])
        self.assertEqual(self.invocations("deploy-release", BACKUP_RECORD="/private/backup")[1],
                         ["release", "update", "--tag", "v1.2.3", "--sha", SHA, "--backup-record", "/private/backup"])

    def test_backup_roundtrip_imports_the_shared_fixture_without_opt_in(self):
        suite = REPOSITORY / "deploy/backup/tests/test_roundtrip.py"
        result = subprocess.run([sys.executable, "-B", str(suite)], capture_output=True, text=True,
                                env={k: v for k, v in os.environ.items() if k != "BACKUP_TEST_IMAGE"},
                                timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("skipped=", result.stderr)


if __name__ == "__main__":
    unittest.main()
