"""Real isolated installs from committed sources, including interrupted upgrades."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from people_gator_deploy import installer
from people_gator_deploy.core import DeployError


class InstallationTests(unittest.TestCase):
    def test_install_reuse_upgrade_pinning_and_failed_publication(self):
        with tempfile.TemporaryDirectory(prefix="deploy test ") as directory:
            root = Path(directory)
            source = root / "source"
            package = source / installer.PACKAGE
            shutil.copytree(Path(__file__).resolve().parents[1], package,
                            ignore=shutil.ignore_patterns("build", "*.egg-info", "__pycache__"))
            def git(*args):
                return subprocess.check_output(["git", "-C", str(source), *args], stderr=subprocess.DEVNULL).decode().strip()
            git("init", "-q")
            git("config", "user.name", "Synthetic installer test")
            git("config", "user.email", "test@example.invalid")
            git("add", ".")
            git("commit", "-qm", "First utility")
            first = git("rev-parse", "HEAD")
            prefix = root / "user prefix"
            result = installer.install(source, first, prefix=prefix)
            executable = Path(result["executable"])
            invocation = subprocess.check_output([executable, "--version"], cwd="/tmp")
            self.assertEqual(json.loads(invocation)["revision"], first)
            (Path(result["config"]) / "private.json").write_text("retained")
            original = installer.integrity(executable.parent.parent)
            self.assertTrue(installer.install(source, first, prefix=prefix)["default_activated"])
            self.assertEqual(original, installer.integrity(executable.parent.parent))
            (package / "src/people_gator_deploy/next.txt").write_text("new source")
            git("add", ".")
            git("commit", "-qm", "Next utility")
            second = git("rev-parse", "HEAD")
            with patch.object(installer.venv.EnvBuilder, "create", side_effect=OSError("Interrupted")):
                with self.assertRaises(OSError):
                    installer.install(source, second, prefix=prefix)
            self.assertEqual((prefix / "bin/people-gator-deploy").resolve(), executable)
            updated = installer.install(source, second, prefix=prefix)
            self.assertTrue(updated["default_activated"])
            self.assertEqual(json.loads(subprocess.check_output([executable, "--version"]))["revision"], first)
            self.assertFalse(installer.install(source, first, prefix=prefix)["default_activated"])
            self.assertEqual((prefix / "bin/people-gator-deploy").resolve(), Path(updated["executable"]))
            self.assertEqual((Path(result["config"]) / "private.json").read_text(), "retained")
            self.assertEqual(git("status", "--porcelain"), "")
            (executable.parent.parent / "extra").write_text("corrupt")
            with self.assertRaisesRegex(DeployError, "corrupt"):
                installer.install(source, first, prefix=prefix)

    def test_system_scope_requires_operator_and_unprivileged_run_as(self):
        with patch("os.geteuid", return_value=1000):
            with self.assertRaisesRegex(DeployError, "operator"):
                installer.install(Path("/tmp"), "a" * 40, scope="system", run_as="nobody")


if __name__ == "__main__":
    unittest.main()
