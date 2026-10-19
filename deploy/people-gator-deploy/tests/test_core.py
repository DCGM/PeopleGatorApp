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

    def test_shared_holders_coexist_but_exclude_exclusive_and_legacy_controllers(self):
        # A separate process tries a non-blocking lock in the mode a caller would use.
        probe = ("import fcntl, sys; f = open(sys.argv[1], 'a'); "
                 "mode = fcntl.LOCK_SH if sys.argv[2] == 'shared' else fcntl.LOCK_EX\n"
                 "try:\n    fcntl.flock(f, mode | fcntl.LOCK_NB)\nexcept BlockingIOError:\n    sys.exit(3)")
        def attempt(path, mode):
            return subprocess.run([sys.executable, "-c", probe, str(path), mode]).returncode
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "controller.lock"
            with lock(path, shared=True):
                self.assertEqual(attempt(path, "shared"), 0)  # another environment's work proceeds
                self.assertEqual(attempt(path, "exclusive"), 3)  # infra upgrade / legacy controller waits
            with lock(path):
                self.assertEqual(attempt(path, "shared"), 3)
            # A legacy controller holding LOCK_EX on the same inode blocks new shared work.
            legacy = subprocess.Popen([sys.executable, "-c", "import fcntl, sys, time; f = open(sys.argv[1], 'a'); "
                                       "fcntl.flock(f, fcntl.LOCK_EX); print('held', flush=True); time.sleep(30)",
                                       str(path)], stdout=subprocess.PIPE, text=True)
            try:
                self.assertEqual(legacy.stdout.readline().strip(), "held")
                self.assertEqual(attempt(path, "shared"), 3)
            finally:
                legacy.kill()
                legacy.wait()
            self.assertEqual(attempt(path, "shared"), 0)

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
