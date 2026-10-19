import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from people_gator_deploy import config
from people_gator_deploy.installer import layout
from people_gator_deploy.core import DeployError, write_json


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path = self.root / "environments/pr/config.json"
        self.value = {"repository": "DCGM/PeopleGatorApp", "state_dir": str(self.root / "state/pr"),
                      "docker_context": "rootless", "domain": "preview.example.invalid", "web_network": "web",
                      "users_file": str(self.root / "private/users.json"), "database_network": "preview-db",
                      "infrastructure": {"mode": "managed", "project": "people-gator-pr-infra", "state_dir": str(self.root / "state/pr")}}

    def test_create_dry_run_edit_backup_and_concurrent_edit(self):
        config.configure("pr", self.path, self.value, dry_run=True)
        self.assertFalse(self.path.parent.exists())
        config.configure("pr", self.path, self.value)
        self.assertEqual(config.read("pr", self.path)["schema_version"], 1)
        before = self.path.read_bytes()
        config.configure("pr", self.path, {"domain": "changed.example.invalid"})
        self.assertEqual(json.loads(before)["users_file"], config.read("pr", self.path)["users_file"])
        self.assertEqual(next(self.path.parent.glob("config.backup-*.json")).read_bytes(), before)
        with self.assertRaisesRegex(DeployError, "concurrently"):
            config.configure("pr", self.path, {}, expected=hashlib.sha256(before).hexdigest())

    def test_precedence_missing_and_redacted_diagnostics(self):
        with patch.dict(os.environ, {"PEOPLE_GATOR_DEPLOY_CONFIG": "/tmp/from-env"}):
            self.assertEqual(config.selected("pr"), Path("/tmp/from-env"))
            self.assertEqual(config.selected("pr", "/tmp/explicit"), Path("/tmp/explicit"))
        with self.assertRaises(DeployError) as caught:
            config.read("pr", self.path)
        self.assertIn(str(self.path), str(caught.exception))
        self.assertIn("pr configure", str(caught.exception))
        config.configure("pr", self.path, self.value)
        with self.assertRaisesRegex(DeployError, "users_file"):
            config.read("pr", self.path, inputs=True)
        self.path.chmod(0o644)
        with self.assertRaisesRegex(DeployError, "mode 600"):
            config.read("pr", self.path)

    def test_schema_migration_and_installed_identity_are_explicit(self):
        config.configure("pr", self.path, self.value)
        value = json.loads(self.path.read_text())
        value["schema_version"] = 0
        write_json(self.path, value)
        with self.assertRaisesRegex(DeployError, "schema_version"):
            config.read("pr", self.path)
        config.migrate("pr", self.path)
        state = Path(self.value["state_dir"])
        write_json(state / "owned.json", {"environment": "pr"})
        with self.assertRaisesRegex(DeployError, "migration"):
            config.configure("pr", self.path, {"state_dir": str(self.root / "another")})
        value["schema_version"] = 99
        write_json(self.path, value)
        with self.assertRaisesRegex(DeployError, "newer"):
            config.migrate("pr", self.path)

    def test_overlapping_environments_rejected(self):
        config.configure("pr", self.path, self.value)
        staging = {**self.value, "environment": "staging", "host": "staging.example.invalid",
                   "storage": {"endpoint_url": "https://s3.example.invalid", "region": "synthetic", "bucket_name": "staging-bucket",
                                  "access_key_id": "synthetic", "secret_access_key": "synthetic"}, "state_dir": str(self.root / "state/pr/child")}
        with self.assertRaisesRegex(DeployError, "overlaps|outside"):
            config.configure("staging", self.path.parent.parent / "staging/config.json", staging)

    def test_single_staging_descriptor_validates_sections_without_echoing_secrets(self):
        path = self.path.parent.parent / "staging/config.json"
        storage = {"endpoint_url": "https://staging.example.invalid", "region": "r", "bucket_name": "staging-bucket",
                   "access_key_id": "id", "secret_access_key": "PRIVATE-DESTINATION-SECRET"}
        source = {"endpoint_url": "https://backup.example.invalid", "region": "r", "bucket": "backups",
                  "access_key_id": "id", "secret_access_key": "PRIVATE-SOURCE-SECRET"}
        value = {**self.value, "host": "staging.example.invalid", "state_dir": str(self.root / "state/staging"),
                 "infrastructure": {**self.value["infrastructure"], "mode": "external"}, "storage": storage}
        config.configure("staging", path, value)  # snapshot sections are optional until snapshot operations
        for changes, field in (({"storage": {**storage, "endpoint_url": "http://insecure.invalid"}}, "storage"),
                               ({"backup_source": {**source, "endpoint_url": "ftp://x"}}, "backup_source"),
                               ({"media_source": {**source, "bucket": "staging-bucket",
                                                  "endpoint_url": storage["endpoint_url"]}}, "media_source"),
                               ({"accounts": {"users": {"staging-viewer": {"hash": "plaintext"}}}}, "accounts")):
            with self.subTest(field=field), self.assertRaises(DeployError) as raised:
                config.configure("staging", path, changes)
            self.assertIn(f"; {field}", str(raised.exception))
            self.assertNotIn("PRIVATE-", str(raised.exception))
        config.configure("staging", path, {"backup_source": source, "media_source": source})
        stored = config.read("staging", path)
        self.assertEqual(stored["backup_source"]["secret_access_key"], "PRIVATE-SOURCE-SECRET")
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertTrue(all(p.stat().st_mode & 0o777 == 0o600 for p in path.parent.glob("config.backup-*.json")))
        write_json(Path(value["state_dir"]) / "owned.json", {"environment": "staging"})
        config.configure("staging", path, {"storage": {"secret_access_key": "rotated"}})  # rotation is allowed
        with self.assertRaisesRegex(DeployError, "resource identity"):
            config.configure("staging", path, {"storage": {"bucket_name": "other-bucket"}})

    def test_example_descriptors_remain_valid_and_default_to_user_scope_paths(self):
        examples = Path(__file__).resolve().parents[1] / "examples"
        scope = layout("user", self.root / "user prefix")
        patcher = patch.object(config, "installation", return_value=scope)
        patcher.start()
        self.addCleanup(patcher.stop)
        staging = json.loads((examples / "staging.json").read_text())
        path = Path(scope["config"]) / "staging/config.json"
        config.configure("staging", path, staging)
        stored = config.read("staging", path)
        self.assertEqual(stored["state_dir"], str(Path(scope["state"]) / "staging"))
        self.assertEqual(stored["infrastructure"], {"mode": "external", "project": "people-gator-preview-infra",
                                                    "state_dir": str(Path(scope["state"]) / "infrastructure")})
        self.assertTrue(Path(stored["state_dir"]).is_relative_to(self.root))
        for name in config.ENVIRONMENTS:
            value = json.loads((examples / f"{name}.json").read_text())
            if name == "release":
                self.assertFalse(value["access_reviewed"])  # operators must confirm it themselves
                value["access_reviewed"] = True
            with self.subTest(environment=name):
                path = self.root / f"examples/{name}/config.json"
                self.assertTrue(config.configure(name, path, value, dry_run=True)["valid"])


if __name__ == "__main__":
    unittest.main()
