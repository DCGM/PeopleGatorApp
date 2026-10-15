#!/usr/bin/env python3
"""Publish complete preview-controller releases from reviewed main revisions.

The runner owns the release cache; operator settings and persistent state live
elsewhere. Publication validates files before an atomic directory rename and
never changes a shared current pointer, configuration, or running services.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile


BUNDLE_FILES = (
    "preview.py", "compose.pr.yaml", "compose.infrastructure.yaml",
    "otel-collector.yaml", "pgadmin-servers.json",
)
DEFAULT_RELEASES = Path("/var/lib/people-gator-preview-controller/releases")


def git(source: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(source), *args], capture_output=True, timeout=30,
    )
    if result.returncode:
        raise ValueError("Cannot read reviewed controller revision from Git; fetch main and retry")
    return result.stdout


def reviewed_source(source: Path, revision: str) -> None:
    if not re.fullmatch(r"[a-f0-9]{40}", revision):
        raise ValueError("Release revision must be a full Git commit SHA")
    if os.environ.get("GITHUB_ACTIONS") == "true":
        repository = os.environ.get("GITHUB_REPOSITORY", "")
        expected = f"{repository}/.github/workflows/pr-preview.yml@refs/heads/main"
        if (
            not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)
            or os.environ.get("GITHUB_WORKFLOW_REF") != expected
            or os.environ.get("GITHUB_EVENT_NAME") not in {
                "workflow_run", "pull_request_target", "schedule", "workflow_dispatch",
            }
            or os.environ.get("GITHUB_REF") != "refs/heads/main"
            or os.environ.get("GITHUB_WORKFLOW_SHA") != revision
            or git(source, "rev-parse", "HEAD").decode().strip() != revision
        ):
            raise ValueError("Controller releases require the main preview lifecycle workflow revision")
    else:
        # Operators publish from an updated main checkout, including older
        # reviewed revisions when explicitly recovering compatible code.
        if git(source, "symbolic-ref", "--short", "HEAD").decode().strip() != "main":
            raise ValueError("Manual controller publication requires a reviewed main checkout")
        git(source, "merge-base", "--is-ancestor", "HEAD", "refs/remotes/origin/main")
        git(source, "merge-base", "--is-ancestor", revision, "refs/remotes/origin/main")


def validate_bundle(directory: Path) -> None:
    """Parse code and render Compose using synthetic settings, without a daemon."""
    compile((directory / "preview.py").read_bytes(), "preview.py", "exec")
    json.loads((directory / "pgadmin-servers.json").read_text())
    environment = {key: value for key, value in os.environ.items() if not key.startswith("COMPOSE_")}
    environment.update({
        "POSTGRES_ADMIN_PASSWORD": "synthetic-validation-password",
        "PGADMIN_DEFAULT_PASSWORD": "synthetic-validation-password",
        "PGADMIN_DEFAULT_EMAIL": "operator@example.test", "PGADMIN_HOST": "pgadmin.example.test",
        "DATABASE_NETWORK": "preview-validation-db", "WEB_NETWORK": "preview-validation-web",
        "CERTIFICATE_RESOLVER": "tlschallenge", "OTEL_NETWORK": "preview-validation-logging",
        "OTEL_EXPORTER_OTLP_ENDPOINT": "http://collector:4318", "PREVIEW_LOG_PORT": "24224",
        "PR_NUMBER": "123", "PREVIEW_HOST": "pr-123.example.test", "COMMIT_SHA": "0" * 40,
        "FRONTEND_IMAGE": "example.invalid/frontend:validation",
        "BACKEND_IMAGE": "example.invalid/backend:validation", "DB_NAME": "preview_pr_123",
        "DB_USER": "preview_pr_123", "DB_PASSWORD": "0" * 64,
        "USERS_FILE": "/nonexistent/preview-validation-users.json", "CORS_ORIGIN_REGEX": ".*",
    })
    for name, required in (
        ("compose.pr.yaml", {"frontend", "backend", "storage-init", "migrate", "seed"}),
        ("compose.infrastructure.yaml", {"postgres", "otel-collector", "pgadmin"}),
    ):
        result = subprocess.run(
            ["docker", "compose", "--env-file", "/dev/null", "-f", str(directory / name),
             "--profile", "tools", "config", "--format", "json"],
            env=environment, capture_output=True, timeout=30,
        )
        if result.returncode:
            # Never echo Compose output or ambient environment values.
            raise ValueError(f"Release validation failed for {name}; run Compose config with synthetic settings")
        config = json.loads(result.stdout)
        if not required.issubset(config.get("services", {})):
            raise ValueError(f"Release {name} is missing required lifecycle services")


def verify_release(directory: Path, manifest: dict) -> None:
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("Existing controller release is not a regular directory")
    if {path.name for path in directory.iterdir()} != {*BUNDLE_FILES, "release.json"}:
        raise ValueError("Existing controller release contains missing or unexpected files")
    for name in (*BUNDLE_FILES, "release.json"):
        path = directory / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Controller release contains an invalid file: {name}")
    if json.loads((directory / "release.json").read_text()) != manifest:
        raise ValueError("Existing controller release manifest does not match the reviewed revision")
    for name, digest in manifest["files"].items():
        if hashlib.sha256((directory / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Existing controller release is corrupted: {name}; preserve it for operator inspection")


def publish(source: Path, releases: Path, revision: str) -> Path:
    reviewed_source(source, revision)
    if not releases.is_absolute() or releases.is_symlink() or not releases.is_dir():
        raise ValueError(f"Provision the runner-owned private release directory first: {releases}")
    permissions = releases.stat()
    if permissions.st_uid != os.geteuid() or stat.S_IMODE(permissions.st_mode) != 0o700:
        raise ValueError("Controller release directory must belong to the runner account with mode 700")
    # Read committed blobs, not possibly modified/untracked files in a checkout.
    files = {name: git(source, "show", f"{revision}:deploy/preview/{name}") for name in BUNDLE_FILES}
    manifest = {"revision": revision, "files": {
        name: hashlib.sha256(content).hexdigest() for name, content in files.items()
    }}
    destination = releases / revision
    descriptor = os.open(releases / "publish.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if destination.exists() or destination.is_symlink():
            verify_release(destination, manifest)
            validate_bundle(destination)
            return destination
        temporary = Path(tempfile.mkdtemp(prefix=f".staging-{revision}-", dir=releases))
        try:
            for name, content in files.items():
                (temporary / name).write_bytes(content)
            (temporary / "release.json").write_text(json.dumps(manifest, indent=2) + "\n")
            validate_bundle(temporary)
            verify_release(temporary, manifest)
            temporary.rename(destination)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--releases", type=Path, default=DEFAULT_RELEASES)
    args = parser.parse_args()
    try:
        release = publish(Path(__file__).resolve().parents[2], args.releases, args.revision)
    except (OSError, ValueError, SyntaxError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"Controller release publication failed: {error}\n")
    print(f"Validated controller release: {release}")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as output:
            output.write(f"path={release}\n")


if __name__ == "__main__":
    main()
