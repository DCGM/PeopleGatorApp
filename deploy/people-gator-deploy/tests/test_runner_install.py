"""The runner installer validates its input before touching the host, and the unit matches what it installs."""
import configparser
from pathlib import Path
import subprocess
import unittest

RUNNER = Path(__file__).resolve().parents[2] / "runner"


class RunnerInstallTests(unittest.TestCase):
    def install(self, *args, **env):
        return subprocess.run(["bash", str(RUNNER / "install.sh"), *args], capture_output=True, text=True, timeout=30,
                              env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", **env})

    def test_arguments_are_validated_before_any_host_check(self):
        self.assertIn("usage: install.sh preview,staging|release", self.install().stderr)
        result = self.install("preview,ci")
        self.assertEqual(result.returncode, 1)
        self.assertIn("unknown environment 'ci'", result.stderr)
        result = self.install("release", RUNNER_NAME="bad name")
        self.assertIn("RUNNER_NAME may contain only", result.stderr)

    def test_labels_guard_and_service_match_the_workflow_and_unit(self):
        script = (RUNNER / "install.sh").read_text()
        self.assertIn('labels+="${labels:+,}people-gator-$environment"', script)  # the deploy jobs' runs-on labels
        self.assertIn("sha256sum -c", script)  # the downloaded runner is verified
        self.assertIn('guard=$HOME/.local/libexec/people-gator/job-started.sh', script)  # outside the runner directory
        self.assertIn("ACTIONS_RUNNER_HOOK_JOB_STARTED=$guard", script)
        self.assertIn("PEOPLE_GATOR_RUNNER_ENVIRONMENT=$environments", script)
        self.assertIn("loginctl enable-linger", script)
        unit = configparser.ConfigParser(interpolation=None, strict=False)
        unit.read_string((RUNNER / "github-runner@.service").read_text())
        self.assertEqual(unit["Service"]["WorkingDirectory"], "%h/actions-runner/%i")
        self.assertEqual(unit["Service"]["ExecStart"], "%h/actions-runner/%i/runsvc.sh")
        self.assertEqual(unit["Service"]["KillMode"], "process")
        self.assertEqual(unit["Install"]["WantedBy"], "default.target")  # started by the lingering user manager
        self.assertIn('cp "$dir/bin/runsvc.sh" "$dir/runsvc.sh"', script)


if __name__ == "__main__":
    unittest.main()
