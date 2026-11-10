"""One JSON document per environment; the setup page's examples must load as they are."""
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from people_gator_deploy import config
from people_gator_deploy.core import DeployError

SETUP_PAGE = Path(__file__).resolve().parents[3] / "deploy/GITHUB-SETUP.md"
REPOSITORY = {"GITHUB_REPOSITORY": "DCGM/PeopleGatorApp"}


def examples():
    """The JSON documents shown on the setup page, keyed by secret name."""
    text = SETUP_PAGE.read_text()
    result = {}
    for name in config.SECRET_NAMES.values():
        section = text.split(f"## `{name}`", 1)[1]
        result[name] = json.loads(section.split("```json\n", 1)[1].split("```", 1)[0])
    return result


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def load(self, environment, document, **env):
        return config.load(environment, {**REPOSITORY, "DEPLOY_STATE_DIR": str(self.root / environment),
                                         "DEPLOY_CONFIG": json.dumps(document), **env})

    def test_setup_page_examples_load_for_every_environment(self):
        documents = examples()
        for environment, secret in config.SECRET_NAMES.items():
            with self.subTest(secret=secret):
                settings = self.load(environment, documents[secret])
                self.assertEqual(settings["environment"], environment)
                self.assertEqual(settings["postgres"]["host"], "people-gator-postgres")
                self.assertEqual(settings["otel"]["endpoint"], "http://lgtm:4318")
                self.assertEqual(settings["rum"]["client_token"], "RUM_TOKEN")
                files = {path.name: content for path, content, _ in config.files(environment, settings)}
                self.assertIn("PEOPLE_GATOR_API__OTEL__LOGS_ENDPOINT=http://lgtm:4318/v1/logs\n", files["telemetry.env"])
                self.assertIn("PEOPLE_GATOR_API__RUM__CLIENT_TOKEN=RUM_TOKEN\n", files["telemetry.env"])
        preview = self.load("pr", documents["PREVIEW_CONFIG"])
        self.assertEqual(preview["domain"], "preview.peoplegator.dev")
        self.assertEqual(preview["storage"], {"local": {"root": "/data"}})
        self.assertIn("test", preview["users"])  # the repository's demo users by default
        staging = self.load("staging", documents["STAGING_CONFIG"])
        self.assertEqual(staging["backup_source"]["bucket"], "peoplegator-db-backup")
        self.assertEqual(staging["snapshot_source_file"], str(self.root / "staging/snapshot-source.json"))
        production = self.load("release", documents["PRODUCTION_CONFIG"])
        self.assertEqual(production["migration"], production["postgres"])  # one role unless migration_database is given
        self.assertIn("Authorization=Basic", production["otel"]["headers"])

    def test_conventions_are_fixed_and_not_configurable(self):
        settings = self.load("staging", examples()["STAGING_CONFIG"])
        self.assertEqual((settings["web_network"], settings["database_network"], settings["otel_network"]),
                         ("web", "people-gator-db", "logging"))
        self.assertEqual(settings["project"], "people-gator-staging")
        self.assertEqual(settings["postgres_image"], "pgvector/pgvector:pg16")
        with self.assertRaisesRegex(DeployError, "docker_context: unknown field"):
            self.load("staging", {**examples()["STAGING_CONFIG"], "docker_context": "rootless"})
        with patch.dict(os.environ, {"HOME": str(self.root / "home")}):
            implicit = config.load("pr", {**REPOSITORY, "DEPLOY_CONFIG": json.dumps(examples()["PREVIEW_CONFIG"])})
        self.assertEqual(implicit["state_dir"], str(self.root / "home/.local/opt/people-gator-deploy/state/pr"))
        self.assertEqual(implicit["users_file"], str(self.root / "home/.local/opt/people-gator-deploy/state/pr/users.json"))
        # Operators may point at a private file instead of passing the JSON text.
        private = self.root / "preview.json"
        private.write_text(json.dumps(examples()["PREVIEW_CONFIG"]))
        self.assertEqual(config.load("pr", {**REPOSITORY, "DEPLOY_CONFIG_FILE": str(private)})["domain"], "preview.peoplegator.dev")

    def test_missing_or_invalid_documents_name_the_secret_and_field(self):
        with self.assertRaisesRegex(DeployError, "STAGING_CONFIG is missing"):
            config.load("staging", REPOSITORY)
        with self.assertRaisesRegex(DeployError, "PREVIEW_CONFIG: document: is not valid JSON"):
            config.load("pr", {**REPOSITORY, "DEPLOY_CONFIG": "{"})
        with self.assertRaisesRegex(DeployError, "GITHUB_REPOSITORY"):
            config.load("pr", {"DEPLOY_CONFIG": json.dumps(examples()["PREVIEW_CONFIG"])})
        base = examples()["STAGING_CONFIG"]
        cases = (
            ({**base, "host": "Staging.Example"}, "host: must be a lowercase hostname"),
            ({**base, "database": "mysql://a:b@c/d"}, "database: must be postgresql://"),
            ({**base, "database": "postgresql://user@host/db"}, "database: must be postgresql://"),
            ({**base, "database": "postgresql://user:pw@host:notaport/db"}, "database: invalid port"),
            ({k: v for k, v in base.items() if k != "storage"}, "storage: is required"),
            ({**base, "storage": {"local": {"root": "relative"}}}, "storage.local"),
            ({**base, "storage": {"s3": {"bucket_name": "b"}}}, "storage.s3: needs region"),
            ({**base, "storage": {"local": {"root": "/data"}, "s3": None}}, "storage: must be"),
            ({**base, "otel": {"endpoint": "lgtm:4318/v1/logs"}}, "otel.endpoint"),
            ({**base, "otel": {"endpoint": "http://lgtm:4318", "exporter": "x"}}, "otel: must be"),
            ({**base, "rum": {"site": "x"}}, "rum: must be"),
            ({**base, "rum": {"client_token": "t", "session_sample_rate": 150}}, "rum.session_sample_rate"),
            ({**base, "backup_source": {"bucket": "b"}}, "backup_source: needs exactly"),
            ({**base, "extra_env": {"PEOPLE_GATOR_API__STORAGE": "x"}}, "extra_env.PEOPLE_GATOR_API__STORAGE"),
            ({**base, "extra_env": {"AWS_SECRET": "x"}}, "extra_env.AWS_SECRET"),
            ({**base, "extra_env": {"PEOPLE_GATOR_API__OPENROUTER__API_KEY": "two\nlines"}}, "extra_env.PEOPLE_GATOR_API__OPENROUTER__API_KEY"),
            ({**base, "users": {}}, "users: unknown field"),
        )
        for document, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(DeployError, "STAGING_CONFIG: " + re.escape(message)) as raised:
                self.load("staging", document)
            self.assertNotIn("READ_ONLY_SECRET", str(raised.exception))  # never the configured values
            self.assertIn("deploy/GITHUB-SETUP.md", str(raised.exception))
        with self.assertRaisesRegex(DeployError, "PREVIEW_CONFIG: users: must map"):
            self.load("pr", {**examples()["PREVIEW_CONFIG"], "users": {"test": "plain"}})
        with self.assertRaisesRegex(DeployError, "PRODUCTION_CONFIG: migration_database: must be postgresql"):
            self.load("release", {**examples()["PRODUCTION_CONFIG"], "migration_database": "nope"})
        self.assertFalse(self.root.exists() and any(self.root.iterdir()))

    def test_database_urls_are_decoded_into_persistence_settings(self):
        document = {**examples()["PRODUCTION_CONFIG"], "database": "postgres://app%40x:p%3Ass%2Fw@db.internal/people",
                    "migration_database": "postgresql://migrator:m@db.internal:6432/people"}
        settings = self.load("release", document)
        self.assertEqual(settings["postgres"], {"host": "db.internal", "port": 5432, "user": "app@x", "password": "p:ss/w", "database": "people"})
        self.assertEqual(settings["migration"]["port"], 6432)
        files = {path.name: content for path, content, _ in config.files("release", settings)}
        self.assertIn("PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__PASSWORD=p:ss/w\n", files["runtime.env"])
        self.assertIn("PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__USER=migrator\n", files["migration.env"])
        self.assertNotIn("migrator", files["runtime.env"])
        self.assertIn('PEOPLE_GATOR_API__STORAGE={"local": null, "s3": {', files["runtime.env"])
        self.assertIn("PEOPLE_GATOR_API__JWK__ISSUER=https://people.example.org\n", files["runtime.env"])

    def test_rendered_files_have_private_modes_and_are_rewritten_only_on_change(self):
        document = {**examples()["PREVIEW_CONFIG"], "extra_env": {"PEOPLE_GATOR_API__OPENROUTER__API_KEY": "sk-synthetic"}}
        settings = self.load("pr", document)
        files = config.files("pr", settings)
        self.assertEqual({path.name for path, _, _ in files}, {"runtime.env", "telemetry.env", "users.json"})
        config.materialize(files)
        runtime = Path(settings["runtime_file"])
        self.assertEqual(runtime.read_text(), 'PEOPLE_GATOR_API__STORAGE={"local": {"root": "/data"}, "s3": null}\n'
                                              "PEOPLE_GATOR_API__OPENROUTER__API_KEY=sk-synthetic\n")
        self.assertEqual(runtime.stat().st_mode & 0o777, 0o600)
        # The unprivileged backend container reads the users file through a bind mount.
        users = Path(settings["users_file"])
        self.assertEqual(users.stat().st_mode & 0o777, 0o644)
        self.assertEqual(json.loads(users.read_text())["test"]["scopes"][0], "people-gator:browse")
        before = runtime.stat().st_mtime_ns
        config.materialize(files)
        self.assertEqual(runtime.stat().st_mtime_ns, before)
        runtime.chmod(0o644)
        config.materialize(files)
        self.assertEqual(runtime.stat().st_mode & 0o777, 0o600)
        without_telemetry = self.load("pr", {k: v for k, v in document.items() if k not in {"otel", "rum"}})
        self.assertNotIn("telemetry_file", without_telemetry)
        self.assertEqual({path.name for path, _, _ in config.files("pr", without_telemetry)}, {"runtime.env", "users.json"})
        self.assertTrue(config.SECRET_FILES >= {"users.json", "runtime.env", "migration.env", "telemetry.env", "snapshot-source.json"})

    def test_bundled_demo_users_match_the_repository_example(self):
        example = Path(__file__).resolve().parents[3] / "people-gator-api/example.users.json"
        self.assertEqual(json.loads(config.EXAMPLE_USERS.read_text()), json.loads(example.read_text()))


if __name__ == "__main__":
    unittest.main()
