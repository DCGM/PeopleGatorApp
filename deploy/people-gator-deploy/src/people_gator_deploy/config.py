"""One JSON document configures each environment; everything else is a convention.

The deploy jobs pass the repository secret ``PREVIEW_CONFIG``, ``STAGING_CONFIG``
or ``PRODUCTION_CONFIG`` as ``DEPLOY_CONFIG`` (operators may point
``DEPLOY_CONFIG_FILE`` at a private file instead). The document names the host,
the database, the media storage, the OTLP collector, the RUM client and, for
previews, the demo users. From it the utility renders the API environment files
and the users file into the environment's private state directory before each
operation, because Compose env files and bind mounts must outlive the job.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat
from urllib.parse import unquote, urlsplit

from .core import DeployError, atomic

ENVIRONMENTS = ("pr", "staging", "release")
SECRET_NAMES = {"pr": "PREVIEW_CONFIG", "staging": "STAGING_CONFIG", "release": "PRODUCTION_CONFIG"}

# Conventions shared by every environment (see deploy/GITHUB-SETUP.md).
WEB_NETWORK = "web"
DATABASE_NETWORK = "people-gator-db"
OTEL_NETWORK = "logging"
POSTGRES_IMAGE = "pgvector/pgvector:pg16"
EXAMPLE_USERS = Path(__file__).with_name("assets") / "users.example.json"

HOSTNAME = re.compile(r"[a-z0-9]+(?:[.-][a-z0-9]+)*")
FIELDS = {
    "pr": {"host", "database", "storage", "otel", "rum", "users", "extra_env"},
    "staging": {"host", "database", "storage", "otel", "rum", "backup_source", "extra_env"},
    "release": {"host", "database", "migration_database", "storage", "otel", "rum", "extra_env"},
}
# API settings the deployment owns; extra_env cannot override them.
MANAGED_PREFIXES = ("PEOPLE_GATOR_API__HOST", "PEOPLE_GATOR_API__PORT", "PEOPLE_GATOR_API__DEBUG", "PEOPLE_GATOR_API__RELOAD",
                    "PEOPLE_GATOR_API__PERSISTENCE", "PEOPLE_GATOR_API__STORAGE", "PEOPLE_GATOR_API__JWK", "PEOPLE_GATOR_API__CORS",
                    "PEOPLE_GATOR_API__DEPLOYMENT", "PEOPLE_GATOR_API__OTEL", "PEOPLE_GATOR_API__RUM")
SECRET_FILES = {"users.json", "runtime.env", "migration.env", "telemetry.env", "snapshot-source.json"}


def default_state_root() -> Path:
    return Path.home() / ".local/opt/people-gator-deploy/state"


def problem(environment, field, reason):
    return DeployError(f"{SECRET_NAMES[environment]}: {field}: {reason}; see deploy/GITHUB-SETUP.md")


def private_file(path: Path):
    return (path.is_file() and not path.is_symlink() and path.stat().st_uid == os.geteuid()
            and stat.S_IMODE(path.stat().st_mode) & 0o077 == 0)


def protected_file(path: Path):
    """Readable by unprivileged containers, but writable only by its trusted owner."""
    return (path.is_file() and not path.is_symlink() and path.stat().st_uid in {0, os.geteuid()}
            and stat.S_IMODE(path.stat().st_mode) & 0o022 == 0)


def single_line(value) -> bool:
    return isinstance(value, str) and bool(value) and not any(ord(c) < 32 or ord(c) == 127 for c in value)


def parse_database(environment, field, url) -> dict:
    """postgresql://user:password@host[:port]/database → the API's persistence fields."""
    parts = urlsplit(url) if isinstance(url, str) else None
    if (parts is None or parts.scheme not in {"postgresql", "postgres"} or not parts.hostname or not parts.username
            or parts.password is None or parts.path in {"", "/"} or parts.query or parts.fragment):
        raise problem(environment, field, "must be postgresql://user:password@host[:port]/database")
    try:
        port = parts.port or 5432
    except ValueError:
        raise problem(environment, field, "invalid port") from None
    database = unquote(parts.path[1:])
    values = {"host": parts.hostname, "port": port, "user": unquote(parts.username),
              "password": unquote(parts.password), "database": database}
    if not all(single_line(values[key]) for key in ("host", "user", "password", "database")) or "/" in database:
        raise problem(environment, field, "user, password, host and database must be single-line values")
    return values


