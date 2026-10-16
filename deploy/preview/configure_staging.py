#!/usr/bin/env python3
"""Update private staging S3 settings without deploying or changing stored data.

Run as the deployment runner user from this checkout or a reviewed controller
release. Secrets are prompted privately or read from --storage-file, never argv.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import getpass
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile

from staging import Staging


class ConfigurationError(ValueError):
    """An actionable message which contains no operator-supplied values."""


def existing(path: Path) -> bytes | None:
    if path.is_symlink():
        raise ConfigurationError("Configuration files must be regular files, not symlinks")
    return path.read_bytes() if path.exists() else None


def atomic_write(path: Path, content: bytes):
    descriptor, name = tempfile.mkstemp(prefix="." + path.name + "-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def serialize(value) -> bytes:
    return (json.dumps(value, indent=2) + "\n").encode()


def prompt_storage(previous):
    current = (previous or {}).get("s3") or {}
    result = {}
    for key, label in (("endpoint_url", "S3 HTTPS endpoint"), ("region", "S3 region"),
                       ("bucket_name", "Staging bucket name")):
        default = current.get(key, "")
        result[key] = input(label + (f" [{default}]" if default else "") + ": ").strip() or default
    for key, label in (("access_key_id", "Staging S3 access key ID"), ("secret_access_key", "Staging S3 secret access key")):
        default = current.get(key, "")
        result[key] = getpass.getpass(label + (" [Enter keeps current]" if default else "") + ": ") or default
    result["timeout_seconds"] = current.get("timeout_seconds", 30)
    return {"local": None, "s3": result}


@contextmanager
def host_lock(root: Path, dry_run: bool):
    lock = root / "controller.lock"
    if dry_run and not lock.exists():
        yield  # A dry run must not create the lock or any other file.
        return
    with lock.open("r" if dry_run else "a") as stream:
        fcntl.flock(stream, fcntl.LOCK_SH if dry_run else fcntl.LOCK_EX)
        yield


def configure(config_path: Path, storage_file: Path | None = None, *, dry_run=False):
    original = existing(config_path)
    if original is None:
        raise ConfigurationError("Existing preview host config is required; this script never resets host configuration")
    config = json.loads(original)
    preview_root = Path(config["state_dir"])
    if not preview_root.is_absolute() or not preview_root.is_dir():
        raise ConfigurationError("Provision the absolute runner-owned preview state directory first")
    if preview_root.stat().st_uid != os.geteuid():
        raise ConfigurationError("Run as the deployment runner user who owns the preview state directory")
    candidate = {**config, "staging": {
        "host": "staging.peoplegator.dev", "state_dir": "/var/lib/people-gator-staging",
        "private_dir": "/opt/people-gator-staging", **config.get("staging", {}),
    }}
    candidate["staging"].pop("auth_volume", None)
    controller = Staging(candidate)
    private = Path(controller.settings["private_dir"])
    state = controller.staging_root
    # Do not let a private-file update replace the host config itself.
    storage_path = private / "storage.json"
    if config_path.resolve() == storage_path.resolve():
        raise ConfigurationError("Host config and staging storage settings must be separate files")
    before_storage = existing(storage_path)
    previous = json.loads(before_storage) if before_storage is not None else None
    proposed = json.loads(storage_file.read_bytes()) if storage_file else prompt_storage(previous)
    controller.validate_storage(proposed)
    controller.dotenv({"STAGING_STORAGE": json.dumps(proposed)})
    # Prompts happen outside the host lock; detect concurrent edits before writing.
    with host_lock(preview_root, dry_run):
        if existing(config_path) != original or existing(storage_path) != before_storage:
            raise ConfigurationError("Configuration changed during input; rerun to preserve those edits")
        if (state / "activation.json").exists():
            raise ConfigurationError("Resolve the pending staging activation before updating settings")
        active = existing(state / "state.json")
        if active is not None:
            binding = json.loads(active).get("storage")
            if binding is None:
                raise ConfigurationError("Legacy local staging data requires explicit migration; settings were not changed")
            if binding != controller.storage_identity(proposed):
                raise ConfigurationError("Active staging must retain its S3 endpoint, region and bucket; migrate data before changing them")
        changes = []
        if candidate != config:
            changes.append((config_path, original, serialize(candidate)))
        if proposed != previous:
            changes.append((storage_path, before_storage, serialize(proposed)))
        for directory in (private, state):
            if directory.exists() and (directory.is_symlink() or directory.stat().st_uid != os.geteuid()):
                raise ConfigurationError("Staging directories must be owned by the deployment runner and must not be symlinks")
            if not directory.exists() and not directory.parent.is_dir():
                raise ConfigurationError("Provision runner-owned parents for staging directories first")
        if dry_run:
            print(f"Valid S3 settings; dry run would update {len(changes)} file(s). No files changed.")
            return
        for directory in (private, state):
            directory.mkdir(mode=0o700, exist_ok=True)
            directory.chmod(0o700)
        suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(4)
        # Prepare every private backup before replacing either configuration file.
        for path, before, _ in changes:
            if before is not None:
                backup = path.with_name(path.name + ".bak-" + suffix)
                atomic_write(backup, before)
                print(f"Private backup: {backup}")
        applied = []
        try:
            for path, before, after in changes:
                atomic_write(path, after)
                applied.append((path, before))
        except Exception:
            for path, before in reversed(applied):
                if before is None:
                    path.unlink(missing_ok=True)
                else:
                    atomic_write(path, before)
            raise
        print(f"Staging S3 settings ready: {storage_path}")
        print("No services restarted and no database/bucket objects changed.")
        operation = "deploy" if active is not None else "refresh"
        print(f"After the reviewed change is on main: gh workflow run staging.yml --ref main -f operation={operation}")


def main(argv=None):
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("/opt/people-gator-preview/config.json"))
    parser.add_argument("--storage-file", type=Path, help="Read full S3 settings from a private JSON file instead of prompting")
    parser.add_argument("--dry-run", action="store_true", help="Validate and report changes without writing files")
    args = parser.parse_args(argv)
    configure(args.config, args.storage_file, dry_run=args.dry_run)


if __name__ == "__main__":
    try:
        main()
    except (Exception, KeyboardInterrupt):
        # JSON errors and filesystem paths can contain secrets; never echo them.
        # Our validation messages are fixed and contain no supplied values.
        error = sys.exception()
        message = str(error) if isinstance(error, ConfigurationError) else "Settings update failed; check explicit S3 configuration, private files, ownership and permissions"
        print(message, file=sys.stderr)
        sys.exit(1)
