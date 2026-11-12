"""A short list of DEPLOY_* variables per environment; names, kinds and the setup page must agree."""
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from people_gator_deploy import config
from people_gator_deploy.core import DeployError

GITHUB_ENVIRONMENT = {"staging": "staging", "release": "production"}
SETUP_PAGE = Path(__file__).resolve().parents[3] / "deploy/GITHUB-SETUP.md"
REPOSITORY = {"GITHUB_REPOSITORY": "DCGM/PeopleGatorApp"}
PREVIEW = {"HOST": "preview.peoplegator.dev", "DATABASE_URL": "postgresql://postgres:SECRET@postgres:5432/postgres",
           "OTEL_ENDPOINT": "http://lgtm:4318", "RUM_CLIENT_TOKEN": "RUM_TOKEN"}
STAGING = {"HOST": "staging.peoplegator.dev", "DATABASE_URL": "postgresql://postgres:SECRET@postgres:5432/postgres",
           "S3_BUCKET": "peoplegator-staging", "S3_REGION": "us-east-1", "S3_ENDPOINT_URL": "https://s3.example.org",
           "S3_ACCESS_KEY_ID": "KEY", "S3_SECRET_ACCESS_KEY": "SECRET",
           "BACKUP_S3_BUCKET": "peoplegator-db-backup", "BACKUP_S3_PREFIX": "production/db-backups/", "BACKUP_S3_REGION": "us-east-1",
           "BACKUP_S3_ENDPOINT_URL": "https://s3.example.org", "BACKUP_S3_ACCESS_KEY_ID": "READ_ONLY_KEY",
           "BACKUP_S3_SECRET_ACCESS_KEY": "READ_ONLY_SECRET", "OTEL_ENDPOINT": "http://lgtm:4318"}
PRODUCTION = {"HOST": "people.example.org", "DATABASE_URL": "postgresql://people_gator:SECRET@postgres:5432/people_gator",
              "S3_BUCKET": "peoplegator", "S3_REGION": "us-east-1", "S3_ACCESS_KEY_ID": "KEY", "S3_SECRET_ACCESS_KEY": "SECRET",
              "OTEL_ENDPOINT": "http://lgtm:4318", "OTEL_HEADERS": "Authorization=Basic BASE64"}
EXAMPLES = {"pr": PREVIEW, "staging": STAGING, "release": PRODUCTION}


