"""A short list of variables configures each environment; everything else is a convention.

The deploy jobs pass the repository variables and secrets of one environment
(``PREVIEW_*``, ``STAGING_*`` or ``PRODUCTION_*``) to the utility as ``DEPLOY_*``:
the host, the database, the media storage, the OTLP collector, the RUM client
and, for previews, the demo users. From them the utility renders the API
environment files and the users file into the environment's private state
directory before each operation, because Compose env files and bind mounts must
outlive the job.
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
GITHUB_PREFIX = {"pr": "PREVIEW", "staging": "STAGING", "release": "PRODUCTION"}

# Conventions shared by every environment (see deploy/GITHUB-SETUP.md).
WEB_NETWORK = "web"
DATABASE_NETWORK = "db"
OTEL_NETWORK = "logging"
POSTGRES_IMAGE = "pgvector/pgvector:pg16"
EXAMPLE_USERS = Path(__file__).with_name("assets") / "users.example.json"

# name -> (environments, secret). Required: HOST and DATABASE_URL everywhere; the
# S3_* group for staging and production (S3_ENDPOINT_URL optional); the
# BACKUP_S3_* group all or nothing; RUM_* needs RUM_CLIENT_TOKEN.
ALL = ("pr", "staging", "release")
VARIABLES = {
    "HOST": (ALL, False),
    "DATABASE_URL": (ALL, True),
    "MIGRATION_DATABASE_URL": (("release",), True),
    "STORAGE_DIR": (("pr",), False),
    "S3_ENDPOINT_URL": (ALL, False), "S3_REGION": (ALL, False), "S3_BUCKET": (ALL, False),
    "S3_ACCESS_KEY_ID": (ALL, True), "S3_SECRET_ACCESS_KEY": (ALL, True),
    "BACKUP_S3_ENDPOINT_URL": (("staging",), False), "BACKUP_S3_REGION": (("staging",), False),
    "BACKUP_S3_BUCKET": (("staging",), False), "BACKUP_S3_PREFIX": (("staging",), False),
    "BACKUP_S3_ACCESS_KEY_ID": (("staging",), True), "BACKUP_S3_SECRET_ACCESS_KEY": (("staging",), True),
    "OTEL_ENDPOINT": (ALL, False), "OTEL_HEADERS": (ALL, True),
    "RUM_CLIENT_TOKEN": (ALL, True), "RUM_SITE": (ALL, False),
    "USERS_JSON": (("pr",), True),
}
S3 = ("S3_REGION", "S3_BUCKET", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY")
BACKUP = ("BACKUP_S3_ENDPOINT_URL", "BACKUP_S3_REGION", "BACKUP_S3_BUCKET", "BACKUP_S3_PREFIX",
          "BACKUP_S3_ACCESS_KEY_ID", "BACKUP_S3_SECRET_ACCESS_KEY")
HOSTNAME = re.compile(r"[a-z0-9]+(?:[.-][a-z0-9]+)*")
SECRET_FILES = {"users.json", "runtime.env", "migration.env", "telemetry.env", "snapshot-source.json"}


def names(environment: str) -> list[str]:
    """The variable names one environment's deploy jobs pass, in table order."""
    return [name for name, (environments, _) in VARIABLES.items() if environment in environments]


def default_state_root() -> Path:
    return Path.home() / ".local/opt/people-gator-deploy/state"


def problem(environment, name, reason):
    return DeployError(f"{GITHUB_PREFIX[environment]}_{name}: {reason}; see deploy/GITHUB-SETUP.md")


def private_file(path: Path):
    return (path.is_file() and not path.is_symlink() and path.stat().st_uid == os.geteuid()
            and stat.S_IMODE(path.stat().st_mode) & 0o077 == 0)


def protected_file(path: Path):
    """Readable by unprivileged containers, but writable only by its trusted owner."""
    return (path.is_file() and not path.is_symlink() and path.stat().st_uid in {0, os.geteuid()}
            and stat.S_IMODE(path.stat().st_mode) & 0o022 == 0)


def single_line(value) -> bool:
    return isinstance(value, str) and bool(value) and not any(ord(c) < 32 or ord(c) == 127 for c in value)


def parse_database(environment, name, url) -> dict:
    """postgresql://user:password@host[:port]/database → the API's persistence fields."""
    parts = urlsplit(url) if isinstance(url, str) else None
    if (parts is None or parts.scheme not in {"postgresql", "postgres"} or not parts.hostname or not parts.username
            or parts.password is None or parts.path in {"", "/"} or parts.query or parts.fragment):
        raise problem(environment, name, "must be postgresql://user:password@host[:port]/database")
    try:
        port = parts.port or 5432
    except ValueError:
        raise problem(environment, name, "invalid port") from None
    database = unquote(parts.path[1:])
    values = {"host": parts.hostname, "port": port, "user": unquote(parts.username),
              "password": unquote(parts.password), "database": database}
    if not all(single_line(values[key]) for key in ("host", "user", "password", "database")) or "/" in database:
        raise problem(environment, name, "user, password, host and database must be single-line values")
    return values