def validate_storage(environment, value) -> dict:
    """{"local": {"root": ...}} or {"s3": {...}} in the API's storage shape."""
    if not isinstance(value, dict) or set(value) - {"local", "s3"} or len(value) != 1:
        raise problem(environment, "storage", 'must be {"local": {"root": "/data"}} or {"s3": {...}}')
    if "local" in value:
        local = value["local"]
        if not isinstance(local, dict) or set(local) != {"root"} or not single_line(local["root"]) or not local["root"].startswith("/"):
            raise problem(environment, "storage.local", 'needs an absolute "root" path inside the container')
    else:
        s3 = value["s3"]
        required = {"region", "bucket_name", "access_key_id", "secret_access_key"}
        if not isinstance(s3, dict) or not required <= set(s3) or set(s3) - required - {"endpoint_url"}:
            raise problem(environment, "storage.s3", "needs region, bucket_name, access_key_id, secret_access_key and optionally endpoint_url")
        for key in set(s3):
            if not single_line(s3[key]):
                raise problem(environment, f"storage.s3.{key}", "must be a non-empty single-line string")
    return value


def validate_otel(environment, value) -> dict:
    if not isinstance(value, dict) or "endpoint" not in value or set(value) - {"endpoint", "headers"}:
        raise problem(environment, "otel", 'must be {"endpoint": "http://collector:4318", "headers": "optional"}')
    if not isinstance(value["endpoint"], str) or not re.fullmatch(r"https?://[A-Za-z0-9.-]+(?::[0-9]{1,5})?", value["endpoint"]):
        raise problem(environment, "otel.endpoint", "must be an http(s)://host[:port] OTLP HTTP base URL without a path")
    if "headers" in value and not single_line(value["headers"]):
        raise problem(environment, "otel.headers", "must be a single-line string such as Authorization=Basic …")
    return value


def validate_rum(environment, value) -> dict:
    optional = {"site", "organization_identifier", "application_id", "session_sample_rate", "session_replay_sample_rate"}
    if not isinstance(value, dict) or "client_token" not in value or set(value) - optional - {"client_token"}:
        raise problem(environment, "rum", 'must be {"client_token": "...", "site": "optional", ...}')
    for key, item in value.items():
        if key.endswith("_rate"):
            if not isinstance(item, (int, float)) or isinstance(item, bool) or not 0 <= item <= 100:
                raise problem(environment, f"rum.{key}", "must be a number between 0 and 100")
        elif not single_line(item):
            raise problem(environment, f"rum.{key}", "must be a non-empty single-line string")
    return value


def validate_extra_env(environment, value) -> dict:
    if not isinstance(value, dict):
        raise problem(environment, "extra_env", "must be an object of PEOPLE_GATOR_API__* settings")
    for key, item in value.items():
        if not re.fullmatch(r"PEOPLE_GATOR_API__[A-Z0-9_]+", key) or key.startswith(MANAGED_PREFIXES):
            raise problem(environment, f"extra_env.{key}", "only PEOPLE_GATOR_API__* settings the deployment does not manage")
        if not single_line(item):
            raise problem(environment, f"extra_env.{key}", "must be a non-empty single-line string")
    return value