def environment_variables(environment, values):
    return {**REPOSITORY, **{f"DEPLOY_{name}": value for name, value in values.items()}}


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def load(self, environment, values, **env):
        return config.load(environment, {**environment_variables(environment, values), "DEPLOY_STATE_DIR": str(self.root / environment), **env})

    def test_setup_page_lists_every_variable_with_its_kind_and_the_examples_load(self):
        page = SETUP_PAGE.read_text()
        table = page.split("| Name (after the prefix) |", 1)[1].split("\n\n", 1)[0]
        for name, (environments, secret) in config.VARIABLES.items():
            with self.subTest(name=name):
                row = next(line for line in table.splitlines() if f"`{name}`" in line)
                self.assertIn("| secret |" if secret else "| variable |", row)
        for environment, values in EXAMPLES.items():
            prefix = config.GITHUB_PREFIX[environment]
            for name, value in values.items():
                kind = "secret" if config.VARIABLES[name][1] else "variable"
                # Staging/production secrets live in their GitHub environment, out of PR workflows' reach.
                scope = f"--env {GITHUB_ENVIRONMENT[environment]} " if kind == "secret" and environment != "pr" else ""
                self.assertRegex(page, rf"gh {kind} set {prefix}_{name} {scope}--body '?{re.escape(value)}'?\n", f"{prefix}_{name}")
            with self.subTest(environment=environment):
                settings = self.load(environment, values)
                self.assertEqual(settings["environment"], environment)
                self.assertEqual(settings["postgres"]["host"], "postgres")
                self.assertEqual(settings["otel"]["endpoint"], "http://lgtm:4318")
        preview = self.load("pr", PREVIEW)
        self.assertEqual((preview["domain"], preview["storage"], preview["rum"]), ("preview.peoplegator.dev", {"local": {"root": "/data"}}, {"client_token": "RUM_TOKEN"}))
        self.assertIn("test", preview["users"])  # the repository's demo users by default
        staging = self.load("staging", STAGING)
        self.assertEqual(staging["storage"]["s3"]["endpoint_url"], "https://s3.example.org")
        self.assertEqual(staging["backup_source"]["bucket"], "peoplegator-db-backup")
        self.assertEqual(staging["snapshot_source_file"], str(self.root / "staging/snapshot-source.json"))
        self.assertNotIn("rum", staging)
        production = self.load("release", PRODUCTION)
        self.assertEqual(production["migration"], production["postgres"])  # one role unless MIGRATION_DATABASE_URL is given
        self.assertEqual(production["otel"]["headers"], "Authorization=Basic BASE64")
        self.assertNotIn("endpoint_url", production["storage"]["s3"])

    def test_conventions_are_fixed_and_unrelated_settings_are_gone(self):
        settings = self.load("staging", STAGING)
        self.assertEqual((settings["web_network"], settings["database_network"], settings["otel_network"]),
                         ("web", "db", "logging"))
        self.assertEqual((settings["project"], settings["postgres_image"]), ("people-gator-staging", "pgvector/pgvector:pg16"))
        for unrelated in ("DOCKER_CONTEXT", "PROJECT", "WEB_NETWORK", "CERTIFICATE_RESOLVER", "ACCESS_REVIEWED", "RUNTIME_ENV", "TELEMETRY_ENV"):
            self.assertNotIn(unrelated, config.VARIABLES)
        self.assertEqual(config.names("pr")[:2], ["HOST", "DATABASE_URL"])
        self.assertNotIn("USERS_JSON", config.names("staging"))
        with patch.dict(os.environ, {"HOME": str(self.root / "home")}):
            implicit = config.load("pr", environment_variables("pr", PREVIEW))
        self.assertEqual(implicit["state_dir"], str(self.root / "home/.local/opt/people-gator-deploy/state/pr"))
        self.assertEqual(implicit["users_file"], str(self.root / "home/.local/opt/people-gator-deploy/state/pr/users.json"))

    def test_missing_or_invalid_values_name_the_github_variable(self):
        with self.assertRaisesRegex(DeployError, "STAGING_HOST: is required"):
            config.load("staging", REPOSITORY)
        with self.assertRaisesRegex(DeployError, "GITHUB_REPOSITORY"):
            config.load("pr", {f"DEPLOY_{k}": v for k, v in PREVIEW.items()})
        cases = (
            ({**STAGING, "HOST": "Staging.Example"}, "STAGING_HOST: must be a lowercase hostname"),
            ({**STAGING, "DATABASE_URL": ""}, "STAGING_DATABASE_URL: is required"),  # GitHub passes undefined names as empty
            ({**STAGING, "DATABASE_URL": "mysql://a:b@c/d"}, "STAGING_DATABASE_URL: must be postgresql://"),
            ({**STAGING, "DATABASE_URL": "postgresql://user@host/db"}, "STAGING_DATABASE_URL: must be postgresql://"),
            ({**STAGING, "DATABASE_URL": "postgresql://user:pw@host:notaport/db"}, "STAGING_DATABASE_URL: invalid port"),
            ({k: v for k, v in STAGING.items() if not k.startswith("S3_")}, "STAGING_S3_BUCKET: is required"),
            ({k: v for k, v in STAGING.items() if k != "S3_REGION"}, "STAGING_S3_REGION: is required with the other STAGING_S3_"),
            ({**STAGING, "OTEL_ENDPOINT": "lgtm:4318/v1/logs"}, "STAGING_OTEL_ENDPOINT: must be an http"),
            ({**STAGING, "OTEL_ENDPOINT": "", "OTEL_HEADERS": "Authorization=x"}, "STAGING_OTEL_ENDPOINT: is required"),
            ({**STAGING, "RUM_SITE": "o2.example"}, "STAGING_RUM_CLIENT_TOKEN: is required"),
            ({k: v for k, v in STAGING.items() if k != "BACKUP_S3_PREFIX"}, "STAGING_BACKUP_S3_PREFIX: is required with the other STAGING_BACKUP_S3_"),
            ({**STAGING, "BACKUP_S3_PREFIX": "/absolute"}, "STAGING_BACKUP_S3_BUCKET: Backup prefix"),
            ({**STAGING, "HOST": "two\nlines"}, "STAGING_HOST: must be a single-line value"),
        )
        for values, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(DeployError, re.escape(message)) as raised:
                self.load("staging", values)
            self.assertNotIn("READ_ONLY_SECRET", str(raised.exception))  # never the configured values
            self.assertIn("deploy/GITHUB-SETUP.md", str(raised.exception))
        with self.assertRaisesRegex(DeployError, "PREVIEW_USERS_JSON: must map"):
            self.load("pr", {**PREVIEW, "USERS_JSON": json.dumps({"test": "plain"})})
        with self.assertRaisesRegex(DeployError, "PREVIEW_USERS_JSON: is not valid JSON"):
            self.load("pr", {**PREVIEW, "USERS_JSON": "{"})
        with self.assertRaisesRegex(DeployError, "PREVIEW_STORAGE_DIR: cannot be combined"):
            self.load("pr", {**PREVIEW, "STORAGE_DIR": "/media", **{k: v for k, v in STAGING.items() if k.startswith("S3_")}})
        with self.assertRaisesRegex(DeployError, "PREVIEW_STORAGE_DIR: must be an absolute path"):
            self.load("pr", {**PREVIEW, "STORAGE_DIR": "media"})
        with self.assertRaisesRegex(DeployError, "PRODUCTION_MIGRATION_DATABASE_URL: must be postgresql"):
            self.load("release", {**PRODUCTION, "MIGRATION_DATABASE_URL": "nope"})
        self.assertFalse(self.root.exists() and any(self.root.iterdir()))

    def test_database_urls_are_decoded_into_persistence_settings(self):
        values = {**PRODUCTION, "DATABASE_URL": "postgres://app%40x:p%3Ass%2Fw@db.internal/people",
                  "MIGRATION_DATABASE_URL": "postgresql://migrator:m@db.internal:6432/people"}
        settings = self.load("release", values)
        self.assertEqual(settings["postgres"], {"host": "db.internal", "port": 5432, "user": "app@x", "password": "p:ss/w", "database": "people"})
        self.assertEqual(settings["migration"]["port"], 6432)
        files = {path.name: content for path, content, _ in config.files("release", settings)}
        self.assertIn("PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__PASSWORD=p:ss/w\n", files["runtime.env"])
        self.assertIn("PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__USER=migrator\n", files["migration.env"])
        self.assertNotIn("migrator", files["runtime.env"])
        self.assertIn('PEOPLE_GATOR_API__STORAGE={"local": null, "s3": {', files["runtime.env"])
        self.assertIn("PEOPLE_GATOR_API__JWK__ISSUER=https://people.example.org\n", files["runtime.env"])

    def test_rendered_files_have_private_modes_and_are_rewritten_only_on_change(self):
        settings = self.load("pr", {**PREVIEW, "STORAGE_DIR": "/media"})
        files = config.files("pr", settings)
        self.assertEqual({path.name for path, _, _ in files}, {"runtime.env", "telemetry.env", "users.json"})
        config.materialize(files, self.root / "pr")
        runtime = Path(settings["runtime_file"])
        self.assertEqual(runtime.read_text(), 'PEOPLE_GATOR_API__STORAGE={"local": {"root": "/media"}, "s3": null}\n')
        self.assertEqual(runtime.stat().st_mode & 0o777, 0o600)
        # The unprivileged backend container reads the users file through a bind mount.
        users = Path(settings["users_file"])
        self.assertEqual(users.stat().st_mode & 0o777, 0o644)
        self.assertEqual(json.loads(users.read_text())["test"]["scopes"][0], "people-gator:browse")
        before = runtime.stat().st_mtime_ns
        config.materialize(files, self.root / "pr")
        self.assertEqual(runtime.stat().st_mtime_ns, before)
        runtime.chmod(0o644)
        config.materialize(files, self.root / "pr")
        self.assertEqual(runtime.stat().st_mode & 0o777, 0o600)
        without_telemetry = self.load("pr", {k: v for k, v in PREVIEW.items() if not k.startswith(("OTEL_", "RUM_"))})
        self.assertNotIn("telemetry_file", without_telemetry)
        config.materialize(config.files("pr", without_telemetry), self.root / "pr")
        self.assertFalse((self.root / "pr/telemetry.env").exists())  # removed with its setting
        self.assertTrue(config.SECRET_FILES >= {"users.json", "runtime.env", "migration.env", "telemetry.env", "snapshot-source.json"})

    def test_bundled_demo_users_match_the_repository_example(self):
        example = Path(__file__).resolve().parents[3] / "people-gator-api/example.users.json"
        self.assertEqual(json.loads(config.EXAMPLE_USERS.read_text()), json.loads(example.read_text()))


if __name__ == "__main__":
    unittest.main()
