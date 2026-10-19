import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from people_gator_deploy import config
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
                   "private_dir": str(self.root / "private"), "state_dir": str(self.root / "state/pr/child")}
        with self.assertRaisesRegex(DeployError, "overlaps|outside"):
            config.configure("staging", self.path.parent.parent / "staging/config.json", staging)


if __name__ == "__main__":
    unittest.main()
