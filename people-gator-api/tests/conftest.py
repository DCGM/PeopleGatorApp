"""Provide deterministic settings and isolate tests from import-time env changes."""

import json
import os

import pytest


os.environ.setdefault("PEOPLE_GATOR_API__PERSISTENCE", json.dumps({
    "postgres": {
        "host": "localhost", "port": 5432, "user": "test",
        "password": "test", "database": "test",
    },
    "weaviate": None,
}))
os.environ.setdefault("PEOPLE_GATOR_API__STORAGE", json.dumps({
    "local": {"root": "/tmp/people-gator-tests"}, "s3": None,
}))
SETTINGS_ENVIRONMENT = {
    name: value for name, value in os.environ.items()
    if name.startswith("PEOPLE_GATOR_API__")
}

# Initialize settings before older media tests set their legacy environment
# defaults during collection. Each test receives the original environment below.
import people_gator_api.schemas  # noqa: E402, F401


@pytest.fixture(autouse=True)
def isolated_settings_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.startswith("PEOPLE_GATOR_API__"):
            monkeypatch.delenv(name)
    for name, value in SETTINGS_ENVIRONMENT.items():
        monkeypatch.setenv(name, value)
