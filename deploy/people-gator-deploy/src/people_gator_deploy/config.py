"""Environment settings from ``DEPLOY_*`` variables; configuration never contacts services.

Deploy jobs receive the GitHub variables and secrets as process environment
variables. Non-secret settings become the controller configuration directly.
Secret contents (users file, API env files, backup source) are written to
private files in the environment's host state directory before deployment,
because Compose bind mounts and env files must outlive the job. The shared
PostgreSQL/pgAdmin stack is operator-run (deploy/infrastructure) and only
checked here; the backend exports logs, traces and metrics itself over OTLP.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat

from .core import DeployError, atomic

ENVIRONMENTS = ("pr", "staging", "release")
PREFIX = "DEPLOY_"
HOSTNAME = re.compile(r"[a-z0-9]+(?:[.-][a-z0-9]+)*")
NAME = re.compile(r"[A-Za-z0-9_.-]+")
PROJECT = re.compile(r"[a-z0-9][a-z0-9_-]*")
REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
TELEMETRY_KEY = re.compile(r"(?:PEOPLE_GATOR_API__(?:RUM|OTEL)__[A-Z0-9_]+|OTEL_EXPORTER_OTLP(?:_[A-Z0-9_]+)?)")
# Previews and staging own OTel enablement and endpoints (DEPLOY_OTEL_*); the
# Compose environment would silently shadow these keys from the secret.
DEPLOY_OWNED_TELEMETRY = re.compile(r"PEOPLE_GATOR_API__OTEL__(?:ENABLED|[A-Z]+_ENDPOINT)|OTEL_EXPORTER_OTLP(?:_[A-Z]+)?_ENDPOINT")

# Secret variables and the private file each one becomes inside state_dir.
# The users file is read by the unprivileged backend container (UID 10001).
SECRETS = {
    "pr": {"USERS_JSON": ("users_file", "users.json", 0o644),
           "TELEMETRY_ENV": ("telemetry_file", "telemetry.env", 0o600)},
    "staging": {"RUNTIME_ENV": ("runtime_file", "runtime.env", 0o600),
                "SNAPSHOT_SOURCE": ("snapshot_source_file", "snapshot-source.json", 0o600),
                "TELEMETRY_ENV": ("telemetry_file", "telemetry.env", 0o600)},
    "release": {"RUNTIME_ENV": ("runtime_file", "runtime.env", 0o600),
                "MIGRATION_ENV": ("migration_file", "migration.env", 0o600),
                "TELEMETRY_ENV": ("telemetry_file", "telemetry.env", 0o600)},
}
REQUIRED_SECRETS = {"pr": ("USERS_JSON",), "staging": ("RUNTIME_ENV",), "release": ("RUNTIME_ENV", "MIGRATION_ENV")}
SECRET_FILES = {name for environment in SECRETS.values() for _, name, _ in environment.values()}


def default_state_root() -> Path:
    return Path.home() / ".local/opt/people-gator-deploy/state"


def problem(environment, name, reason):
    return DeployError(f"{environment} configuration: {PREFIX}{name}: {reason}; set it as a GitHub Environment "
                       f"variable or secret (or export it for operator commands)")


def private_file(path: Path):
    return (path.is_file() and not path.is_symlink() and path.stat().st_uid == os.geteuid()
            and stat.S_IMODE(path.stat().st_mode) & 0o077 == 0)


def protected_file(path: Path):
    """Readable by unprivileged containers, but writable only by its trusted owner."""
    return (path.is_file() and not path.is_symlink() and path.stat().st_uid in {0, os.geteuid()}
            and stat.S_IMODE(path.stat().st_mode) & 0o022 == 0)


def env_keys(text: str, *, source: str) -> set[str]:
    keys = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, _ = line.partition("=")
        if not separator or not re.fullmatch(r"PEOPLE_GATOR_API__[A-Z0-9_]+", key):
            raise DeployError(f"{source}: only PEOPLE_GATOR_API__* KEY=value lines are supported")
        keys.add(key)
    return keys


def load(environment: str, env=None) -> dict:
    """Validated controller settings for one environment, without reading secret values."""
    env = os.environ if env is None else env
    if environment not in ENVIRONMENTS:
        raise DeployError(f"Unknown environment {environment!r}; choose one of {', '.join(ENVIRONMENTS)}")

    def value(name, default=None):
        # GitHub passes undefined variables as empty strings: empty means unset.
        supplied = env.get(PREFIX + name)
        return supplied if supplied else default

    def require(condition, name, reason):
        if not condition:
            raise problem(environment, name, reason)

    def absolute(name, supplied):
        require(isinstance(supplied, str) and Path(supplied).is_absolute() and "\n" not in supplied, name, "requires an absolute path")
        require(not any(part == ".." for part in Path(supplied).parts), name, "parent traversal is unsupported")
        require(not Path(supplied).is_symlink(), name, "symlinks are unsupported")
        return Path(supplied).resolve()

    repository = value("REPOSITORY") or env.get("GITHUB_REPOSITORY", "")
    require(bool(REPOSITORY.fullmatch(repository)), "REPOSITORY", "missing or invalid owner/repository (GITHUB_REPOSITORY is used when set)")
    context = value("DOCKER_CONTEXT", "")
    require(bool(NAME.fullmatch(context)), "DOCKER_CONTEXT", "select an explicit Docker context")
    root = absolute("STATE_DIR", value("STATE_DIR") or str(default_state_root() / environment))
    require(root != Path("/"), "STATE_DIR", "must not be the filesystem root")
    settings = {"environment": environment, "repository": repository, "docker_context": context,
                "state_dir": str(root), "web_network": value("WEB_NETWORK", "web"),
                "otel_network": value("OTEL_NETWORK", "logging")}
    require(bool(settings["web_network"]) and bool(NAME.fullmatch(settings["web_network"])), "WEB_NETWORK", "name an external proxy network")
    require(bool(NAME.fullmatch(settings["otel_network"])), "OTEL_NETWORK", "missing or invalid network")
    if value("CERTIFICATE_RESOLVER"):
        # "none" reuses an existing wildcard certificate instead of a Traefik resolver.
        settings["certificate_resolver"] = "" if value("CERTIFICATE_RESOLVER") == "none" else value("CERTIFICATE_RESOLVER")
    hostname_field = "DOMAIN" if environment == "pr" else "HOST"
    hostname = value(hostname_field, "")
    require(bool(HOSTNAME.fullmatch(hostname)), hostname_field, "missing or invalid hostname")
    settings["domain" if environment == "pr" else "host"] = hostname
    if environment != "release":
        # Previews and staging share an operator-run PostgreSQL (deploy/infrastructure).
        settings["database_network"] = value("DATABASE_NETWORK", "people-gator-preview-db")
        require(bool(NAME.fullmatch(settings["database_network"])), "DATABASE_NETWORK", "missing or invalid network")
        settings["postgres_container"] = value("POSTGRES_CONTAINER", "people-gator-postgres")
        require(bool(NAME.fullmatch(settings["postgres_container"])), "POSTGRES_CONTAINER", "missing or invalid container name")
        settings["postgres_admin_user"] = value("POSTGRES_ADMIN_USER", "preview_admin")
        require(bool(re.fullmatch(r"[a-z_][a-z0-9_]*", settings["postgres_admin_user"])), "POSTGRES_ADMIN_USER", "invalid role name")
        # The backend sends logs, traces and metrics straight to this OTLP HTTP collector.
        settings["otel_http_endpoint"] = value("OTEL_HTTP_ENDPOINT", "http://lgtm:4318")
        require(bool(re.fullmatch(r"https?://[A-Za-z0-9.-]+(?::[0-9]{1,5})?", settings["otel_http_endpoint"])),
                "OTEL_HTTP_ENDPOINT", "requires an http(s)://host[:port] OTLP HTTP base URL without a path")
        require(value("OTEL_ENABLED", "true") in {"true", "false"}, "OTEL_ENABLED", "must be true or false")
        settings["otel_enabled"] = value("OTEL_ENABLED", "true") == "true"
    if environment != "pr":
        settings["project"] = value("PROJECT", "people-gator-" + environment)
        require(bool(PROJECT.fullmatch(settings["project"])), "PROJECT", "invalid Compose project")
    if environment == "staging" and value("SNAPSHOT"):
        try:
            snapshot = json.loads(value("SNAPSHOT"))
        except ValueError:
            raise problem(environment, "SNAPSHOT", "malformed JSON") from None
        from .staging import validate_snapshot
        try:
            settings["snapshot"] = validate_snapshot(snapshot)
        except DeployError as error:
            raise problem(environment, "SNAPSHOT", str(error)) from None
        require(not value("SNAPSHOT_SOURCE"), "SNAPSHOT_SOURCE", "choose the automatic source or the local SNAPSHOT archive, not both")
    if environment == "release":
        settings["database_network"] = value("DATABASE_NETWORK", "")
        require(bool(NAME.fullmatch(settings["database_network"])), "DATABASE_NETWORK", "name the external PostgreSQL network")
        settings["backend_memory"] = value("BACKEND_MEMORY", "4g")
        require(value("ACCESS_REVIEWED") == "true", "ACCESS_REVIEWED",
                "set to true after confirming the external access boundary and browser demo-login limitation")
    for name, (field, filename, _) in SECRETS[environment].items():
        if value(name) or name in REQUIRED_SECRETS[environment]:
            settings[field] = str(root / filename)
    return settings


def secrets(environment: str, settings: dict, env=None) -> list[tuple[Path, str, int]]:
    """Validated secret contents and their private destinations; nothing is written here."""
    env = os.environ if env is None else env
    files = []
    for name, (field, filename, mode) in SECRETS[environment].items():
        content = env.get(PREFIX + name) or ""
        if not content.strip():
            if name in REQUIRED_SECRETS[environment]:
                raise problem(environment, name, "missing secret contents")
            continue
        if name == "TELEMETRY_ENV":
            for line in content.splitlines():
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                key, separator, _ = line.partition("=")
                if not separator or not TELEMETRY_KEY.fullmatch(key):
                    raise problem(environment, name, "only unquoted RUM, API OTEL and OTLP exporter KEY=value lines are permitted")
                if environment != "release" and DEPLOY_OWNED_TELEMETRY.fullmatch(key):
                    raise problem(environment, name, f"{key} is set by the deployment; use DEPLOY_OTEL_ENABLED / DEPLOY_OTEL_HTTP_ENDPOINT")
        elif name in {"RUNTIME_ENV", "MIGRATION_ENV"}:
            try:
                keys = env_keys(content, source=PREFIX + name)
            except DeployError as error:
                raise problem(environment, name, str(error).partition(": ")[2]) from None
            if environment == "staging" and any(key.startswith("PEOPLE_GATOR_API__PERSISTENCE") for key in keys):
                raise problem(environment, name, "persistence settings are managed by staging; remove them")
        elif name == "USERS_JSON":
            try:
                users = json.loads(content)
            except ValueError:
                raise problem(environment, name, "malformed JSON") from None
            if not isinstance(users, dict):
                raise problem(environment, name, "expected a JSON object of users")
        elif name == "SNAPSHOT_SOURCE":
            from . import snapshots
            try:
                snapshots.parse_source(content)
            except DeployError as error:
                raise problem(environment, name, str(error)) from None
        if name.endswith("_ENV") and not content.endswith("\n"):
            content += "\n"
        files.append((Path(settings[field]), content, mode))
    return files


def materialize(files: list[tuple[Path, str, int]]) -> None:
    """Write secret files privately and atomically; unchanged content is left alone."""
    for path, content, mode in files:
        if path.exists() and not path.is_symlink() and path.read_text() == content and stat.S_IMODE(path.stat().st_mode) == mode:
            continue
        atomic(path, content)
        path.chmod(mode)
