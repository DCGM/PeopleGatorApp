"""A successful CI seed check must not hide an outdated installed deployer."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "check_installation.py"
SPEC = importlib.util.spec_from_file_location("check_installation", MODULE_PATH)
installation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installation)


class InstallationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.expected, self.installed = root / "reviewed", root / "installed"
        self.expected.mkdir()
        self.installed.mkdir()
        for name in installation.DEPLOYMENT_FILES:
            content = (MODULE_PATH.parent / name).read_bytes()
            (self.expected / name).write_bytes(content)
            (self.installed / name).write_bytes(content)

    def test_current_installation_is_accepted_without_touching_private_config(self):
        private = self.installed / "config.json"
        private.write_text("operator-owned configuration")
        installation.check_installation(self.expected, self.installed)
        self.assertEqual(private.read_text(), "operator-owned configuration")

    def test_stale_controller_that_skips_seeding_is_rejected_without_replacing_it(self):
        controller = self.installed / "preview.py"
        old = controller.read_text().replace(
            '        self.command(self.compose(number, candidate, "run", "--rm", "--no-deps", "seed"))\n', ""
        )
        controller.write_text(old)
        with self.assertRaisesRegex(RuntimeError, "preview.py.*skip seeding"):
            installation.check_installation(self.expected, self.installed)
        self.assertEqual(controller.read_text(), old)

    def test_missing_or_stale_seed_service_is_rejected(self):
        compose = self.installed / "compose.pr.yaml"
        compose.write_text(compose.read_text().replace("  seed:\n", "  old-service:\n"))
        with self.assertRaisesRegex(RuntimeError, "compose.pr.yaml"):
            installation.check_installation(self.expected, self.installed)
        compose.unlink()
        with self.assertRaisesRegex(RuntimeError, "compose.pr.yaml"):
            installation.check_installation(self.expected, self.installed)


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

    def test_preflight_runs_for_every_event_before_docker_and_installed_controller(self):
        checkout = self.step("Read trusted preview deployment requirements")
        preflight = self.step("Check preview repository and GitHub access")
        self.assertNotIn("        if:", checkout + preflight)
        self.assertIn("ref: ${{ github.workflow_sha }}", checkout)
        self.assertIn(".preview-workflow/deploy/preview/preview.py check-access", preflight)
        names = ["Check preview repository and GitHub access",
                 "Use temporary registry credentials", "Check deployment Docker daemon",
                 "Log into image registry", "Apply preview lifecycle"]
        positions = [self.workflow.index(f"      - name: {name}\n") for name in names]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("python3 /opt/people-gator-preview/preview.py", self.step("Apply preview lifecycle"))

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


if __name__ == "__main__":
    unittest.main()
