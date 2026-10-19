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
                   "runtime_file": str(self.root / "private/runtime.env"), "state_dir": str(self.root / "state/pr/child")}
        with self.assertRaisesRegex(DeployError, "overlaps|outside"):
            config.configure("staging", self.path.parent.parent / "staging/config.json", staging)

    def test_staging_requires_external_runtime_and_validates_only_snapshot_metadata(self):
        path = self.path.parent.parent / "staging/config.json"
        value = {**self.value, "host": "staging.example.invalid", "state_dir": str(self.root / "state/staging"),
                 "infrastructure": {**self.value["infrastructure"], "mode": "external"},
                 "runtime_file": str(self.root / "private/runtime.env")}
        config.configure("staging", path, value)
        self.assertNotIn("storage", config.read("staging", path))
        with self.assertRaisesRegex(DeployError, "managed externally"):
            config.configure("staging", path, {"media_source": {"secret_access_key": "unused-secret"}})
        for changes, field in (({"runtime_file": "relative.env"}, "runtime_file"),
                               ({"snapshot": {"path": "/private/snapshot.dump"}}, "snapshot")):
            with self.subTest(field=field), self.assertRaises(DeployError) as raised:
                config.configure("staging", path, changes)
            self.assertIn(f"; {field}", str(raised.exception))
        snapshot = {"path": "/private/snapshot.dump", "sha256": "a" * 64, "application_revision": "b" * 40}
        config.configure("staging", path, {"snapshot": snapshot})
        self.assertEqual(config.read("staging", path)["snapshot"], snapshot)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertTrue(all(p.stat().st_mode & 0o777 == 0o600 for p in path.parent.glob("config.backup-*.json")))

    def test_external_runtime_configuration_removes_obsolete_staging_sections(self):
        path = self.path.parent.parent / "staging/config.json"
        value = {**self.value, "schema_version": 1, "environment": "staging", "host": "staging.example.invalid",
                 "state_dir": str(self.root / "state/staging"),
                 "infrastructure": {**self.value["infrastructure"], "mode": "external"},
                 "storage": {"secret_access_key": "obsolete-secret"}, "media_source": {"secret_access_key": "obsolete-source"},
                 "accounts": {"users": {}}, "backup_source": {}, "media_transfer": {}}
        write_json(path, value)
        write_json(Path(value["state_dir"]) / "owned.json", {"environment": "staging"})
        write_json(Path(value["state_dir"]) / "state.json", {"generation": "retained"})
        config.configure("staging", path, {"runtime_file": str(self.root / "private/runtime.env")})
        current = config.read("staging", path)
        for field in ("storage", "media_source", "accounts", "backup_source", "media_transfer"):
            self.assertNotIn(field, current)
        # Descriptor backups preserve the previous private input for operator review.
        self.assertIn("obsolete-secret", next(path.parent.glob("config.backup-*.json")).read_text())
        self.assertEqual(json.loads((Path(value["state_dir"]) / "state.json").read_text()), {"generation": "retained"})

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
