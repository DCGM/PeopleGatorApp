"""Exercise lifecycle races, rejected inputs, retry behavior and Compose output."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "preview.py"
SPEC = importlib.util.spec_from_file_location("preview_controller", MODULE_PATH)
preview = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preview)
SHA = "a" * 40
IMAGES = {
    component: f"ghcr.io/dcgm/people_gator-{component}@sha256:{'b' * 64}"
    for component in ("frontend", "backend")
}
RUN = {
    "id": 100, "run_attempt": 1, "workflow_id": 5, "conclusion": "success",
    "event": "pull_request", "head_sha": SHA,
    "head_repository": {"full_name": "DCGM/people_gator"},
    "pull_requests": [{"number": 123}],
}


def pull_request(*, state="open", sha=SHA, repository="DCGM/people_gator"):
    return {"number": 123, "state": state, "head": {
        "sha": sha, "repo": {"full_name": repository},
    }}


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.users = self.root / "users.json"
        self.users.write_text("{}")
        self.controller = preview.Controller({
            "repository": "DCGM/people_gator", "state_dir": str(self.root),
            "users_file": str(self.users),
        })
        self.controller.command = Mock(return_value="")
        self.controller.sql = Mock(return_value="")
        self.controller.api = Mock(side_effect=lambda endpoint: (
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

    def test_updates_preserve_password_and_ignore_older_runs(self):
        directory = self.seed_preview()
        self.controller.deploy_pr(123, RUN, IMAGES)
        state = json.loads((directory / "state.json").read_text())
        self.assertEqual(state["password"], "c" * 64)
        self.assertEqual(state["version"], [100, 1])
        self.assertEqual((directory / "compose.env").stat().st_mode & 0o777, 0o600)
        self.assertIn(f"COMMIT_SHA='{SHA}'", (directory / "compose.env").read_text())
        self.controller.command.reset_mock()
        self.controller.deploy_pr(123, {**RUN, "id": 99}, IMAGES)
        self.controller.command.assert_not_called()

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
        self.controller.api.side_effect = None
        self.controller.api.return_value = pull_request(state="closed")
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
        self.assertTrue(all(mount.startswith("/") for mount in config["services"]["backend"]["tmpfs"]))
        for name in ("frontend", "backend", "migrate", "storage-init"):
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
            controller = preview.Controller({"repository": "DCGM/people_gator", "state_dir": root})

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
