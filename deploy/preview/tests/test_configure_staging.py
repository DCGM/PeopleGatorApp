"""Operator settings updates preserve host state and keep secrets private."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import configure_staging as updater
import provision_staging as provisioner


STORAGE = {"local": None, "s3": {"endpoint_url": "https://s3.example.test", "region": "test",
    "bucket_name": "staging-fixture", "access_key_id": "private-id", "secret_access_key": "private-sentinel"}}


class ConfigureTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        preview = self.root / "preview"
        preview.mkdir()
        self.private = self.root / "private"
        self.state = self.root / "staging"
        self.config = self.root / "config.json"
        self.original = {"repository": "DCGM/PeopleGatorApp", "state_dir": str(preview),
            "database_network": "existing-private-network", "users_file": "/unchanged/preview/users.json",
            "extra_operator_setting": {"preserved": True}, "staging": {
                "host": "stage.example.test", "state_dir": str(self.state), "private_dir": str(self.private),
                "extra_setting": "preserved", "auth_volume": "legacy-volume"}}
        self.config.write_text(json.dumps(self.original))
        self.input = self.root / "input.json"
        self.input.write_text(json.dumps(STORAGE))
        self.output = io.StringIO()
        output = redirect_stdout(self.output)
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)

    def apply(self, **kwargs):
        updater.configure(self.config, self.input, **kwargs)

    def test_explicit_env_import_maps_only_s3_literals_without_executing_them(self):
        env = self.root / ".env"
        env.write_text("\n".join([
            "AWS_ENDPOINT_URL=https://s3.example.test", "AWS_S3_REGION=test",
            "export AWS_ACCESS_KEY_ID='private-id'", 'AWS_SECRET_ACCESS_KEY="private-sentinel" # private',
            "OPENROUTER_API_KEY=ignored", "POSTGRES_PASSWORD=ignored",
        ]))
        updater.configure(self.config, env_file=env, bucket="staging-fixture")
        self.assertEqual(json.loads((self.private / "storage.json").read_text()), STORAGE)
        self.assertNotIn("private-sentinel", self.output.getvalue())
        for value in ("$(touch marker)", "${AWS_SECRET_ACCESS_KEY}", "`touch marker`", "'unterminated"):
            env.write_text("AWS_SECRET_ACCESS_KEY=" + value)
            with self.subTest(value=value), self.assertRaises(updater.ConfigurationError):
                updater.storage_from_env(env, "staging-fixture")
        self.assertFalse((self.root / "marker").exists())

    def test_env_requires_explicit_complete_settings_and_bucket(self):
        env = self.root / ".env"
        env.write_text("AWS_ACCESS_KEY_ID=private-id\nAWS_ACCESS_KEY_ID=duplicate")
        with self.assertRaisesRegex(updater.ConfigurationError, "Duplicate"):
            updater.storage_from_env(env, "staging-fixture")
        env.write_text("AWS_ACCESS_KEY_ID=private-id")
        with self.assertRaisesRegex(updater.ConfigurationError, "endpoint, region"):
            updater.storage_from_env(env, "staging-fixture")
        with self.assertRaisesRegex(updater.ConfigurationError, "--bucket"):
            updater.configure(self.config, env_file=env)
        self.assertFalse(self.private.exists())

    def test_operator_owned_host_config_fails_before_backups_or_directory_writes(self):
        before = self.config.read_bytes()
        with patch.object(updater.os, "access", return_value=False):
            with self.assertRaisesRegex(updater.ConfigurationError, "operator-owned"):
                self.apply()
        self.assertEqual(self.config.read_bytes(), before)
        self.assertFalse(self.private.exists())
        self.assertFalse(self.state.exists())
        self.assertEqual(list(self.root.glob("*.bak-*")), [])

    def test_complete_operator_owned_host_config_allows_runner_storage_update(self):
        del self.original["staging"]["auth_volume"]
        self.config.write_text(json.dumps(self.original))
        before = self.config.read_bytes()
        with patch.object(updater.os, "access", return_value=False):
            self.apply()
        self.assertEqual(self.config.read_bytes(), before)
        self.assertEqual(list(self.root.glob("config.json.bak-*")), [])
        self.assertEqual(json.loads((self.private / "storage.json").read_text()), STORAGE)

    def test_configured_backup_bucket_cannot_be_used_as_destination(self):
        self.private.mkdir()
        (self.private / "backup-source.json").write_text(json.dumps({
            "endpoint_url": STORAGE["s3"]["endpoint_url"], "bucket": STORAGE["s3"]["bucket_name"]}))
        with self.assertRaisesRegex(updater.ConfigurationError, "separate"):
            self.apply()
        self.assertFalse((self.private / "storage.json").exists())

    def test_preserves_settings_private_inputs_and_state_with_private_backups(self):
        self.private.mkdir()
        self.state.mkdir()
        untouched = {"credential-input.json": b"private accounts", "media-policy.json": b"private policy"}
        for name, data in untouched.items():
            (self.private / name).write_bytes(data)
        old_storage = {**STORAGE, "s3": {**STORAGE["s3"], "secret_access_key": "old-secret"}}
        (self.private / "storage.json").write_text(json.dumps(old_storage))
        active = {"storage": updater.Staging.storage_identity(STORAGE), "generation": "a" * 16, "password": "retained"}
        (self.state / "state.json").write_text(json.dumps(active))
        before = self.config.read_bytes()
        self.apply()
        expected = json.loads(json.dumps(self.original))
        expected["staging"].pop("auth_volume")
        self.assertEqual(json.loads(self.config.read_text()), expected)
        self.assertEqual(json.loads((self.private / "storage.json").read_text()), STORAGE)
        self.assertEqual(json.loads((self.state / "state.json").read_text()), active)
        for name, data in untouched.items():
            self.assertEqual((self.private / name).read_bytes(), data)
        config_backup, = self.root.glob("config.json.bak-*")
        storage_backup, = self.private.glob("storage.json.bak-*")
        self.assertEqual(config_backup.read_bytes(), before)
        self.assertEqual(json.loads(storage_backup.read_text()), old_storage)
        for path in (config_backup, storage_backup, self.config, self.private / "storage.json"):
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.private.stat().st_mode & 0o777, 0o700)
        self.assertIn("operation=deploy", self.output.getvalue())
        self.assertNotIn("private-sentinel", self.output.getvalue())

    def test_dry_run_creates_no_files_directories_or_lock(self):
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.apply(dry_run=True)
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()})
        self.assertFalse(self.private.exists())
        self.assertFalse(self.state.exists())
        self.assertIn("No files changed", self.output.getvalue())

    def test_repeated_update_preserves_bytes_and_does_not_add_backups(self):
        self.apply()
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.apply()
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()})
        self.assertIn("operation=refresh", self.output.getvalue())

    def test_local_or_changed_destination_and_legacy_data_are_rejected(self):
        before = self.config.read_bytes()
        self.state.mkdir()
        active = self.state / "state.json"
        for value in ({"generation": "legacy"}, {"storage": {"bucket_name": "different-bucket"}}):
            active.write_text(json.dumps(value))
            with self.subTest(state=value), self.assertRaises(ValueError):
                self.apply()
            self.assertEqual(self.config.read_bytes(), before)
            self.assertFalse(self.private.exists())
        active.unlink()
        self.input.write_text('{"local":{"root":"/data"},"s3":null}')
        with self.assertRaisesRegex(ValueError, "S3"):
            self.apply()
        self.assertEqual(self.config.read_bytes(), before)

    def test_concurrent_edit_during_prompt_is_preserved(self):
        def changed(_):
            self.config.write_text('{"operator":"concurrent edit"}')
            return STORAGE
        with patch.object(updater, "prompt_storage", side_effect=changed), self.assertRaisesRegex(ValueError, "changed during input"):
            updater.configure(self.config)
        self.assertEqual(json.loads(self.config.read_text()), {"operator": "concurrent edit"})
        self.assertFalse(self.private.exists())

    def test_existing_credentials_are_defaults_and_empty_input_preserves_them(self):
        with patch("builtins.input", return_value=""), patch.object(updater.getpass, "getpass", return_value=""):
            self.assertEqual(updater.prompt_storage(STORAGE), {**STORAGE, "s3": {**STORAGE["s3"], "timeout_seconds": 30}})

    def test_write_failure_restores_host_config(self):
        before = self.config.read_bytes()
        original_write = updater.atomic_write
        def failed(path, content):
            if path == self.private / "storage.json":
                raise OSError("synthetic failure")
            original_write(path, content)
        with patch.object(updater, "atomic_write", side_effect=failed), self.assertRaises(OSError):
            self.apply()
        self.assertEqual(self.config.read_bytes(), before)
        self.assertFalse((self.private / "storage.json").exists())

    def test_pending_activation_is_not_reconfigured(self):
        self.state.mkdir()
        (self.state / "activation.json").write_text("private journal")
        with self.assertRaisesRegex(ValueError, "pending staging activation"):
            self.apply()
        self.assertFalse(self.private.exists())

    def test_cli_does_not_print_private_invalid_json(self):
        self.input.write_text('{"private-sentinel": not-json}')
        result = subprocess.run([sys.executable, str(Path(updater.__file__)), "--config", str(self.config),
                                 "--storage-file", str(self.input)], text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("private-sentinel", result.stdout + result.stderr)
        self.assertFalse(self.private.exists())

    def test_cli_does_not_echo_endpoint_validation_errors_containing_secrets(self):
        malformed = {**STORAGE, "s3": {**STORAGE["s3"], "endpoint_url": "https://private-sentinel＠example.test"}}
        self.input.write_text(json.dumps(malformed))
        result = subprocess.run([sys.executable, str(Path(updater.__file__)), "--config", str(self.config),
                                 "--storage-file", str(self.input)], text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("private-sentinel", result.stdout + result.stderr)
        self.assertFalse(self.private.exists())


class ProvisionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.preview = self.root / "preview"
        self.preview.mkdir(mode=0o700)
        (self.preview / "controller.lock").touch(mode=0o600)
        self.private = self.root / "private"
        self.state = self.root / "state"
        self.config = self.root / "config.json"
        self.original = {"repository": "DCGM/PeopleGatorApp", "state_dir": str(self.preview),
            "private-sentinel": {"password": "preserved-secret"}, "staging": {
                "host": "stage.example.test", "state_dir": str(self.state),
                "private_dir": str(self.private), "operator_setting": "preserved"}}
        self.config.write_text(json.dumps(self.original))
        self.config.chmod(0o644)
        self.output = io.StringIO()
        output = redirect_stdout(self.output)
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)

    def test_provisions_runner_directories_preserves_config_and_reruns(self):
        before = self.config.read_bytes()
        provisioner.provision(self.config)
        for directory in (self.private, self.state):
            self.assertEqual(directory.stat().st_mode & 0o777, 0o700)
            self.assertEqual(directory.stat().st_uid, self.preview.stat().st_uid)
            self.assertEqual(directory.stat().st_gid, self.preview.stat().st_gid)
        self.assertEqual(self.config.read_bytes(), before)
        provisioner.provision(self.config)
        self.assertEqual(list(self.root.glob("config.json.bak-*")), [])
        self.assertNotIn("preserved-secret", self.output.getvalue())

    def test_adds_missing_host_default_with_private_backup_preserves_metadata(self):
        del self.original["staging"]["host"]
        self.config.write_text(json.dumps(self.original))
        before = self.config.read_bytes()
        metadata = self.config.stat()
        provisioner.provision(self.config)
        expected = {**self.original, "staging": {"host": "staging.peoplegator.dev", **self.original["staging"]}}
        self.assertEqual(json.loads(self.config.read_text()), expected)
        self.assertEqual(self.config.stat().st_mode, metadata.st_mode)
        self.assertEqual(self.config.stat().st_uid, metadata.st_uid)
        self.assertEqual(self.config.stat().st_gid, metadata.st_gid)
        backup, = self.root.glob("config.json.bak-*")
        self.assertEqual(backup.read_bytes(), before)
        self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
        self.assertEqual(backup.stat().st_uid, metadata.st_uid)
        provisioner.provision(self.config)
        self.assertEqual(len(list(self.root.glob("config.json.bak-*"))), 1)

    def test_missing_staging_section_dry_run_does_not_write(self):
        del self.original["staging"]
        self.config.write_text(json.dumps(self.original))
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        with patch.object(provisioner, "DEFAULT_STAGING", {"host": "staging.peoplegator.dev",
                "state_dir": str(self.state), "private_dir": str(self.private)}):
            provisioner.provision(self.config, dry_run=True)
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()})
        self.assertFalse(self.private.exists())
        self.assertFalse(self.state.exists())

    def test_rejects_shared_state_and_symlinks_before_writes(self):
        for state in (self.preview, self.private, self.preview / "staging", self.root):
            self.original["staging"]["state_dir"] = str(state)
            self.config.write_text(json.dumps(self.original))
            with self.subTest(state=state), self.assertRaises(provisioner.ProvisionError):
                provisioner.provision(self.config)
            self.assertFalse(self.private.exists())
        link = self.root / "config-link.json"
        link.symlink_to(self.config)
        with self.assertRaises(provisioner.ProvisionError):
            provisioner.provision(link)

    def test_refuses_insecure_directory_and_preserves_config_on_setup_failure(self):
        self.private.mkdir(mode=0o755)
        with self.assertRaisesRegex(provisioner.ProvisionError, "mode 700"):
            provisioner.provision(self.config)
        self.assertFalse(self.state.exists())
        self.private.chmod(0o700)
        with patch.object(provisioner.os, "chown", side_effect=PermissionError):
            # Simulates an administrator setup failure; no host config update.
            with self.assertRaises(PermissionError):
                provisioner.provision(self.config)
        self.assertEqual(json.loads(self.config.read_text()), self.original)

    def test_refuses_pending_activation_and_legacy_storage(self):
        self.state.mkdir(mode=0o700)
        journal = self.state / "activation.json"
        journal.write_text("private activation")
        with self.assertRaisesRegex(provisioner.ProvisionError, "activation"):
            provisioner.provision(self.config)
        journal.unlink()
        self.original["staging"]["auth_volume"] = "old-volume"
        self.config.write_text(json.dumps(self.original))
        with self.assertRaisesRegex(provisioner.ProvisionError, "migration"):
            provisioner.provision(self.config)
        self.assertFalse(self.private.exists())

    def test_cli_requires_sudo_and_never_echoes_malformed_config(self):
        self.config.write_text('{"preserved-secret": invalid}')
        result = subprocess.run([sys.executable, str(Path(provisioner.__file__)), "--config", str(self.config),
                                 "--dry-run"], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("preserved-secret", result.stdout + result.stderr)
        with patch.object(provisioner.os, "geteuid", return_value=1000), patch.object(sys, "argv", ["provision_staging.py"]):
            with self.assertRaises(SystemExit):
                provisioner.main()


if __name__ == "__main__":
    unittest.main()