def load(environment: str, env=None) -> dict:
    """Validated controller settings for one environment; nothing is written here."""
    env = os.environ if env is None else env
    if environment not in ENVIRONMENTS:
        raise DeployError(f"Unknown environment {environment!r}; choose one of {', '.join(ENVIRONMENTS)}")
    secret = SECRET_NAMES[environment]
    text = env.get("DEPLOY_CONFIG")
    if not text and env.get("DEPLOY_CONFIG_FILE"):
        try:
            text = Path(env["DEPLOY_CONFIG_FILE"]).read_text()
        except OSError:
            raise DeployError(f"DEPLOY_CONFIG_FILE: cannot read {env['DEPLOY_CONFIG_FILE']}") from None
    if not text or not text.strip():
        raise DeployError(f"{secret} is missing: pass its JSON as DEPLOY_CONFIG (or a file as DEPLOY_CONFIG_FILE); "
                          "see deploy/GITHUB-SETUP.md")
    try:
        document = json.loads(text)
    except ValueError:
        raise problem(environment, "document", "is not valid JSON") from None
    if not isinstance(document, dict):
        raise problem(environment, "document", "must be a JSON object")
    unknown = set(document) - FIELDS[environment]
    if unknown:
        raise problem(environment, ", ".join(sorted(unknown)), f"unknown field; allowed: {', '.join(sorted(FIELDS[environment]))}")
    repository = env.get("DEPLOY_REPOSITORY") or env.get("GITHUB_REPOSITORY", "")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise DeployError("GITHUB_REPOSITORY (owner/name) is required; set DEPLOY_REPOSITORY outside GitHub Actions")
    root = Path(env.get("DEPLOY_STATE_DIR") or str(default_state_root() / environment)).expanduser()
    if not root.is_absolute() or root == Path("/"):
        raise DeployError("DEPLOY_STATE_DIR must be an absolute directory")

    host = document.get("host", "")
    if not isinstance(host, str) or not HOSTNAME.fullmatch(host):
        raise problem(environment, "host", "must be a lowercase hostname such as staging.example.org")
    settings = {"environment": environment, "repository": repository, "state_dir": str(root),
                "web_network": WEB_NETWORK, "database_network": DATABASE_NETWORK, "otel_network": OTEL_NETWORK,
                "postgres_image": POSTGRES_IMAGE, "project": f"people-gator-{environment}",
                "domain" if environment == "pr" else "host": host,
                "postgres": parse_database(environment, "database", document.get("database")),
                "storage": validate_storage(environment, document["storage"]) if "storage" in document
                else ({"local": {"root": "/data"}} if environment == "pr" else None),
                "extra_env": validate_extra_env(environment, document.get("extra_env", {}))}
    if settings["storage"] is None:
        raise problem(environment, "storage", 'is required: {"s3": {...}} or {"local": {"root": "/data"}}')
    if "otel" in document:
        settings["otel"] = validate_otel(environment, document["otel"])
    if "rum" in document:
        settings["rum"] = validate_rum(environment, document["rum"])
    if environment == "pr":
        users = document.get("users")
        if users is None:
            users = json.loads(EXAMPLE_USERS.read_text())
        if not isinstance(users, dict) or not users or not all(isinstance(entry, dict) and "hash" in entry for entry in users.values()):
            raise problem(environment, "users", "must map user names to objects with a hash and scopes, like people-gator-api/example.users.json")
        settings["users"] = users
        settings["users_file"] = str(root / "users.json")
    if environment == "staging" and "backup_source" in document:
        from . import snapshots
        source = document["backup_source"]
        try:
            if not isinstance(source, dict) or set(source) != {"endpoint_url", "region", "bucket", "prefix", "access_key_id", "secret_access_key"}:
                raise DeployError("needs exactly endpoint_url, region, bucket, prefix, access_key_id and secret_access_key")
            snapshots.validate_storage(source)
        except DeployError as error:
            raise problem(environment, "backup_source", str(error)) from None
        settings["backup_source"] = source
        settings["snapshot_source_file"] = str(root / "snapshot-source.json")
    if environment == "release":
        settings["migration"] = (parse_database(environment, "migration_database", document["migration_database"])
                                 if "migration_database" in document else settings["postgres"])
        settings["migration_file"] = str(root / "migration.env")
        settings["backend_memory"] = "4g"
    settings["runtime_file"] = str(root / "runtime.env")
    if "otel" in settings or "rum" in settings:
        settings["telemetry_file"] = str(root / "telemetry.env")
    return settings


