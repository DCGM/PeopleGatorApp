"""Keep tests from writing to the real GitHub Actions job summary and step outputs.

The utility appends deployment summaries to ``GITHUB_STEP_SUMMARY`` and the
preflight host to ``GITHUB_OUTPUT`` when those files are set; the deploy tests
run inside a CI job where they are, so every synthetic deployment would land in
the job summary.
"""
import os
from unittest.mock import patch


def isolate(testcase):
    environment = patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": "", "GITHUB_OUTPUT": ""})
    environment.start()
    testcase.addCleanup(environment.stop)
