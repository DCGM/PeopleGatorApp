"""Verified backup retrieval and isolated, original-data database recovery."""
from __future__ import annotations

from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from .core import (BackupError, client_for, database_environment, require, run_tool,
                   text_fields, validate_database, validate_storage)


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
    checksum = before.get("Metadata", {}).get("sha256", "")
    revision = before.get("Metadata", {}).get("application-revision", "")
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
        with destination.open("xb") as stream:
            while chunk := response["Body"].read(1024 * 1024):
                size += len(chunk)
                require(size <= before["ContentLength"], "Backup exceeds its pinned size")
                digest.update(chunk)
                stream.write(chunk)
    finally:
        response["Body"].close()
    after = client.head_object(**request)
    require(all(after.get(field) == before.get(field) for field in ("ETag", "VersionId", "ContentLength", "Metadata")),
            "Backup changed during download")
    require(size == before["ContentLength"] and digest.hexdigest() == checksum,
            "Backup length or SHA256 checksum did not match")
    with destination.open("rb") as stream:
        require(stream.read(5) == b"PGDMP", "Backup is not a PostgreSQL custom archive")
    return {"bucket": storage["bucket"], "key": key, "backup_date": backup_date(key, storage["prefix"]).isoformat(),
            "size": size, "sha256": checksum, "etag": before["ETag"], "version_id": version,
            "application_revision": revision}


def validate_restore(config):
    require(set(config) == {"database", "storage", "target"}, "Restore requires database, storage and target only")
    validate_database(config["database"])
    validate_storage(config["storage"])
    target = config["target"]
    require(isinstance(target, dict) and set(target) == {"database", "user", "password"},
            "Restore target requires a database, restricted owner username and password")
    text_fields(target, ("database", "user", "password"))
    require(all(re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]{0,62}", target[key]) for key in ("database", "user")),
            "Invalid restore target identifiers")
    require(target["database"] not in {"postgres", "template0", "template1", config["database"]["database"]},
            "Restore target must be a separate new database")
    require(target["user"] != config["database"]["user"], "Restore owner must differ from the provisioning user")
    return config


def sql(query, environment):
    return run_tool(["psql", "--no-password", "-XqAt", "--set=ON_ERROR_STOP=1", "--command=" + query], environment).decode().strip()


def restore(config, report: Path, *, exact_key="", client=None):
    validate_restore(config)
    require(report.parent.is_dir() and report.parent.stat().st_mode & 0o077 == 0,
            "Restore report needs an existing private mode-700 parent directory")
    # Reserve output before any side effect; never overwrite another recovery's report.
    descriptor = os.open(report, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    created = False
    try:
        storage = config["storage"]
        client = client if client is not None else client_for(storage)
        key = select_backup(client, storage, exact_key)
        with tempfile.TemporaryDirectory(prefix="people-gator-restore-") as directory:
            work = Path(directory)
            archive = work / "snapshot.dump"
            provenance = download(client, storage, key, archive)
            for name in ("admin", "extensions", "target"):
                (work / name).mkdir(mode=0o700)
            admin = database_environment(config["database"], work / "admin")
            require(re.search(rb"\b16\.", run_tool(["pg_restore", "--version"], admin)),
                    "Restore agent requires PostgreSQL 16 client tools")
            run_tool(["pg_restore", "--list", str(archive)], admin)
            target = config["target"]
            name, owner = target["database"], target["user"]
            quoted_name, quoted_owner = '"' + name + '"', '"' + owner + '"'
            require(sql(f"SELECT count(*) FROM pg_database WHERE datname='{name}'", admin) == "0",
                    "Restore refuses an existing target database")
            require(sql(f"""SELECT rolcanlogin AND NOT (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls)
                AND NOT EXISTS (SELECT FROM pg_auth_members WHERE member=pg_roles.oid)
                FROM pg_roles WHERE rolname='{owner}'""", admin) == "t",
                    "Restore owner must be an existing restricted LOGIN role without role memberships")
            # CREATE DATABASE cannot run inside a transaction. Keep it a single command
            # so a confirmed success is distinct from later setup/restore failures.
            sql(f"CREATE DATABASE {quoted_name} OWNER {quoted_owner} TEMPLATE template0 ALLOW_CONNECTIONS false", admin)
            created = True
            try:
                sql(f"REVOKE ALL ON DATABASE {quoted_name} FROM PUBLIC; GRANT CONNECT, TEMPORARY ON DATABASE {quoted_name} TO {quoted_owner}; "
                    f"ALTER DATABASE {quoted_name} ALLOW_CONNECTIONS true", admin)
                target_admin = database_environment({**config["database"], "database": name}, work / "extensions")
                sql("CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS pg_trgm; CREATE EXTENSION IF NOT EXISTS unaccent; "
                    "REVOKE CREATE ON SCHEMA public FROM PUBLIC", target_admin)
                # Archive SQL authenticates directly as restricted owner. SET ROLE
                # on a superuser connection does not provide this isolation.
                restricted = database_environment({**config["database"], **target}, work / "target")
                run_tool(["pg_restore", "--no-password", "--exit-on-error", "--single-transaction", "--no-owner",
                          "--no-privileges", "--no-comments", "--no-security-labels", "--dbname=" + name, str(archive)], restricted)
                schema_revision = sql("SELECT version_num FROM alembic_version", restricted)
                require(re.fullmatch(r"[a-zA-Z0-9_]{1,64}", schema_revision), "Restored migration revision is missing or invalid")
                provenance.update(database=name, owner=owner, schema_revision=schema_revision)
                with os.fdopen(descriptor, "w") as stream:
                    descriptor = None
                    json.dump(provenance, stream, indent=2)
                    stream.write("\n")
                    stream.flush()
                    os.fsync(stream.fileno())
            except BaseException:
                sql(f"DROP DATABASE {quoted_name} WITH (FORCE)", admin)
                created = False
                raise
            return provenance
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if not created:
            report.unlink(missing_ok=True)
