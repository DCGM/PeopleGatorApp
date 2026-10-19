import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from people_gator_deploy.core import atomic, lock, run, DeployError
from people_gator_deploy.installer import integrity, layout, verify


class CoreTests(unittest.TestCase):
    def test_atomic_is_private_and_lock_inode_survives(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            atomic(path / "config.json", "secret")
            self.assertEqual((path / "config.json").stat().st_mode & 0o777, 0o600)
            with lock(path / "controller.lock"):
                inode = (path / "controller.lock").stat().st_ino
            with lock(path / "controller.lock"):
                self.assertEqual(inode, (path / "controller.lock").stat().st_ino)

    def test_failures_hide_subprocess_output(self):
        with self.assertRaises(DeployError) as error:
            run([sys.executable, "-c", "print('private-password'); raise SystemExit(4)"])
        self.assertNotIn("private-password", str(error.exception))

    def test_integrity_detects_extra_corrupt_or_missing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "asset").write_text("reviewed")
            (path / "installation.json").write_text(json.dumps({"config_schema": 1, "state_schema": 1, "files": integrity(path)}))
            verify(path)
            (path / "extra").write_text("unreviewed")
            with self.assertRaisesRegex(DeployError, "corrupt"):
                verify(path)

    def test_user_and_system_layouts_are_disjoint(self):
        self.assertEqual(layout("user", "/tmp/a space")["bin"], "/tmp/a space/bin")
        self.assertEqual(layout("system")["config"], "/etc/people-gator-deploy/environments")


if __name__ == "__main__":
    unittest.main()
