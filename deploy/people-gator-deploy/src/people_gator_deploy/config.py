"""Versioned environment descriptors; configuration never contacts services."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

from . import CONFIG_SCHEMA
from .core import DeployError, atomic, lock, write_json
from .installer import layout

ENVIRONMENTS = ("pr", "staging", "release")


def installation():
    path = Path(sys.prefix) / "installation.json"
    return json.loads(path.read_text()) if path.exists() else layout()


def selected(environment, explicit=None):
    path = Path(explicit or os.environ.get("PEOPLE_GATOR_DEPLOY_CONFIG") or
                Path(installation()["config"]) / environment / "config.json").expanduser()
    if not path.is_absolute():
        raise DeployError("--config / PEOPLE_GATOR_DEPLOY_CONFIG must be an absolute path")
    return path


def problem(environment, path, field, reason):
    return DeployError(f"{environment} configuration: {path}; {field}: {reason}; "
                       f"run people-gator-deploy {environment} configure --config '{path}' --input <private-json>")


def private_file(path: Path):
    return (path.is_file() and not path.is_symlink() and path.stat().st_uid == os.geteuid()
            and stat.S_IMODE(path.stat().st_mode) & 0o077 == 0)


def protected_file(path: Path):
    """Readable by unprivileged containers, but writable only by its trusted owner."""
    return (path.is_file() and not path.is_symlink() and path.stat().st_uid in {0, os.geteuid()}
            and stat.S_IMODE(path.stat().st_mode) & 0o022 == 0)


def validate(value, environment, path, *, inputs=False):
    def require(condition, field, reason):
        if not condition:
            raise problem(environment, path, field, reason)
    require(isinstance(value, dict), "descriptor", "expected a JSON object")
    require(value.get("schema_version") == CONFIG_SCHEMA, "schema_version", "unsupported; run migrate-config for older descriptors or upgrade the utility")
    require(value.get("environment") == environment, "environment", "does not match selected command group")
    require(bool(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", str(value.get("repository", "")))), "repository", "missing or invalid owner/repository")
    def absolute(field, supplied):
        require(isinstance(supplied, str) and Path(supplied).is_absolute() and "\n" not in supplied,
                field, "requires an absolute path")
        require(not any(part == ".." for part in Path(supplied).parts), field, "parent traversal is unsupported")
        require(not Path(supplied).is_symlink(), field, "symlinks are unsupported")
        return Path(supplied).resolve()
    root = absolute("state_dir", value.get("state_dir"))
    require(root != Path("/") and root not in path.parents and not path.is_relative_to(root), "state_dir", "must be separate from descriptor directories")
    require(isinstance(value.get("docker_context"), str) and bool(re.fullmatch(r"[A-Za-z0-9_.-]+", value["docker_context"])), "docker_context", "select an explicit Docker context")
    hostname = value.get("domain" if environment == "pr" else "host", "")
    require(isinstance(hostname, str) and bool(re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)*", hostname)), "domain" if environment == "pr" else "host", "missing or invalid hostname")
    require(value.get("web_network") and isinstance(value["web_network"], str), "web_network", "name an external proxy network")
    if environment != "release":
        infra = value.get("infrastructure", {})
        require(isinstance(infra, dict) and infra.get("mode") in {"managed", "external"}, "infrastructure.mode", "choose managed or external")
        infra_root = absolute("infrastructure.state_dir", infra.get("state_dir"))
        if environment != "pr":
            require(not (infra_root.is_relative_to(root) or root.is_relative_to(infra_root)), "infrastructure.state_dir", "must be outside environment state")
        require(bool(re.fullmatch(r"[a-z0-9][a-z0-9_-]*", str(infra.get("project", "")))), "infrastructure.project", "missing or invalid Compose project")
        require(bool(re.fullmatch(r"[a-zA-Z0-9_.-]+", str(value.get("database_network", "")))), "database_network", "missing or invalid network")
    if environment in {"staging", "release"}:
        require(bool(re.fullmatch(r"[a-z0-9][a-z0-9_-]*", str(value.get("project", "people-gator-" + environment)))),
                "project", "invalid Compose project")
    if environment == "pr":
        users = absolute("users_file", value.get("users_file"))
        if inputs:
            # The backend container (UID 10001) reads this bind mount.
            require(protected_file(users), "users_file",
                    "needs a regular users file owned by this account or root, not group/world writable")
    elif environment == "staging":
        runtime = absolute("runtime_file", value.get("runtime_file"))
        require(not any(field in value for field in ("storage", "backup_source", "media_source", "accounts", "media_transfer")),
                "descriptor", "storage/media/auth are managed externally; configure runtime_file to remove obsolete sections")
        if inputs:
            require(private_file(runtime), "runtime_file", "needs an owned private API environment file")
            from .release import env_keys
            try:
                keys = env_keys(runtime)
            except DeployError as error:
                raise problem(environment, path, "runtime_file", str(error)) from None
            require(not any(key.startswith("PEOPLE_GATOR_API__PERSISTENCE") for key in keys),
                    "runtime_file", "persistence settings are managed by staging; remove them")
        require(not ("snapshot" in value and "snapshot_source_file" in value), "snapshot_source_file",
                "choose automatic snapshot_source_file or legacy snapshot, not both")
        if "snapshot_source_file" in value:
            # Resolve/read backup credentials only for snapshot operations.
            absolute("snapshot_source_file", value["snapshot_source_file"])
        if "snapshot" in value:
            from .staging import validate_snapshot
            try:
                validate_snapshot(value["snapshot"])
            except DeployError as error:
                raise problem(environment, path, "snapshot", str(error)) from None

    else:
        for field in ("runtime_file", "migration_file"):
            ref = absolute(field, value.get(field))
            if inputs:
                require(private_file(ref), field, "needs an owned mode-600 API environment file")
        require(value.get("access_reviewed") is True, "access_reviewed", "confirm the external access boundary and browser demo-login limitation")
        require(value.get("database_network"), "database_network", "name the external PostgreSQL network")
    if inputs:
        repository = os.environ.get("GITHUB_REPOSITORY")
        require(not repository or repository.lower() == value["repository"].lower(), "repository", "differs from the workflow repository")
    return value


def read(environment, path, *, inputs=False):
    if not private_file(path):
        raise problem(environment, path, "descriptor", "missing, symlinked, wrong owner or not mode 600")
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError):
        raise problem(environment, path, "descriptor", "malformed JSON") from None
    return validate(value, environment, path, inputs=inputs)


def merge(original, changes):
    result = copy.deepcopy(original)
    for key, value in changes.items():
        result[key] = merge(result[key], value) if isinstance(result.get(key), dict) and isinstance(value, dict) else value
    return result


def defaults(environment, value):
    """Fill locations from the installation scope, so user scope needs no root-owned paths."""
    state = Path(installation()["state"])
    value.setdefault("schema_version", CONFIG_SCHEMA)
    value.setdefault("environment", environment)
    value.setdefault("state_dir", str(state / environment))
    value.setdefault("web_network", "web")
    if environment != "release":
        value.setdefault("database_network", "people-gator-preview-db")
        infra = value.setdefault("infrastructure", {})
        if isinstance(infra, dict):
            infra.setdefault("mode", "managed" if environment == "pr" else "external")
            infra.setdefault("project", "people-gator-preview-infra")
            infra.setdefault("state_dir", str(state / "infrastructure"))
    return value


def configure(environment, path, changes, *, dry_run=False, expected=None):
    original = path.read_bytes() if path.exists() else None
    if original is not None and not private_file(path):
        raise problem(environment, path, "descriptor", "must belong to this account with mode 600")
    if expected is not None and hashlib.sha256(original or b"").hexdigest() != expected:
        raise problem(environment, path, "descriptor", "changed concurrently; reread and retry")
    try:
        previous = json.loads(original) if original else {}
    except ValueError:
        raise problem(environment, path, "descriptor", "malformed JSON; restore a private backup") from None
    candidate = defaults(environment, merge(previous, changes))
    # Staging no longer owns S3/media/auth. Explicitly supplying its external
    # runtime file also drops obsolete private sections from pre-rollout configs.
    if environment == "staging" and "runtime_file" in changes:
        for field in ("storage", "backup_source", "media_source", "accounts", "media_transfer"):
            candidate.pop(field, None)
    if environment == "staging" and "snapshot_source_file" in changes:
        candidate.pop("snapshot", None)
    validate(candidate, environment, path)
    # Data identities cannot change while an environment is installed.
    if previous and (Path(previous.get("state_dir", "/nonexistent")) / "owned.json").exists():
        fields = ("state_dir", "infrastructure", "database_network", "migration_file",
                  "docker_context", "project")
        # An explicit runtime_file adds the external settings reference to old
        # staging descriptors without moving any retained database resources.
        if environment != "staging" or previous.get("runtime_file") is not None:
            fields += ("runtime_file",)
        if any(candidate.get(field) != previous.get(field) for field in fields):
            raise problem(environment, path, "resource identity", "installed resource identity changes require explicit migration")
    # Detect accidental state overlap among descriptors in this installation.
    for sibling in path.parent.parent.glob("*/config.json"):
        if sibling == path:
            continue
        try:
            other = json.loads(sibling.read_text())
            other_root = Path(other["state_dir"]).resolve()
        except (OSError, ValueError, KeyError):
            continue
        root = Path(candidate["state_dir"]).resolve()
        if root.is_relative_to(other_root) or other_root.is_relative_to(root):
            raise problem(environment, path, "state_dir", f"overlaps environment descriptor {sibling}")
        if candidate.get("host") and candidate.get("host") == other.get("host"):
            raise problem(environment, path, "host", "already used by another environment")
    digest = hashlib.sha256(original or b"").hexdigest()
    if not dry_run:
        with lock(path.with_suffix(".lock")):
            if (path.read_bytes() if path.exists() else None) != original:
                raise problem(environment, path, "descriptor", "changed concurrently; reread and retry")
            if original:
                atomic(path.with_name(f"config.backup-{digest}.json"), original)
            write_json(path, candidate)
    return {"config": str(path), "environment": environment, "dry_run": dry_run, "previous_digest": digest, "valid": True}


def migrate(environment, path, *, dry_run=False):
    if not private_file(path):
        raise problem(environment, path, "descriptor", "needs a private owned descriptor")
    original = path.read_bytes()
    try:
        value = json.loads(original)
    except ValueError:
        raise problem(environment, path, "descriptor", "malformed JSON") from None
    if value.get("schema_version") == 0:
        value["schema_version"] = 1
        value.setdefault("environment", environment)
    elif value.get("schema_version") != 1:
        raise problem(environment, path, "schema_version", "unsupported newer version; upgrade the utility")
    return configure(environment, path, value, dry_run=dry_run, expected=hashlib.sha256(original).hexdigest())