def dotenv(values: dict) -> str:
    """Raw-format env file: values are literal, one per line."""
    for key, value in values.items():
        if not single_line(str(value)):
            raise DeployError(f"{key}: value must be a single line")
    return "".join(f"{key}={value}\n" for key, value in values.items())


def persistence(values: dict) -> dict:
    return {f"PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__{key.upper()}": str(values[key])
            for key in ("host", "port", "user", "password", "database")}


def files(environment: str, settings: dict) -> list[tuple[Path, str, int]]:
    """The private files the Compose stacks read, rendered from the settings."""
    storage = settings["storage"]
    runtime = {"PEOPLE_GATOR_API__STORAGE": json.dumps({"local": storage.get("local"), "s3": storage.get("s3")})}
    if environment != "pr":
        host = settings["host"]
        runtime.update({"PEOPLE_GATOR_API__JWK__ISSUER": f"https://{host}", "PEOPLE_GATOR_API__JWK__AUDIENCE": host})
    if environment == "release":
        runtime.update(persistence(settings["postgres"]))
    runtime.update(settings["extra_env"])
    result = [(Path(settings["runtime_file"]), dotenv(runtime), 0o600)]
    if environment == "release":
        result.append((Path(settings["migration_file"]), dotenv(persistence(settings["migration"])), 0o600))
    if "telemetry_file" in settings:
        telemetry = {}
        if "otel" in settings:
            endpoint = settings["otel"]["endpoint"]
            telemetry.update({"PEOPLE_GATOR_API__OTEL__ENABLED": "true",
                              "PEOPLE_GATOR_API__OTEL__TRACES_ENDPOINT": f"{endpoint}/v1/traces",
                              "PEOPLE_GATOR_API__OTEL__LOGS_ENDPOINT": f"{endpoint}/v1/logs",
                              "PEOPLE_GATOR_API__OTEL__METRICS_ENDPOINT": f"{endpoint}/v1/metrics"})
            if "headers" in settings["otel"]:
                telemetry["OTEL_EXPORTER_OTLP_HEADERS"] = settings["otel"]["headers"]
        if "rum" in settings:
            telemetry["PEOPLE_GATOR_API__RUM__ENABLED"] = "true"
            telemetry.update({f"PEOPLE_GATOR_API__RUM__{key.upper()}": str(value) for key, value in settings["rum"].items()})
        result.append((Path(settings["telemetry_file"]), dotenv(telemetry), 0o600))
    if environment == "pr":
        # The unprivileged backend container (UID 10001) reads this bind mount.
        result.append((Path(settings["users_file"]), json.dumps(settings["users"], indent=2) + "\n", 0o644))
    if "snapshot_source_file" in settings:
        result.append((Path(settings["snapshot_source_file"]), json.dumps(settings["backup_source"]) + "\n", 0o600))
    return result


def materialize(files: list[tuple[Path, str, int]], root: Path | None = None) -> None:
    """Write private files atomically; unchanged content is left alone, unconfigured files are removed."""
    for path, content, mode in files:
        if path.exists() and not path.is_symlink() and path.read_text() == content and stat.S_IMODE(path.stat().st_mode) == mode:
            continue
        atomic(path, content)
        path.chmod(mode)
    if root is not None:
        rendered = {path for path, _, _ in files}
        for name in SECRET_FILES:
            if root / name not in rendered:
                (root / name).unlink(missing_ok=True)
