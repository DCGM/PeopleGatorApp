"""Docker adapter: explicit contexts, disposable registry credentials and owned-worker cleanup."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest
from unittest.mock import patch

from people_gator_deploy.core import DeployError
from people_gator_deploy.docker import Docker

FAKE_DOCKER = textwrap.dedent('''\
    #!/usr/bin/env python3
    import json, os, pathlib, sys, time
    args = sys.argv[1:]
    config = pathlib.Path(os.environ.get('DOCKER_CONFIG', '/nonexistent'))
    stdin = sys.stdin.read() if 'login' in args else ''
    with open(os.environ['DOCKER_TEST_LOG'], 'a') as log:
        log.write(json.dumps({'args': args, 'config': str(config), 'stdin': stdin,
                              'environment': sorted(k for k in os.environ if k.startswith(('DB_', 'AWS_', 'PEOPLE_', 'DOCKER_HOST')))}) + '\\n')
    if os.environ.get('DOCKER_TEST_FAIL') and os.environ['DOCKER_TEST_FAIL'] in ' '.join(args):
        sys.exit(1)
    if args[:1] == ['context']:
        operation = args  # local context store operations select no daemon
    elif args[:2] == ['--context', os.environ['DOCKER_TEST_CONTEXT']]:
        operation = args[2:]
    else:
        sys.exit('missing explicit context')
    if operation[:2] == ['context', 'use']:
        sys.exit('the host-wide active context must never change')
    if operation[:2] == ['context', 'export']:
        pathlib.Path(operation[3]).write_text('synthetic context')
    elif operation[:2] == ['context', 'import']:
        (config / 'imported-context').write_text(operation[2])
    elif operation[:1] == ['login']:
        (config / 'config.json').write_text(json.dumps({'auths': {'ghcr.io': {'auth': 'synthetic-job-login'}}}))
    elif operation[:1] == ['run']:
        time.sleep(float(os.environ.get('DOCKER_TEST_SLEEP', '0')))
    ''')


class DockerAdapterTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "bin").mkdir()
        (self.root / "bin/docker").write_text(FAKE_DOCKER)
        (self.root / "bin/docker").chmod(0o755)
        self.ambient = self.root / "ambient"
        self.ambient.mkdir()
        (self.ambient / "config.json").write_text('{"auths":{"other":{"auth":"retained-login"}}}')
        self.log = self.root / "log"
        self.log.write_text("")

    def environment(self, context, **extra):
        return patch.dict(os.environ, {"PATH": f"{self.root / 'bin'}:{os.environ['PATH']}",
                                       "DOCKER_CONFIG": str(self.ambient), "DOCKER_TEST_LOG": str(self.log),
                                       "DOCKER_TEST_CONTEXT": context, "GH_TOKEN": "synthetic-job-token",
                                       "GH_ACTOR": "synthetic-actor", **extra})

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_registry_credentials_are_disposable_on_success_and_failure(self):
        for context in ("default", "rootless-preview"):
            for failure in ("", "context export", "login ghcr.io", "pull image"):
                if context == "default" and failure.startswith("context"):
                    continue
                self.log.write_text("")
                with self.subTest(context=context, failure=failure), self.environment(context, DOCKER_TEST_FAIL=failure):
                    docker = Docker(context)
                    used = None
                    try:
                        with docker.registry():
                            used = docker.registry_config
                            self.assertIn("synthetic-job-login", (Path(used) / "config.json").read_text())
                            docker.run(["docker", "pull", "image"])
                    except DeployError:
                        self.assertTrue(failure)
                    else:
                        self.assertFalse(failure)
                    calls = self.calls()
                    temporaries = {call["config"] for call in calls if call["config"] != str(self.ambient)}
                    self.assertTrue(all(not Path(path).exists() for path in temporaries))
                    self.assertIsNone(docker.registry_config)
                    self.assertIn("retained-login", (self.ambient / "config.json").read_text())
                    logins = [call for call in calls if call["args"][2:3] == ["login"]]
                    self.assertTrue(all(call["config"] != str(self.ambient) for call in logins))
                    self.assertTrue(all(call["stdin"] == "synthetic-job-token" for call in logins))
                    self.assertTrue(all("synthetic-job-token" not in " ".join(call["args"]) for call in calls))
                    if context != "default" and not failure.startswith("context"):
                        imports = [call for call in calls if call["args"][:2] == ["context", "import"]]
                        self.assertEqual(len(imports), 1)
                        self.assertNotEqual(imports[0]["config"], str(self.ambient))
                    if used is not None:
                        self.assertFalse(Path(used).exists())

    def test_every_command_names_its_context_and_drops_ambient_interpolation(self):
        with self.environment("rootless", DB_PASSWORD="ambient", AWS_SECRET_ACCESS_KEY="ambient",
                              PEOPLE_GATOR_API__STORAGE="ambient", DOCKER_HOST="tcp://ambient:2375"):
            Docker("rootless").run(["docker", "compose", "--project-name", "p", "ps"])
        call = self.calls()[0]
        self.assertEqual(call["args"][:2], ["--context", "rootless"])
        self.assertEqual(call["environment"], [])
        with self.assertRaises(DeployError):
            Docker("")

    def test_cancelled_or_timed_out_runs_remove_their_server_side_container(self):
        with self.environment("rootless", DOCKER_TEST_SLEEP="5"):
            with self.assertRaises(subprocess.TimeoutExpired):
                Docker("rootless").run(["docker", "run", "--rm", "worker-image"], timeout=0.5)
        calls = self.calls()
        started = calls[0]["args"]
        name = started[started.index("--name") + 1]
        self.assertTrue(name.startswith("people-gator-operation-"))
        self.assertEqual(calls[-1]["args"], ["--context", "rootless", "rm", "-f", name])
        # Compose exec does not start a container, so there is nothing extra to remove.
        self.log.write_text("")
        with self.environment("rootless"):
            Docker("rootless").run(["docker", "compose", "exec", "-T", "postgres", "psql"])
        self.assertNotIn("--name", self.calls()[0]["args"])


if __name__ == "__main__":
    unittest.main()
