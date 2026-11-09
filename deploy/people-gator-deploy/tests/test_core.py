import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from people_gator_deploy.core import atomic, lock, run, DeployError


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

    def test_exclusive_holders_in_other_processes_block_each_other(self):
        probe = ("import fcntl, sys; f = open(sys.argv[1], 'a')\n"
                 "try:\n    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)\nexcept BlockingIOError:\n    sys.exit(3)")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "environment.lock"
            with lock(path):
                self.assertEqual(subprocess.run([sys.executable, "-c", probe, str(path)]).returncode, 3)
            self.assertEqual(subprocess.run([sys.executable, "-c", probe, str(path)]).returncode, 0)

    def test_failures_hide_subprocess_output(self):
        with self.assertRaises(DeployError) as error:
            run([sys.executable, "-c", "print('private-password'); raise SystemExit(4)"])
        self.assertNotIn("private-password", str(error.exception))


if __name__ == "__main__":
    unittest.main()
