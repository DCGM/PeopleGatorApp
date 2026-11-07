"""Settings come from DEPLOY_* variables; secrets become private files in the state directory."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from people_gator_deploy import config
from people_gator_deploy.core import DeployError


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.env = {"GITHUB_REPOSITORY": "DCGM/PeopleGatorApp", "DEPLOY_DOCKER_CONTEXT": "rootless",
                    "DEPLOY_DOMAIN": "preview.example.invalid", "DEPLOY_HOST": "staging.example.invalid",
                    "DEPLOY_STATE_DIR": str(self.root / "state"),
                    "DEPLOY_INFRASTRUCTURE_STATE_DIR": str(self.root / "infrastructure"),
                    "DEPLOY_USERS_JSON": '{"test": {}}', "DEPLOY_RUNTIME_ENV": "PEOPLE_GATOR_API__STORAGE__LOCAL__ROOT=/data",
                    "DEPLOY_MIGRATION_ENV": "PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__USER=migrator\n",
                    "DEPLOY_DATABASE_NETWORK": "production-db", "DEPLOY_ACCESS_REVIEWED": "true"}

    def test_missing_required_variables_name_the_variable_without_side_effects(self):
        cases = (("pr", "DEPLOY_DOMAIN"), ("staging", "DEPLOY_HOST"), ("release", "DEPLOY_HOST"),
                 ("pr", "DEPLOY_DOCKER_CONTEXT"), ("release", "DEPLOY_DATABASE_NETWORK"), ("release", "DEPLOY_ACCESS_REVIEWED"))
        for environment, name in cases:
            env = {key: value for key, value in self.env.items() if key != name}
            with self.subTest(environment=environment, name=name), self.assertRaises(DeployError) as raised:
                config.load(environment, env)
            self.assertIn(f"{environment} configuration: {name}", str(raised.exception))
            self.assertIn("GitHub Environment", str(raised.exception))
        env = {key: value for key, value in self.env.items() if key != "GITHUB_REPOSITORY"}
        with self.assertRaisesRegex(DeployError, "DEPLOY_REPOSITORY"):
            config.load("pr", env)
        self.assertEqual(config.load("pr", {**env, "DEPLOY_REPOSITORY": "Fork/Repo"})["repository"], "Fork/Repo")
        with self.assertRaisesRegex(DeployError, "Unknown environment"):
            config.load("production", self.env)
        self.assertFalse((self.root / "state").exists())

    def test_defaults_and_overrides(self):
        settings = config.load("pr", {k: v for k, v in self.env.items() if k != "DEPLOY_DATABASE_NETWORK"})
        self.assertEqual(settings["infrastructure"], {"mode": "managed", "project": "people-gator-preview-infra",
                                                      "state_dir": str(self.root / "infrastructure")})
        self.assertEqual((settings["web_network"], settings["otel_network"], settings["database_network"]),
                         ("web", "logging", "people-gator-preview-db"))
        self.assertEqual(settings["users_file"], str(self.root / "state/users.json"))
        self.assertNotIn("telemetry_file", settings)
        self.assertNotIn("certificate_resolver", settings)
        # Undefined GitHub variables arrive as empty strings and keep their defaults.
        empty = config.load("pr", {**self.env, "DEPLOY_OTEL_NETWORK": "", "DEPLOY_STATE_DIR": "", "DEPLOY_TELEMETRY_ENV": ""})
        self.assertEqual(empty["otel_network"], "logging")
        self.assertNotIn("telemetry_file", empty)
        self.assertEqual(config.load("pr", {**self.env, "DEPLOY_CERTIFICATE_RESOLVER": "letsencrypt"})["certificate_resolver"], "letsencrypt")
        staging = config.load("staging", {**self.env, "DEPLOY_CERTIFICATE_RESOLVER": "none", "DEPLOY_PROJECT": "stage-2",
                                          "DEPLOY_SNAPSHOT_SOURCE": "{}", "DEPLOY_TELEMETRY_ENV": "x"})
        self.assertEqual(staging["infrastructure"]["mode"], "external")
        self.assertEqual((staging["project"], staging["certificate_resolver"]), ("stage-2", ""))
        self.assertEqual(staging["snapshot_source_file"], str(self.root / "state/snapshot-source.json"))
        self.assertEqual(staging["telemetry_file"], str(self.root / "state/telemetry.env"))
        release = config.load("release", self.env)
        self.assertEqual((release["project"], release["backend_memory"], release["database_network"]),
                         ("people-gator-release", "4g", "production-db"))
        self.assertNotIn("infrastructure", release)
        with patch.dict(os.environ, {"HOME": str(self.root / "home")}):
            implicit = config.load("staging", {k: v for k, v in self.env.items() if "STATE_DIR" not in k})
        self.assertEqual(implicit["state_dir"], str(self.root / "home/.local/opt/people-gator-deploy/state/staging"))
        self.assertEqual(implicit["infrastructure"]["state_dir"], str(self.root / "home/.local/opt/people-gator-deploy/state/infrastructure"))

    def test_invalid_values_are_rejected(self):
        cases = {"DEPLOY_DOMAIN": "Preview.Example", "DEPLOY_DOCKER_CONTEXT": "root less", "DEPLOY_STATE_DIR": "relative/state",
                 "DEPLOY_INFRASTRUCTURE_STATE_DIR": str(self.root / "state/infra"), "DEPLOY_PREVIEW_LOG_PORT": "port",
                 "DEPLOY_INFRASTRUCTURE_PROJECT": "Infra", "DEPLOY_PGADMIN_HOST": "pg admin"}
        for name, value in cases.items():
            with self.subTest(name=name), self.assertRaisesRegex(DeployError, name):
                config.load("pr", {**self.env, name: value})
        with self.assertRaisesRegex(DeployError, "DEPLOY_SNAPSHOT"):
            config.load("staging", {**self.env, "DEPLOY_SNAPSHOT": '{"path": "/private/snapshot.dump"}'})
        snapshot = {"path": "/private/snapshot.dump", "sha256": "a" * 64, "application_revision": "b" * 40}
        self.assertEqual(config.load("staging", {**self.env, "DEPLOY_SNAPSHOT": json.dumps(snapshot)})["snapshot"], snapshot)
        with self.assertRaisesRegex(DeployError, "not both"):
            config.load("staging", {**self.env, "DEPLOY_SNAPSHOT": json.dumps(snapshot), "DEPLOY_SNAPSHOT_SOURCE": "{}"})
        with self.assertRaisesRegex(DeployError, "DEPLOY_ACCESS_REVIEWED"):
            config.load("release", {**self.env, "DEPLOY_ACCESS_REVIEWED": "yes"})

    def test_secret_contents_are_validated_before_anything_is_written(self):
        settings = config.load("staging", {**self.env, "DEPLOY_SNAPSHOT_SOURCE": "{}"})
        cases = (
            ({"DEPLOY_RUNTIME_ENV": "PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__DATABASE=external"}, "persistence settings are managed"),
            ({"DEPLOY_RUNTIME_ENV": "export AWS_SECRET_ACCESS_KEY=ambient"}, "only PEOPLE_GATOR_API"),
            ({"DEPLOY_RUNTIME_ENV": "   "}, "missing secret contents"),
            ({"DEPLOY_SNAPSHOT_SOURCE": "{}"}, "DEPLOY_SNAPSHOT_SOURCE"),
        )
        for changes, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(DeployError, message) as raised:
                config.secrets("staging", settings, {**self.env, **changes})
            self.assertNotIn("external", str(raised.exception))
        env = {key: value for key, value in self.env.items() if key != "DEPLOY_RUNTIME_ENV"}
        with self.assertRaisesRegex(DeployError, "DEPLOY_RUNTIME_ENV: missing"):
            config.secrets("staging", config.load("staging", env), env)
        with self.assertRaisesRegex(DeployError, "DEPLOY_USERS_JSON"):
            config.secrets("pr", config.load("pr", self.env), {**self.env, "DEPLOY_USERS_JSON": "[]"})
        self.assertFalse((self.root / "state").exists())

    def test_materialized_files_have_private_modes_and_are_rewritten_only_on_change(self):
        source = {"endpoint_url": "https://s3.example.invalid", "region": "us-east-1", "bucket": "backups",
                  "prefix": "production/db-backups/", "access_key_id": "reader", "secret_access_key": "reader-secret"}
        env = {**self.env, "DEPLOY_SNAPSHOT_SOURCE": json.dumps(source), "DEPLOY_TELEMETRY_ENV": "PEOPLE_GATOR_API__RUM__ENABLED=true"}
        settings = config.load("staging", env)
        files = config.secrets("staging", settings, env)
        self.assertEqual({path.name for path, _, _ in files}, {"runtime.env", "snapshot-source.json", "telemetry.env"})
        config.materialize(files)
        runtime = Path(settings["runtime_file"])
        self.assertEqual(runtime.read_text(), "PEOPLE_GATOR_API__STORAGE__LOCAL__ROOT=/data\n")
        self.assertTrue(all(path.stat().st_mode & 0o777 == 0o600 for path, _, _ in files))
        before = runtime.stat().st_mtime_ns
        config.materialize(files)
        self.assertEqual(runtime.stat().st_mtime_ns, before)
        runtime.chmod(0o644)
        config.materialize(files)
        self.assertEqual(runtime.stat().st_mode & 0o777, 0o600)
        env["DEPLOY_RUNTIME_ENV"] = "PEOPLE_GATOR_API__STORAGE__LOCAL__ROOT=/other\n"
        config.materialize(config.secrets("staging", settings, env))
        self.assertEqual(runtime.read_text(), "PEOPLE_GATOR_API__STORAGE__LOCAL__ROOT=/other\n")
        self.assertTrue(config.private_file(Path(settings["snapshot_source_file"])))
        preview = config.load("pr", self.env)
        config.materialize(config.secrets("pr", preview, self.env))
        users = Path(preview["users_file"])
        # The unprivileged backend container reads the users file through a bind mount.
        self.assertEqual(users.stat().st_mode & 0o777, 0o644)
        self.assertTrue(config.protected_file(users))
        self.assertEqual(json.loads(users.read_text()), {"test": {}})
        self.assertTrue(config.SECRET_FILES >= {"users.json", "runtime.env", "migration.env", "telemetry.env", "snapshot-source.json"})


if __name__ == "__main__":
    unittest.main()
