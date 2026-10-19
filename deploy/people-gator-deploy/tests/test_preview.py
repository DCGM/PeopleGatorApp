"""PR preview lifecycle races, rejected inputs, retry behavior and Compose output.

Carried forward from deploy/preview/tests/test_preview.py onto the package.
"""

import io
from contextlib import redirect_stderr
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
import urllib.error


from people_gator_deploy import host, preview
from people_gator_deploy.core import DeployError
SHA = "a" * 40
IMAGES = {
    component: f"ghcr.io/dcgm/peoplegatorapp-{component}@sha256:{'b' * 64}"
    for component in ("frontend", "backend")
}
RUN = {
    "id": 100, "run_attempt": 1, "workflow_id": 5, "conclusion": "success",
    "event": "pull_request", "head_sha": SHA,
    "head_repository": {"full_name": "DCGM/PeopleGatorApp"},
    "pull_requests": [{"number": 123}],
}


def pull_request(*, state="open", sha=SHA, repository="DCGM/PeopleGatorApp"):
    return {"number": 123, "state": state, "head": {
        "sha": sha, "repo": {"full_name": repository},
    }}


def response(data):
    return io.BytesIO(json.dumps(data).encode())


class GitHubAccessTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.environment = patch.dict(os.environ, {
            "GH_TOKEN": "synthetic_secret_token", "GITHUB_REPOSITORY": "DCGM/PeopleGatorApp",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.config = {"repository": "DCGM/PeopleGatorApp", "state_dir": str(self.root)}
        self.controller = preview.Preview(self.config)
        self.controller.command = Mock()
        self.controller.sql = Mock()

    def error(self, status, *, request_id="ABCD:1234:5678"):
        return urllib.error.HTTPError(
            "https://untrusted.invalid/synthetic_secret_token", status,
            "synthetic_secret_token", {"X-GitHub-Request-Id": request_id},
            io.BytesIO(b'synthetic_secret_token'),
        )

    def test_mismatch_is_rejected_before_creating_state_or_making_requests(self):
        with patch.object(host.urllib.request, "urlopen") as urlopen:
            with self.assertRaisesRegex(ValueError, "does not match GITHUB_REPOSITORY.*operator"):
                preview.Preview({**self.config, "repository": "DCGM/people_gator",
                                    "state_dir": str(self.root / "untouched")})
            self.assertFalse((self.root / "untouched").exists())
            urlopen.assert_not_called()

    def test_case_insensitive_repository_identity_and_authenticated_request(self):
        with patch.object(host.urllib.request, "urlopen", return_value=response(
            {"full_name": "dcgm/peoplegatorapp"}
        )) as urlopen:
            self.controller.check_access()
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.github.com/repos/DCGM/PeopleGatorApp")
        self.assertEqual(request.get_header("Authorization"), "Bearer synthetic_secret_token")
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 30)

    def test_redirected_repository_identity_is_rejected(self):
        with patch.object(host.urllib.request, "urlopen", return_value=response(
            {"full_name": "DCGM/renamed-repo"}
        )), self.assertRaisesRegex(ValueError, "different repository identity"):
            self.controller.check_access()

    def test_missing_and_malformed_tokens_fail_even_with_no_previews(self):
        for token in ("", "bad\ntoken", " token "):
            with self.subTest(token=repr(token)), patch.dict(os.environ, {"GH_TOKEN": token}):
                with patch.object(host.urllib.request, "urlopen") as urlopen:
                    with self.assertRaisesRegex(ValueError, "GH_TOKEN"):
                        self.controller.reconcile()
                    urlopen.assert_not_called()

    def test_empty_reconciliation_still_verifies_repository_access(self):
        with patch.object(host.urllib.request, "urlopen", return_value=response(
            {"full_name": "DCGM/PeopleGatorApp"}
        )) as urlopen:
            self.controller.reconcile()
            urlopen.assert_called_once()

    def test_access_check_does_not_create_state_directory(self):
        state = self.root / "not-created"
        controller = preview.Preview({**self.config, "state_dir": str(state)})
        with patch.object(host.urllib.request, "urlopen", return_value=response(
            {"full_name": "DCGM/PeopleGatorApp"}
        )):
            controller.check_access()
        self.assertFalse(state.exists())

    def test_access_errors_preserve_state_in_every_lifecycle_path(self):
        directory = self.root / "pr-123"
        directory.mkdir()
        (directory / "state.json").write_text('{"password":"retained-password"}')
        (directory / "compose.env").write_text("retained running configuration")
        (directory / "candidate.env").write_text("retained candidate configuration")
        (directory / "media").mkdir()
        (directory / "media" / "example").write_bytes(b"retained media")
        def snapshot():
            return {p.relative_to(self.root): p.read_bytes()
                    for p in self.root.rglob("*") if p.is_file()}
        before = snapshot()
        for status in (401, 403, 404):
            for action in (lambda: self.controller.deploy(100),
                           lambda: self.controller.cleanup(123), self.controller.reconcile):
                # Exercise both repository preflight failure and PR/run access
                # failures after repository access has already succeeded.
                for preflight in (True, False):
                    self.controller._access_checked = False
                    replies = ([] if preflight else [response({"full_name": "DCGM/PeopleGatorApp"})])
                    with self.subTest(status=status, action=action, preflight=preflight):
                        with patch.object(host.urllib.request, "urlopen",
                                          side_effect=[*replies, self.error(status)]) as urlopen:
                            with self.assertRaises(DeployError) as raised:
                                action()
                        message = str(raised.exception)
                        self.assertIn(f"HTTP {status}", message)
                        self.assertIn("GET https://api.github.com/repos/DCGM/PeopleGatorApp", message)
                        self.assertIn("ABCD:1234:5678", message)
                        if not preflight:
                            self.assertRegex(message, r"/(pulls/123|actions/runs/100)")
                        self.assertNotIn("synthetic_secret_token", message)
                        self.assertNotIn("retained-password", message)
                        self.assertEqual(urlopen.call_count, 1 if preflight else 2)
                        self.assertEqual(snapshot(), before)
        self.controller.command.assert_not_called()
        self.controller.sql.assert_not_called()

    def test_transient_errors_retry_but_are_bounded_and_sanitized(self):
        failures = [self.error(502), urllib.error.URLError("synthetic_secret_token"),
                    TimeoutError("synthetic_secret_token")]
        for failure in failures:
            with self.subTest(failure=type(failure).__name__):
                log = io.StringIO()
                with patch.object(host.urllib.request, "urlopen", side_effect=failure) as urlopen, \
                     patch.object(host.time, "sleep") as sleep, redirect_stderr(log):
                    with self.assertRaises(DeployError) as raised:
                        self.controller.api("pulls/123")
                self.assertEqual(urlopen.call_count, 3)
                self.assertEqual([call.args[0] for call in sleep.call_args_list], [1, 2])
                self.assertNotIn("synthetic_secret_token", log.getvalue() + str(raised.exception))

    def test_transient_error_can_recover(self):
        with patch.object(host.urllib.request, "urlopen", side_effect=[
            self.error(503), response(pull_request()),
        ]), patch.object(host.time, "sleep"):
            self.assertEqual(self.controller.api("pulls/123")["state"], "open")

    def test_request_id_cannot_inject_logs_or_expose_token(self):
        for request_id in ("evil\n::warning::injected", "synthetic_secret_token"):
            with patch.object(host.urllib.request, "urlopen", side_effect=self.error(
                404, request_id=request_id,
            )), self.assertRaises(DeployError) as raised:
                self.controller.api("pulls/123")
            self.assertNotIn(request_id, str(raised.exception))

    def test_invalid_json_does_not_expose_response_body(self):
        with patch.object(host.urllib.request, "urlopen", return_value=io.BytesIO(
            b"synthetic_secret_token"
        )), self.assertRaisesRegex(DeployError, "returned invalid JSON") as raised:
            self.controller.api("pulls/123")
        self.assertNotIn("synthetic_secret_token", str(raised.exception))


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.users = self.root / "users.json"
        self.users.write_text("{}")
        self.controller = preview.Preview({
            "repository": "DCGM/PeopleGatorApp", "state_dir": str(self.root),
            "users_file": str(self.users),
        })
        self.controller.command = Mock(return_value="")
        self.controller.sql = Mock(return_value="")
        self.controller.readiness = Mock()
        self.controller.api = Mock(side_effect=lambda endpoint: (
            {"full_name": "DCGM/PeopleGatorApp"} if endpoint == "" else
            RUN if endpoint == "actions/runs/100" else
            {"path": ".github/workflows/pr-ci.yml"} if endpoint == "actions/workflows/5"
            else pull_request()
        ))

    def seed_preview(self):
        directory = self.root / "pr-123"
        directory.mkdir()
        (directory / "state.json").write_text(json.dumps({"password": "c" * 64}))
        (directory / "compose.env").write_text("placeholder")
        return directory

    def test_untrusted_identifiers_are_rejected(self):
        for identifier in ("../123", "123;echo bad", "0", "-1", "1\n", "01"):
            with self.subTest(identifier=identifier), self.assertRaises(ValueError):
                preview.positive_int(identifier)

    def test_forks_closed_and_stale_heads_are_rejected(self):
        for pr in (pull_request(repository="attacker/fork"),
                   pull_request(state="closed"), pull_request(sha="d" * 40)):
            self.controller.api.return_value = pr
            self.controller.api.side_effect = None
            self.assertIsNone(self.controller.current_pr(123, SHA))

    def test_deployment_verifies_workflow_identity(self):
        self.controller.api.side_effect = [RUN, {"path": ".github/workflows/other.yml"}]
        with self.assertRaises(ValueError):
            self.controller.eligible_run(100)
        self.controller.command.assert_not_called()

    def test_stale_run_does_not_pull_images(self):
        self.controller.current_pr = Mock(return_value=None)
        self.controller.deploy(100)
        self.controller.command.assert_not_called()

    def test_image_must_match_tested_commit_and_registry(self):
        inspected = {"Config": {"Labels": {"org.opencontainers.image.revision": "d" * 40}},
                     "RepoDigests": [IMAGES["frontend"]]}
        self.controller.command.side_effect = ["", json.dumps([inspected])]
        with self.assertRaises(ValueError):
            self.controller.image("frontend", RUN)

        inspected["Config"]["Labels"]["org.opencontainers.image.revision"] = SHA
        inspected["RepoDigests"] = ["ghcr.io/attacker/frontend@sha256:" + "b" * 64]
        self.controller.command.side_effect = ["", json.dumps([inspected])]
        with self.assertRaises(ValueError):
            self.controller.image("frontend", RUN)

    def test_deploy_repeats_and_populated_reconciliation_preserve_open_preview(self):
        (self.root / "infrastructure.env").write_text("existing infrastructure credentials")
        directory = self.seed_preview()
        inspected = [{"Config": {"Labels": {"org.opencontainers.image.revision": SHA}},
                      "RepoDigests": [digest]} for digest in IMAGES.values()]
        self.controller.command.side_effect = lambda args, **kwargs: (
            json.dumps([inspected[0 if "frontend" in args[-1] else 1]])
            if args[:3] == ["docker", "image", "inspect"] else ""
        )
        self.controller.deploy(100)
        expected_tags = {f"ghcr.io/dcgm/peoplegatorapp-{component}:run-100-1"
                         for component in ("frontend", "backend")}
        self.assertEqual({call.args[0][-1] for call in self.controller.command.call_args_list
                          if call.args[0][:2] == ["docker", "pull"]}, expected_tags)
        state = (directory / "state.json").read_bytes()
        environment = (directory / "compose.env").read_bytes()
        self.controller.command.reset_mock()
        self.controller.sql.reset_mock()
        self.controller.deploy(100)
        self.controller.reconcile()
        self.assertEqual((directory / "state.json").read_bytes(), state)
        self.assertEqual((directory / "compose.env").read_bytes(), environment)
        self.assertEqual(json.loads(state)["password"], "c" * 64)
        self.assertFalse(any("up" in call.args[0] for call in self.controller.command.call_args_list))
        self.controller.sql.assert_not_called()
        # Reconciliation removes only the closed PR; repeating closure is safe.
        closed = self.root / "pr-124"
        closed.mkdir()
        (closed / "candidate.env").write_text("interrupted deployment")
        self.controller.api.side_effect = lambda endpoint: (
            pull_request(state="closed") if endpoint == "pulls/124" else pull_request()
        )
        self.controller.reconcile()
        self.controller.cleanup(124)
        self.assertFalse(closed.exists())
        self.assertEqual((directory / "state.json").read_bytes(), state)

    def test_updates_preserve_password_and_ignore_older_runs(self):
        directory = self.seed_preview()
        self.controller.deploy_pr(123, RUN, IMAGES)
        state = json.loads((directory / "state.json").read_text())
        self.assertEqual(state["password"], "c" * 64)
        self.assertEqual(state["version"], [100, 1])
        self.assertEqual(state["seeded_version"], [100, 1])
        self.assertEqual((directory / "compose.env").stat().st_mode & 0o777, 0o600)
        self.assertIn(f"COMMIT_SHA='{SHA}'", (directory / "compose.env").read_text())
        self.controller.command.reset_mock()
        self.controller.deploy_pr(123, {**RUN, "id": 99}, IMAGES)
        self.controller.command.assert_not_called()

    def test_same_run_from_old_controller_is_seeded_once_after_upgrade(self):
        directory = self.seed_preview()
        state_file = directory / "state.json"
        state = json.loads(state_file.read_text())
        state.update(version=[100, 1], sha=SHA, images=IMAGES)
        state_file.write_text(json.dumps(state))
        self.controller.deploy_pr(123, RUN, IMAGES)
        commands = [call.args[0] for call in self.controller.command.call_args_list]
        self.assertEqual([command[-1] for command in commands[:3]], ["storage-init", "migrate", "seed"])
        self.assertEqual(json.loads(state_file.read_text())["seeded_version"], [100, 1])
        self.controller.command.reset_mock()
        self.controller.deploy_pr(123, RUN, IMAGES)
        self.controller.command.assert_not_called()

    def test_failed_seed_of_existing_run_does_not_mark_it_seeded(self):
        directory = self.seed_preview()
        state_file = directory / "state.json"
        state = json.loads(state_file.read_text())
        state.update(version=[100, 1], sha=SHA, images=IMAGES)
        state_file.write_text(json.dumps(state))
        self.controller.command.side_effect = ["", "", RuntimeError("seed failed")]
        with self.assertRaisesRegex(RuntimeError, "seed failed"):
            self.controller.deploy_pr(123, RUN, IMAGES)
        self.assertEqual(json.loads(state_file.read_text()), state)
        self.assertEqual((directory / "compose.env").read_text(), "placeholder")
        self.assertFalse(any("up" in call.args[0] for call in self.controller.command.call_args_list))

    def test_seeding_runs_after_migrations_and_before_application_startup(self):
        self.controller.deploy_pr(123, RUN, IMAGES)
        commands = [call.args[0] for call in self.controller.command.call_args_list]
        self.assertEqual([command[-1] for command in commands[:3]], ["storage-init", "migrate", "seed"])
        self.assertIn("up", commands[3])

    def test_seed_failure_preserves_running_configuration_for_retry(self):
        directory = self.seed_preview()
        self.controller.command.side_effect = ["", "", RuntimeError("seed failed")]
        with self.assertRaisesRegex(RuntimeError, "seed failed"):
            self.controller.deploy_pr(123, RUN, IMAGES)
        self.assertEqual((directory / "compose.env").read_text(), "placeholder")
        self.assertNotIn("version", json.loads((directory / "state.json").read_text()))
        self.assertFalse(any("up" in call.args[0] for call in self.controller.command.call_args_list))

    def test_infrastructure_upgrade_and_reruns_preserve_credentials(self):
        env_file = self.root / "infrastructure.env"
        env_file.write_text("POSTGRES_ADMIN_PASSWORD=" + "c" * 64 + "\nDATABASE_NETWORK=people-gator-preview-db\n")
        self.controller.init()
        first = env_file.read_text()
        self.assertIn("POSTGRES_ADMIN_PASSWORD='" + "c" * 64 + "'", first)
        self.assertIn("PGADMIN_DEFAULT_PASSWORD='", first)
        self.assertIn("OTEL_EXPORTER_OTLP_ENDPOINT='http://lgtm:4318'", first)
        self.assertEqual(env_file.stat().st_mode & 0o777, 0o600)
        self.controller.init()
        self.assertEqual(env_file.read_text(), first)

    def test_config_controls_otel_pgadmin_and_preview_log_port(self):
        self.controller.config.update(
            otel_network="observability", otel_http_endpoint="https://otel.example.test",
            preview_log_port=24225, pgadmin_email="operator@example.test",
            pgadmin_host="pgadmin.example.test", certificate_resolver="",
        )
        self.controller.init()
        infrastructure = (self.root / "infrastructure.env").read_text()
        for value in ("OTEL_NETWORK='observability'", "PGADMIN_DEFAULT_EMAIL='operator@example.test'",
                      "PGADMIN_HOST='pgadmin.example.test'", "CERTIFICATE_RESOLVER=''",
                      "OTEL_EXPORTER_OTLP_ENDPOINT='https://otel.example.test'"):
            self.assertIn(value, infrastructure)
        self.assertIn("PREVIEW_LOG_ADDRESS='127.0.0.1:24225'",
                      self.controller.env(123, {"password": "c" * 64}, IMAGES, sha=SHA))

    def test_infrastructure_rejects_dotenv_injection_before_starting(self):
        self.controller.config["pgadmin_email"] = "admin@example.test\nINJECTED=value"
        with self.assertRaises(ValueError):
            self.controller.init()
        self.controller.command.assert_not_called()

    def test_migration_failure_preserves_running_configuration_for_retry(self):
        directory = self.seed_preview()
        self.controller.command.side_effect = ["", RuntimeError("migration failed")]
        with self.assertRaises(RuntimeError):
            self.controller.deploy_pr(123, RUN, IMAGES)
        self.assertEqual((directory / "compose.env").read_text(), "placeholder")
        self.assertNotIn("version", json.loads((directory / "state.json").read_text()))
        self.assertTrue((directory / "candidate.env").exists())

    def test_closure_during_migration_cleans_up_instead_of_starting(self):
        directory = self.seed_preview()
        self.controller.current_pr = Mock(side_effect=[pull_request(), None])
        self.controller.api.side_effect = None
        self.controller.api.return_value = pull_request(state="closed")
        self.controller.deploy_pr(123, RUN, IMAGES)
        self.assertFalse(directory.exists())
        for call in self.controller.command.call_args_list:
            self.assertNotIn("up", call.args[0])
        self.assertIn("DROP DATABASE", self.controller.sql.call_args.args[0])

    def test_reopened_pr_is_not_removed_by_delayed_close(self):
        directory = self.seed_preview()
        self.controller.cleanup(123)
        self.assertTrue(directory.exists())
        self.controller.command.assert_not_called()
        self.controller.sql.assert_not_called()

    def test_failed_cleanup_keeps_state_for_reconciliation(self):
        directory = self.seed_preview()
        self.controller.api.side_effect = lambda endpoint: (
            {"full_name": "DCGM/PeopleGatorApp"} if endpoint == ""
            else pull_request(state="closed")
        )
        self.controller.sql.side_effect = RuntimeError("database unavailable")
        with self.assertRaises(RuntimeError):
            self.controller.cleanup(123)
        self.assertTrue(directory.exists())
        self.controller.sql.side_effect = None
        self.controller.reconcile()
        self.assertFalse(directory.exists())
        self.assertIn("--volumes", self.controller.command.call_args.args[0])

    def test_reconciliation_does_not_infer_closure_from_api_errors(self):
        directory = self.seed_preview()
        self.controller.api.side_effect = OSError("API unavailable")
        with self.assertRaises(OSError):
            self.controller.reconcile()
        self.assertTrue(directory.exists())
        self.controller.command.assert_not_called()

    @unittest.skipUnless(shutil.which("docker"), "Docker Compose not installed")
    def test_compose_resolves_unique_router_names_and_uses_shared_database(self):
        env_file = self.root / "compose.env"
        preview.write_private(env_file, self.controller.env(123, {"password": "c" * 64}, IMAGES))
        # Use the real CLI, not the mocked command executor.
        result = subprocess.run(self.controller.compose(123, env_file,
            "--profile", "tools", "config", "--format", "json"),
            text=True, capture_output=True, check=True)
        config = json.loads(result.stdout)
        self.assertNotIn("postgres", config["services"])
        self.assertNotIn("db", config["services"])
        labels = config["services"]["backend"]["labels"]
        self.assertIn("traefik.http.routers.pg-pr-123-api.rule", labels)
        self.assertIn("pr-123.preview.peoplegator.dev", labels["traefik.http.routers.pg-pr-123-api.rule"])
        self.assertTrue(config["networks"]["database"]["external"])
        self.assertFalse(config["services"]["backend"].get("ports"))
        self.assertEqual(config["services"]["migrate"]["command"], ["migrate"])
        self.assertEqual(config["services"]["seed"]["command"], ["seed"])
        self.assertEqual(config["services"]["seed"]["user"], "10001:10001")
        self.assertEqual(set(config["services"]["seed"]["networks"]), {"database"})
        self.assertTrue(all(mount.startswith("/") for mount in config["services"]["backend"]["tmpfs"]))
        for name in ("frontend", "backend", "migrate", "seed", "storage-init"):
            service = config["services"][name]
            self.assertEqual(service["logging"]["driver"], "fluentd")
            self.assertEqual(service["logging"]["options"]["fluentd-async"], "true")
            self.assertEqual(service["labels"]["people-gator.preview.pr"], "123")
            self.assertIn("com.docker.compose.service", service["logging"]["options"]["labels"])

    @unittest.skipUnless(shutil.which("docker"), "Docker Compose not installed")
    def test_infrastructure_routes_pgadmin_and_keeps_database_private(self):
        self.controller.init()
        result = subprocess.run(self.controller.infra("config", "--format", "json"),
                                text=True, capture_output=True, check=True)
        config = json.loads(result.stdout)
        self.assertFalse(config["services"]["postgres"].get("ports"))
        self.assertNotIn("web", config["services"]["postgres"]["networks"])
        pgadmin = config["services"]["pgadmin"]
        self.assertFalse(pgadmin.get("ports"))
        self.assertEqual(set(pgadmin["networks"]), {"database", "web"})
        self.assertEqual(pgadmin["labels"]["traefik.http.routers.pg-preview-pgadmin.rule"],
                         "Host(`pgadmin-preview.peoplegator.dev`)")
        self.assertEqual(pgadmin["environment"]["PGADMIN_CONFIG_SESSION_COOKIE_SECURE"], "True")
        collector = config["services"]["otel-collector"]
        self.assertEqual(collector["ports"][0]["host_ip"], "127.0.0.1")
        self.assertTrue(config["networks"]["logging"]["external"])
        self.assertFalse(any("docker.sock" in mount.get("source", "") for mount in collector["volumes"]))


@unittest.skipUnless(os.environ.get("PREVIEW_TEST_POSTGRES_CONTAINER"), "requires disposable PostgreSQL container")
class DatabaseIsolationTests(unittest.TestCase):
    def test_two_pr_databases_are_isolated_and_cleanup_is_repeatable(self):
        container = os.environ["PREVIEW_TEST_POSTGRES_CONTAINER"]
        admin = os.environ.get("PREVIEW_TEST_POSTGRES_USER", "ci")
        with tempfile.TemporaryDirectory() as root:
            # The fixture lives in the caller's active context; the adapter never guesses one.
            context = os.environ.get("PREVIEW_TEST_DOCKER_CONTEXT") or subprocess.check_output(
                ["docker", "context", "show"], text=True).strip()
            controller = preview.Preview({"repository": "DCGM/PeopleGatorApp", "state_dir": root,
                                          "docker_context": context})

            def sql(statements, database="postgres"):
                return controller.command([
                    "docker", "exec", "-i", container, "psql", "-X", "-qAt",
                    "-v", "ON_ERROR_STOP=1", "-U", admin, "-d", database,
                ], sql=statements)

            controller.sql = sql
            numbers = (900001, 900002)
            try:
                for number in numbers:
                    controller.provision_database(number, "c" * 64)
                    controller.provision_database(number, "c" * 64)
                permissions = sql("SELECT has_database_privilege('preview_pr_900001', 'preview_pr_900001', 'CONNECT'), has_database_privilege('preview_pr_900001', 'preview_pr_900002', 'CONNECT');")
                self.assertEqual(permissions.strip(), "t|f")
                attributes = sql("SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication FROM pg_roles WHERE rolname='preview_pr_900001';")
                self.assertEqual(attributes.strip(), "f|f|f|f")
                extensions = sql("SELECT extname FROM pg_extension WHERE extname IN ('vector', 'pg_trgm', 'unaccent') ORDER BY extname", "preview_pr_900001")
                self.assertEqual(extensions.split(), ["pg_trgm", "unaccent", "vector"])
                # An actual password-authenticated TCP connection must be denied.
                denied = subprocess.run([
                    "docker", "exec", "-e", "PGPASSWORD=" + "c" * 64, container,
                    "psql", "-h", "127.0.0.1", "-U", "preview_pr_900001", "-d", "preview_pr_900002", "-c", "SELECT 1",
                ], capture_output=True, text=True)
                self.assertNotEqual(denied.returncode, 0)
                self.assertIn("permission denied for database", denied.stderr)
                allowed = subprocess.run([
                    "docker", "exec", "-e", "PGPASSWORD=" + "c" * 64, container,
                    "psql", "-h", "127.0.0.1", "-U", "preview_pr_900001", "-d", "preview_pr_900001", "-v", "ON_ERROR_STOP=1",
                    "-c", "CREATE TABLE isolated_data (id integer); CREATE EXTENSION IF NOT EXISTS vector;",
                ], capture_output=True, text=True)
                self.assertEqual(allowed.returncode, 0, allowed.stderr)
            finally:
                for _ in range(2):
                    for number in numbers:
                        sql(f"DROP DATABASE IF EXISTS preview_pr_{number} WITH (FORCE); DROP ROLE IF EXISTS preview_pr_{number};")


if __name__ == "__main__":
    unittest.main()
