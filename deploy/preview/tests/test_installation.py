"""A successful CI seed check must not hide an outdated installed deployer."""

import importlib.util
from pathlib import Path
import tempfile
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "check_installation.py"
SPEC = importlib.util.spec_from_file_location("check_installation", MODULE_PATH)
installation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installation)


class InstallationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.expected, self.installed = root / "reviewed", root / "installed"
        self.expected.mkdir()
        self.installed.mkdir()
        for name in installation.DEPLOYMENT_FILES:
            content = (MODULE_PATH.parent / name).read_bytes()
            (self.expected / name).write_bytes(content)
            (self.installed / name).write_bytes(content)

    def test_current_installation_is_accepted_without_touching_private_config(self):
        private = self.installed / "config.json"
        private.write_text("operator-owned configuration")
        installation.check_installation(self.expected, self.installed)
        self.assertEqual(private.read_text(), "operator-owned configuration")

    def test_stale_controller_that_skips_seeding_is_rejected_without_replacing_it(self):
        controller = self.installed / "preview.py"
        old = controller.read_text().replace(
            '        self.command(self.compose(number, candidate, "run", "--rm", "--no-deps", "seed"))\n', ""
        )
        controller.write_text(old)
        with self.assertRaisesRegex(RuntimeError, "preview.py.*skip seeding"):
            installation.check_installation(self.expected, self.installed)
        self.assertEqual(controller.read_text(), old)

    def test_missing_or_stale_seed_service_is_rejected(self):
        compose = self.installed / "compose.pr.yaml"
        compose.write_text(compose.read_text().replace("  seed:\n", "  old-service:\n"))
        with self.assertRaisesRegex(RuntimeError, "compose.pr.yaml"):
            installation.check_installation(self.expected, self.installed)
        compose.unlink()
        with self.assertRaisesRegex(RuntimeError, "compose.pr.yaml"):
            installation.check_installation(self.expected, self.installed)


if __name__ == "__main__":
    unittest.main()
