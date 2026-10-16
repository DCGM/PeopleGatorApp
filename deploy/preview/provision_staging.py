#!/usr/bin/env python3
"""One-time administrator setup for staging; never deploys or accesses data.

Standalone standard-library script: preserves host config ownership and unrelated
settings, and derives the runner identity from existing preview state ownership.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import secrets
import stat
import sys
import tempfile


DEFAULT_STAGING = {"host": "staging.peoplegator.dev", "state_dir": "/var/lib/people-gator-staging",
                   "private_dir": "/opt/people-gator-staging"}


class ProvisionError(ValueError):
    """Fixed messages safe to print without configuration contents."""


def require(condition, message):
    if not condition:
        raise ProvisionError(message)


def regular_path(path: Path, *, directory=False):
    require(path.is_absolute() and path.resolve() == path,
            "Setup paths must be absolute and must not contain symlinks or parent traversals")
    require(path.is_dir() if directory else path.is_file(),
            "Existing host configuration and preview state directory are required")


def replace_config(path: Path, content: bytes, metadata):
    descriptor, name = tempfile.mkstemp(prefix=".staging-config-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
            os.fchown(stream.fileno(), metadata.st_uid, metadata.st_gid)
            os.fchmod(stream.fileno(), stat.S_IMODE(metadata.st_mode))
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def provision(config_path: Path, *, dry_run=False):
    regular_path(config_path)
    original = config_path.read_bytes()
    metadata = config_path.stat()
    config = json.loads(original)
    preview = Path(config["state_dir"])
    regular_path(preview, directory=True)
    runner = preview.stat()
    supplied = config.get("staging", {})
    require(isinstance(supplied, dict), "The existing staging setting must be an object")
    require("auth_volume" not in supplied,
            "Legacy staging storage requires an explicit migration; host settings were not changed")
    staging = {**DEFAULT_STAGING, **supplied}
    directories = [Path(staging[key]) for key in ("state_dir", "private_dir")]
    for directory in directories:
        require(directory.is_absolute() and directory.resolve() == directory,
                "Staging directories must be absolute paths without symlinks or parent traversals")
        require(not directory.is_relative_to(preview) and not preview.is_relative_to(directory),
                "Staging directories must be separate from preview state")
        require(not config_path.is_relative_to(directory),
                "Staging directories must be separate from operator configuration")
        require(directory.parent.is_dir(), "Provision existing parent directories first")
        if directory.exists():
            require(directory.is_dir() and directory.stat().st_uid == runner.st_uid,
                    "Existing staging directories must belong to the preview runner; ownership was not changed")
            require(stat.S_IMODE(directory.stat().st_mode) == 0o700,
                    "Existing staging directories must have mode 700; permissions were not changed")
    require(not directories[0].is_relative_to(directories[1]) and not directories[1].is_relative_to(directories[0]),
            "Private inputs and staging state must be separate directories")
    require(not (directories[0] / "activation.json").exists(),
            "Resolve pending staging activation before provisioning host settings")
    candidate = {**config, "staging": staging}
    lock = preview / "controller.lock"
    # Never create/replace the lock inode while another lifecycle may hold it.
    regular_path(lock)
    lock_metadata = lock.stat()
    require(lock_metadata.st_uid == runner.st_uid, "The existing host lock must belong to the preview runner")
    descriptor = os.open(lock, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "r") as stream:
        fcntl.flock(stream, fcntl.LOCK_SH if dry_run else fcntl.LOCK_EX)
        require(config_path.read_bytes() == original, "Host configuration changed; rerun setup")
        if dry_run:
            print("Host setup validated. Dry run: no files, services or data changed.")
            return
        for directory in directories:
            if not directory.exists():
                directory.mkdir(mode=0o700)
                os.chown(directory, runner.st_uid, runner.st_gid)
        if candidate != config:
            suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(4)
            backup = config_path.with_name(config_path.name + ".bak-" + suffix)
            descriptor = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(original)
                stream.flush()
                os.fsync(stream.fileno())
                os.fchown(stream.fileno(), metadata.st_uid, metadata.st_gid)
            replace_config(config_path, (json.dumps(candidate, indent=2) + "\n").encode(), metadata)
    print("Staging host settings and runner directories are ready; existing host ownership was preserved.")
    print("No services restarted and no database or storage objects changed.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("/opt/people-gator-preview/config.json"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        require(args.dry_run or os.geteuid() == 0, "Run this one-time host setup with sudo; --dry-run needs no sudo")
        provision(args.config, dry_run=args.dry_run)
    except Exception:
        error = sys.exception()
        message = str(error) if isinstance(error, ProvisionError) else "Host setup failed; check configuration, ownership and permissions. Private values were not printed."
        parser.exit(1, message + "\n")


if __name__ == "__main__":
    main()
