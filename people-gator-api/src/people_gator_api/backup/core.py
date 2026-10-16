"""Private PostgreSQL archives and immutable S3 publication."""
from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit


class BackupError(ValueError):
    """Only fixed messages authored here may be printed by the CLI."""


class BackupExists(BackupError):
    pass


def require(condition, message):
    if not condition:
        raise BackupError(message)


def read_config(path: Path) -> dict:
    if path != Path("-"):
        require(not path.is_symlink() and path.is_file(), "A regular private JSON configuration file is required")
        require(path.stat().st_mode & 0o077 == 0, "Configuration permissions must be mode 600 or stricter")
    try:
        value = json.loads(sys.stdin.read() if path == Path("-") else path.read_text())
        require(isinstance(value, dict), "Configuration must be a JSON object")
        return value
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise BackupError("Cannot read private JSON configuration") from None


def text_fields(value, names):
    require(isinstance(value, dict), "Configuration section must be an object")
    require(all(isinstance(value.get(k), str) and value[k].strip() and
                not any(ord(c) < 32 or ord(c) == 127 for c in value[k]) for k in names),
            "Required configuration fields must be nonempty strings without control characters")


def validate_storage(storage):
    text_fields(storage, ("endpoint_url", "region", "bucket", "prefix", "access_key_id", "secret_access_key"))
    endpoint = urlsplit(storage["endpoint_url"])
    require(endpoint.scheme == "https" and endpoint.hostname and not endpoint.username and not endpoint.password
            and not endpoint.query and not endpoint.fragment and endpoint.path in {"", "/"},
            "Backup storage needs an explicit HTTPS S3 endpoint")
    require(re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", storage["bucket"]), "Invalid backup bucket")
    prefix = storage["prefix"]
    require(prefix.endswith("/") and not prefix.startswith("/") and ".." not in prefix.split("/")
            and "\\" not in prefix, "Backup prefix must be a relative directory ending in slash")
    return storage


def validate_database(database):
    text_fields(database, ("host", "user", "password", "database"))
    require(re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]{0,62}", database["database"]), "Invalid database identifier")
    require(type(database.get("port")) is int and 1 <= database["port"] <= 65535, "Explicit database port is required")
    require(database.get("sslmode") in {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"},
            "Explicit PostgreSQL sslmode is required")
    certificate = database.get("sslrootcert")
    if certificate is not None:
        text_fields(database, ("sslrootcert",))
        require((certificate == "system" and database["sslmode"] == "verify-full") or Path(certificate).is_absolute(),
                "PostgreSQL sslrootcert must be an absolute CA path, or system with verify-full")
    require(database["sslmode"] != "verify-ca" or certificate is not None,
            "verify-ca requires an explicit sslrootcert path")
    return database


def validate_publisher(config):
    require(set(config) == {"database", "storage", "application_revision"}, "Publisher requires database, storage and application_revision only")
    validate_database(config["database"])
    validate_storage(config["storage"])
    require(isinstance(config["application_revision"], str) and re.fullmatch(r"[a-f0-9]{40}", config["application_revision"]),
            "Explicit source application revision must be a full Git SHA")
    return config


def client_for(storage):
    import boto3
    from botocore.config import Config
    validate_storage(storage)
    return boto3.client("s3", endpoint_url=storage["endpoint_url"], region_name=storage["region"],
                        aws_access_key_id=storage["access_key_id"], aws_secret_access_key=storage["secret_access_key"],
                        config=Config(connect_timeout=10, read_timeout=120,
                                      retries={"max_attempts": 3, "mode": "standard"}))


def object_key(storage, day: date):
    return storage["prefix"] + "peoplegator-prod-" + day.isoformat() + ".dump"


def head_or_none(client, storage, key):
    from botocore.exceptions import ClientError
    try:
        return client.head_object(Bucket=storage["bucket"], Key=key)
    except ClientError as error:
        if error.response["ResponseMetadata"]["HTTPStatusCode"] == 404:
            return None
        raise


def digest_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def database_environment(database, work):
    # Neither libpq service files/options nor application/AWS credentials leak in.
    environment = {k: v for k, v in os.environ.items() if not k.startswith(("PG", "AWS_", "PEOPLE_GATOR_"))}
    def escape(value):
        return str(value).replace("\\", "\\\\").replace(":", "\\:")
    password_file = work / "pgpass"
    password_file.write_text(":".join(escape(database[k]) for k in ("host", "port", "database", "user", "password")) + "\n")
    password_file.chmod(0o600)
    environment.update(PGHOST=database["host"], PGPORT=str(database["port"]), PGUSER=database["user"],
                       PGDATABASE=database["database"], PGPASSFILE=str(password_file),
                       PGSSLMODE=database["sslmode"], PGCONNECT_TIMEOUT="15")
    if database.get("sslrootcert") or database["sslmode"] == "verify-full":
        environment["PGSSLROOTCERT"] = database.get("sslrootcert", "system")
    return environment


def run_tool(args, environment):
    try:
        return subprocess.run(args, env=environment, capture_output=True, check=True, timeout=3600).stdout
    except (OSError, subprocess.SubprocessError):
        raise BackupError("PostgreSQL tool failed; verify connection, permissions and PostgreSQL 16 compatibility") from None


def upload_archive(client, storage, key, archive, metadata, *, part_size=64 * 1024 * 1024):
    """Only a conditional PUT/CompleteMultipartUpload makes a dated key visible."""
    from botocore.exceptions import ClientError
    size = archive.stat().st_size
    require(0 < part_size <= 64 * 1024 * 1024 and size <= part_size * 10000,
            "Archive exceeds this agent's bounded-memory multipart limit")
    request = {"Bucket": storage["bucket"], "Key": key}
    upload = None
    try:
        with archive.open("rb") as stream:
            if size <= part_size:
                client.put_object(**request, Body=stream, ContentLength=size, Metadata=metadata,
                                  ContentType="application/octet-stream", IfNoneMatch="*")
            else:
                upload = client.create_multipart_upload(**request, Metadata=metadata,
                                                        ContentType="application/octet-stream")["UploadId"]
                parts = []
                while chunk := stream.read(part_size):
                    number = len(parts) + 1
                    response = client.upload_part(**request, UploadId=upload, PartNumber=number, Body=chunk)
                    parts.append({"PartNumber": number, "ETag": response["ETag"]})
                client.complete_multipart_upload(**request, UploadId=upload, MultipartUpload={"Parts": parts}, IfNoneMatch="*")
                upload = None
    except ClientError as error:
        if error.response["ResponseMetadata"]["HTTPStatusCode"] == 412:
            raise BackupExists("A backup already exists for this UTC date; it was not replaced") from None
        if error.response["ResponseMetadata"]["HTTPStatusCode"] == 409:
            raise BackupError("Conditional publication conflicted; inspect the dated object before retrying") from None
        raise
    finally:
        if upload is not None:
            client.abort_multipart_upload(**request, UploadId=upload)
    stored = client.head_object(**request)
    require(stored["ContentLength"] == size and all(stored.get("Metadata", {}).get(k) == v for k, v in metadata.items()),
            "Published backup metadata verification failed; inspect the dated object before retrying")
    return {"key": key, "size": size, "sha256": metadata["sha256"], "version_id": stored.get("VersionId")}


def publish(config, *, client=None, now=None):
    validate_publisher(config)
    storage = config["storage"]
    client = client if client is not None else client_for(storage)
    now = now or datetime.now(timezone.utc)
    require(now.tzinfo is not None, "Backup time must include a timezone")
    key = object_key(storage, now.astimezone(timezone.utc).date())
    if head_or_none(client, storage, key) is not None:
        raise BackupExists("A backup already exists for this UTC date; it was not replaced")
    with tempfile.TemporaryDirectory(prefix="people-gator-backup-") as directory:
        work = Path(directory)
        archive = work / "snapshot.dump"
        environment = database_environment(config["database"], work)
        version = run_tool(["pg_dump", "--version"], environment)
        require(re.search(rb"\b16\.", version), "Backup agent requires PostgreSQL 16 client tools")
        run_tool(["pg_dump", "--no-password", "--format=custom", "--no-owner", "--no-privileges", "--file=" + str(archive)], environment)
        with archive.open("rb") as stream:
            require(stream.read(5) == b"PGDMP", "Backup is not a PostgreSQL custom archive")
        run_tool(["pg_restore", "--list", str(archive)], environment)
        return upload_archive(client, storage, key, archive, {
            "sha256": digest_file(archive), "application-revision": config["application_revision"],
        })
