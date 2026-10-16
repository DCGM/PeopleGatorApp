"""Exercise controller release publication and workflow credential isolation."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
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


class WorkflowCredentialTests(unittest.TestCase):
    """Execute the registry shell steps with a fake daemon and private config."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.workflow = (MODULE_PATH.parents[2] / ".github/workflows/pr-preview.yml").read_text()
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

    def test_every_event_uses_reviewed_release_before_docker_and_lifecycle(self):
        checkout = self.step("Read trusted preview deployment requirements")
        preflight = self.step("Check preview repository and GitHub access")
        self.assertNotIn("        if:", checkout + preflight)
        self.assertIn("ref: ${{ github.workflow_sha }}", checkout)
        publication = self.step("Publish reviewed preview controller release")
        self.assertNotIn("        if:", publication)
        self.assertIn('release.py --revision "$GITHUB_WORKFLOW_SHA"', publication)
        self.assertIn('python3 "$PREVIEW_CONTROLLER" check-access', preflight)
        self.assertIn("github.workflow_ref == format(", self.workflow)
        self.assertIn("pr-preview.yml@refs/heads/main", self.workflow)
        self.assertNotIn("check_installation.py", self.workflow)
        self.assertNotIn("sudo", self.workflow)
        names = ["Publish reviewed preview controller release", "Select preview controller release",
                 "Check preview repository and GitHub access",
                 "Use temporary registry credentials", "Check deployment Docker daemon",
                 "Log into image registry", "Apply preview lifecycle"]
        positions = [self.workflow.index(f"      - name: {name}\n") for name in names]
        self.assertEqual(positions, sorted(positions))
        lifecycle = self.step("Apply preview lifecycle")
        self.assertEqual(lifecycle.count('python3 "$PREVIEW_CONTROLLER"'), 3)
        self.assertNotIn("/opt/people-gator-preview/preview.py", lifecycle)

    def test_selected_release_handles_every_lifecycle_event(self):
        controller = self.root / "selected-release" / "preview.py"
        controller.parent.mkdir()
        controller.write_text(
            "import json, os, pathlib, sys\n"
            "pathlib.Path(os.environ['CONTROLLER_TEST_OUTPUT']).write_text(json.dumps(sys.argv[1:]))\n"
        )
        env_file, output = self.root / "job-env", self.root / "controller-output"
        environment = {**os.environ, "GITHUB_ENV": str(env_file),
                       "CONTROLLER_RELEASE": str(controller.parent),
                       "CONTROLLER_TEST_OUTPUT": str(output), "RUN_ID": "456", "PR_NUMBER": "123"}
        selection = self.shell(self.script("Select preview controller release"), environment)
        self.assertEqual(selection.returncode, 0, selection.stderr)
        environment["PREVIEW_CONTROLLER"] = env_file.read_text().strip().removeprefix("PREVIEW_CONTROLLER=")
        for event, expected in (
            ("workflow_run", ["deploy", "--run-id", "456"]),
            ("pull_request_target", ["cleanup", "--pr", "123"]),
            ("schedule", ["reconcile"]), ("workflow_dispatch", ["reconcile"]),
        ):
            with self.subTest(event=event):
                result = self.shell(self.script("Apply preview lifecycle"), {**environment, "EVENT_NAME": event})
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(output.read_text()), expected)

    def test_registry_credentials_are_disposable_on_success_and_failures(self):
        for context in ("default", "rootless-preview"):
            for failure in ("", "context export", "context import", "login ghcr.io", "pull image"):
                if context == "default" and failure.startswith("context"):
                    continue
                with self.subTest(context=context, failure=failure):
                    output, env_file, log = [self.root / name for name in ("output", "env", "log")]
                    for path in (output, env_file, log):
                        path.write_text("")
                    environment = {**os.environ, "PATH": f"{self.bin}:{os.environ['PATH']}",
                                   "RUNNER_TEMP": str(self.root), "GITHUB_OUTPUT": str(output),
                                   "GITHUB_ENV": str(env_file), "DOCKER_CONFIG": str(self.ambient),
                                   "GH_TOKEN": "synthetic-job-token", "GH_ACTOR": "synthetic-actor",
                                   "DOCKER_TEST_CONTEXT": context, "DOCKER_TEST_FAIL": failure,
                                   "DOCKER_TEST_LOG": str(log)}
                    result = self.shell(self.script("Use temporary registry credentials"), environment)
                    temporary_config = Path(output.read_text().strip().removeprefix("path="))
                    self.assertEqual(temporary_config.parent, self.root)
                    self.assertTrue(temporary_config.is_dir())
                    try:
                        if not failure.startswith("context"):
                            self.assertEqual(result.returncode, 0, result.stderr)
                            environment["DOCKER_CONFIG"] = env_file.read_text().strip().removeprefix("DOCKER_CONFIG=")
                            self.assertEqual(environment["DOCKER_CONFIG"], str(temporary_config))
                            result = self.shell(self.script("Log into image registry"), environment)
                            if not failure.startswith("login"):
                                self.assertEqual(result.returncode, 0, result.stderr)
                                result = self.shell("docker pull image", environment)
                        self.assertEqual(result.returncode, 1 if failure else 0, result.stderr)
                        self.assertNotIn("synthetic-job-token", result.stdout + result.stderr + log.read_text())
                    finally:
                        cleanup = self.step("Remove temporary registry credentials")
                        self.assertIn("if: always() && steps.registry-config.outputs.path != ''", cleanup)
                        environment["PREVIEW_DOCKER_CONFIG"] = str(temporary_config)
                        result = self.shell(self.script("Remove temporary registry credentials"), environment)
                        self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertFalse(temporary_config.exists())
                    self.assertIn("retained-login", (self.ambient / "config.json").read_text())
                    self.assertEqual(list(self.root.glob("people-gator-preview-docker.*")), [])

    def test_staging_registry_credentials_are_disposable_on_success_and_failures(self):
        self.workflow = (MODULE_PATH.parents[2] / ".github/workflows/staging.yml").read_text()
        self.test_registry_credentials_are_disposable_on_success_and_failures()

    def test_image_matrix_jobs_cannot_remove_each_others_registry_credentials(self):
        self.workflow = (MODULE_PATH.parents[2] / ".github/workflows/pr-ci.yml").read_text()
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
