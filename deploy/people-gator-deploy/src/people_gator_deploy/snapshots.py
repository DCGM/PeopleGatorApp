"""Private S3 snapshot gathering, aligned with the backend backup publication contract.

Kept inside the reviewed host package: candidate application code never selects
or downloads backups. Only boto3/botocore are external runtime dependencies.
"""
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

from .core import DeployError
from .config import private_file


def require(condition, message):
    if not condition:
        raise DeployError(message)


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

def client_for(storage):
    import boto3
    from botocore.config import Config
    validate_storage(storage)
    return boto3.client("s3", endpoint_url=storage["endpoint_url"], region_name=storage["region"],
                        aws_access_key_id=storage["access_key_id"], aws_secret_access_key=storage["secret_access_key"],
                        config=Config(connect_timeout=10, read_timeout=120,
                                      retries={"max_attempts": 3, "mode": "standard"}))

def object_metadata(response):
    """Metadata comes from case-insensitive HTTP headers on S3 providers."""
    supplied = response.get("Metadata", {})
    require(isinstance(supplied, dict), "Invalid backup object metadata")
    result = {}
    for key, value in supplied.items():
        require(isinstance(key, str) and isinstance(value, str), "Invalid backup object metadata")
        normalized = key.lower()
        require(normalized not in result or result[normalized] == value, "Conflicting backup object metadata")
        result[normalized] = value
    return result

BACKUP_NAME = re.compile(r"peoplegator-prod-(\d{4}-\d{2}-\d{2})\.dump")

def backup_date(key, prefix):
    match = BACKUP_NAME.fullmatch(key[len(prefix):]) if key.startswith(prefix) else None
    if match:
        try:
            return date.fromisoformat(match[1])
        except ValueError:
            pass
    return None

def select_backup(client, storage, exact_key=""):
    validate_storage(storage)
    if exact_key:
        require(backup_date(exact_key, storage["prefix"]) is not None,
                "Exact backup key must be a dated archive inside the configured prefix")
        return exact_key
    latest = None
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=storage["bucket"], Prefix=storage["prefix"]):
        for item in page.get("Contents", []):
            day = backup_date(item["Key"], storage["prefix"])
            if day is not None and (latest is None or day > latest[0]):
                latest = (day, item["Key"])
    require(latest is not None, "No completed dated backup exists in the configured prefix")
    return latest[1]

def download(client, storage, key, destination):
    request = {"Bucket": storage["bucket"], "Key": key}
    before = client.head_object(**request)
    metadata = object_metadata(before)
    checksum = metadata.get("sha256", "")
    revision = metadata.get("application-revision", "")
    require(re.fullmatch(r"[a-f0-9]{64}", checksum) and re.fullmatch(r"[a-f0-9]{40}", revision),
            "Backup needs valid publisher SHA256 and application-revision metadata")
    require(type(before.get("ContentLength")) is int and before["ContentLength"] >= 5,
            "Backup has an invalid content length")
    require(isinstance(before.get("ETag"), str) and before["ETag"], "Backup needs an object identity")
    version = before.get("VersionId")
    condition = {"IfMatch": before["ETag"]}
    if version and version != "null":
        condition["VersionId"] = version
    response = client.get_object(**request, **condition)
    digest, size = hashlib.sha256(), 0
    try:
        require(all(response.get(field) == before.get(field) for field in ("ETag", "VersionId", "ContentLength")),
                "Backup identity changed before download")
        with os.fdopen(os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "wb") as stream:
            while chunk := response["Body"].read(1024 * 1024):
                size += len(chunk)
                require(size <= before["ContentLength"], "Backup exceeds its pinned size")
                digest.update(chunk)
                stream.write(chunk)
    finally:
        response["Body"].close()
    after = client.head_object(**request)
    require(all(after.get(field) == before.get(field) for field in ("ETag", "VersionId", "ContentLength"))
            and object_metadata(after) == metadata,
            "Backup changed during download")
    require(size == before["ContentLength"] and digest.hexdigest() == checksum,
            "Backup length or SHA256 checksum did not match")
    with destination.open("rb") as stream:
        require(stream.read(5) == b"PGDMP", "Backup is not a PostgreSQL custom archive")
    return {"bucket": storage["bucket"], "key": key, "backup_date": backup_date(key, storage["prefix"]).isoformat(),
            "size": size, "sha256": checksum, "etag": before["ETag"], "version_id": version,
            "application_revision": revision}


def read_source(path):
    require(private_file(Path(path)), "snapshot_source_file needs an owned private regular JSON file")
    try:
        storage = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        raise DeployError("Cannot read snapshot_source_file JSON") from None
    require(isinstance(storage, dict) and set(storage) == {
        "endpoint_url", "region", "bucket", "prefix", "access_key_id", "secret_access_key"},
        "Snapshot source requires endpoint_url, region, bucket, prefix and read-only access_key_id/secret_access_key")
    return validate_storage(storage)


def unchanged(client, storage, provenance):
    current = client.head_object(Bucket=storage["bucket"], Key=provenance["key"])
    require(all(current.get(field) == provenance.get(name) for field, name in (
        ("ETag", "etag"), ("VersionId", "version_id"), ("ContentLength", "size")))
        and object_metadata(current).get("sha256") == provenance["sha256"]
        and object_metadata(current).get("application-revision") == provenance["application_revision"],
        "Backup changed during restore; candidate will not be activated")