def load(environment: str, env=None) -> dict:
    """Validated controller settings for one environment; nothing is written here."""
    env = os.environ if env is None else env
    if environment not in ENVIRONMENTS:
        raise DeployError(f"Unknown environment {environment!r}; choose one of {', '.join(ENVIRONMENTS)}")

    def value(name):
        # GitHub passes undefined variables as empty strings: empty means unset.
        supplied = env.get("DEPLOY_" + name, "")
        if supplied and not single_line(supplied) and name != "USERS_JSON":
            raise problem(environment, name, "must be a single-line value")
        return supplied or None

    def require(name):
        supplied = value(name)
        if supplied is None:
            raise problem(environment, name, "is required")
        return supplied

    repository = env.get("DEPLOY_REPOSITORY") or env.get("GITHUB_REPOSITORY", "")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise DeployError("GITHUB_REPOSITORY (owner/name) is required; set DEPLOY_REPOSITORY outside GitHub Actions")
    root = Path(env.get("DEPLOY_STATE_DIR") or str(default_state_root() / environment)).expanduser()
    if not root.is_absolute() or root == Path("/"):
        raise DeployError("DEPLOY_STATE_DIR must be an absolute directory")
    host = require("HOST")
    if not HOSTNAME.fullmatch(host):
        raise problem(environment, "HOST", "must be a lowercase hostname such as staging.example.org")
    settings = {"environment": environment, "repository": repository, "state_dir": str(root),
                "web_network": WEB_NETWORK, "database_network": DATABASE_NETWORK, "otel_network": OTEL_NETWORK,
                "postgres_image": POSTGRES_IMAGE, "project": f"people-gator-{environment}",
                "domain" if environment == "pr" else "host": host,
                "postgres": parse_database(environment, "DATABASE_URL", require("DATABASE_URL")),
                "runtime_file": str(root / "runtime.env")}

    # Storage: S3 (the S3_* group) or, for previews, a directory on a Docker volume.
    s3 = {name: value(name) for name in (*S3, "S3_ENDPOINT_URL")}
    given = {name for name, supplied in s3.items() if supplied}
    if given:
        missing = [name for name in S3 if not s3[name]]
        if missing:
            raise problem(environment, missing[0], f"is required with the other {GITHUB_PREFIX[environment]}_S3_* settings")
        if value("STORAGE_DIR"):
            raise problem(environment, "STORAGE_DIR", "cannot be combined with the S3 settings")
        settings["storage"] = {"s3": {"region": s3["S3_REGION"], "bucket_name": s3["S3_BUCKET"],
                                      "access_key_id": s3["S3_ACCESS_KEY_ID"], "secret_access_key": s3["S3_SECRET_ACCESS_KEY"],
                                      **({"endpoint_url": s3["S3_ENDPOINT_URL"]} if s3["S3_ENDPOINT_URL"] else {})}}
    elif environment == "pr":
        directory = value("STORAGE_DIR") or "/data"
        if not directory.startswith("/"):
            raise problem(environment, "STORAGE_DIR", "must be an absolute path inside the container")
        settings["storage"] = {"local": {"root": directory}}
    else:
        raise problem(environment, "S3_BUCKET", f"is required (with {GITHUB_PREFIX[environment]}_S3_REGION, "
                                                 "S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY): media and users live in S3")

    if value("OTEL_ENDPOINT") or value("OTEL_HEADERS"):
        endpoint = require("OTEL_ENDPOINT")
        if not re.fullmatch(r"https?://[A-Za-z0-9.-]+(?::[0-9]{1,5})?", endpoint):
            raise problem(environment, "OTEL_ENDPOINT", "must be an http(s)://host[:port] OTLP HTTP base URL without a path")
        settings["otel"] = {"endpoint": endpoint, **({"headers": value("OTEL_HEADERS")} if value("OTEL_HEADERS") else {})}
    if value("RUM_CLIENT_TOKEN") or value("RUM_SITE"):
        settings["rum"] = {"client_token": require("RUM_CLIENT_TOKEN"), **({"site": value("RUM_SITE")} if value("RUM_SITE") else {})}
    if "otel" in settings or "rum" in settings:
        settings["telemetry_file"] = str(root / "telemetry.env")

    if environment == "pr":
        users = value("USERS_JSON")
        try:
            users = json.loads(users) if users else json.loads(EXAMPLE_USERS.read_text())
        except ValueError:
            raise problem(environment, "USERS_JSON", "is not valid JSON") from None
        if not isinstance(users, dict) or not users or not all(isinstance(entry, dict) and "hash" in entry for entry in users.values()):
            raise problem(environment, "USERS_JSON", "must map user names to objects with a hash and scopes, like people-gator-api/example.users.json")
        settings["users"] = users
        settings["users_file"] = str(root / "users.json")
    if environment == "staging":
        backup = {name: value(name) for name in BACKUP}
        if any(backup.values()):
            missing = [name for name in BACKUP if not backup[name]]
            if missing:
                raise problem(environment, missing[0], "is required with the other STAGING_BACKUP_S3_* settings")
            from . import snapshots
            source = {"endpoint_url": backup["BACKUP_S3_ENDPOINT_URL"], "region": backup["BACKUP_S3_REGION"],
                      "bucket": backup["BACKUP_S3_BUCKET"], "prefix": backup["BACKUP_S3_PREFIX"],
                      "access_key_id": backup["BACKUP_S3_ACCESS_KEY_ID"], "secret_access_key": backup["BACKUP_S3_SECRET_ACCESS_KEY"]}
            try:
                snapshots.validate_storage(source)
            except DeployError as error:
                raise problem(environment, "BACKUP_S3_BUCKET", str(error)) from None
            settings["backup_source"] = source
            settings["snapshot_source_file"] = str(root / "snapshot-source.json")
    if environment == "release":
        settings["migration"] = (parse_database(environment, "MIGRATION_DATABASE_URL", value("MIGRATION_DATABASE_URL"))
                                 if value("MIGRATION_DATABASE_URL") else settings["postgres"])
        settings["migration_file"] = str(root / "migration.env")
        settings["backend_memory"] = "4g"
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
