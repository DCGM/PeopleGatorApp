#!/usr/bin/env python3
"""Private staging preparation worker, run with the candidate backend's dependencies.

Never run on active data. Transfer credentials are supplied only to preparation
workers through stdin, never to the API. Worker output is private to the controller.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import date
import hashlib
import io
import json
import os
from pathlib import Path
import posixpath
import re
import sys


BACKUP_NAME = re.compile(r"peoplegator-prod-(\d{4}-\d{2}-\d{2})\.dump")
EXAMPLE_SCOPES = {
    "staging-viewer": ["browse"],
    "staging-annotator": ["browse", "annotate"],
    "staging-importer": ["browse", "ingest"],
    "staging-admin": ["browse", "annotate", "ingest", "admin"],
}

# Application tables whose restored rows must be preserved exactly.
TABLES = ("pg_demo_users", "pg_demo_api_keys", "pg_demo_entities", "pg_demo_aliases", "pg_demo_sources",
          "pg_demo_documents", "pg_demo_pages", "pg_demo_images", "pg_demo_text_mentions",
          "pg_demo_image_occurrences", "pg_demo_faces", "pg_demo_face_models", "pg_demo_face_embeddings",
          "alembic_version")
TRANSFER = {"concurrency": 8, "max_object_mib": 256}


def backup_date(key: str, prefix: str) -> date | None:
    if not key.startswith(prefix):
        return None
    match = BACKUP_NAME.fullmatch(key[len(prefix):])
    if match:
        try:
            return date.fromisoformat(match[1])
        except ValueError:
            pass
    return None


def select_backup(client, bucket: str, prefix: str, exact_key: str = "") -> str:
    if not prefix or not prefix.endswith("/") or prefix.startswith("/") or ".." in prefix.split("/"):
        raise ValueError("Invalid backup prefix")
    if exact_key:
        if backup_date(exact_key, prefix) is None:
            raise ValueError("Exact key must be a dated backup within the configured prefix")
        return exact_key
    candidates = []
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        for item in page.get("Contents", []):
            timestamp = backup_date(item["Key"], prefix)
            if timestamp:
                candidates.append((timestamp, item["Key"]))
    if not candidates:
        raise ValueError("No completed dated backup exists")
    return max(candidates)[1]


def s3_client(config: dict):
    import boto3
    from botocore.config import Config
    if not config.get("endpoint_url", "").startswith("https://"):
        raise ValueError("An explicit HTTPS S3-compatible endpoint is required")
    # Never inherit an instance profile, ambient AWS credentials or a default endpoint.
    return boto3.client("s3", endpoint_url=config["endpoint_url"],
                        region_name=config["region"],
                        aws_access_key_id=config["access_key_id"],
                        aws_secret_access_key=config["secret_access_key"],
                        config=Config(retries={"max_attempts": 3, "mode": "standard"}))


def object_metadata(response):
    # Keep the controller worker standalone: trusted-controller tests also run
    # from sparse checkouts without the backend package or its dependencies.
    supplied = response.get("Metadata", {})
    if not isinstance(supplied, dict):
        raise ValueError("Invalid backup object metadata")
    result = {}
    for key, value in supplied.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ValueError("Invalid backup object metadata")
        normalized = key.lower()
        if normalized in result and result[normalized] != value:
            raise ValueError("Conflicting backup object metadata")
        result[normalized] = value
    return result


def download(client, bucket: str, key: str, destination: Path) -> dict:
    identity = client.head_object(Bucket=bucket, Key=key)
    metadata = object_metadata(identity)
    version = identity.get("VersionId")
    request = {"Bucket": bucket, "Key": key, "IfMatch": identity["ETag"]}
    if version and version != "null":
        request["VersionId"] = version
    response = client.get_object(**request)
    digest = hashlib.sha256()
    size = 0
    try:
        if response["ETag"] != identity["ETag"] or response.get("VersionId") != version:
            raise ValueError("Backup identity changed")
        with destination.open("xb") as stream:
            while chunk := response["Body"].read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
                stream.write(chunk)
    finally:
        response["Body"].close()
    # Check the current key as well as the pinned version. Replacement fails closed.
    after = client.head_object(Bucket=bucket, Key=key)
    if (any(after.get(field) != identity.get(field) for field in ("ETag", "VersionId", "ContentLength"))
            or object_metadata(after) != metadata):
        raise ValueError("Backup changed during download")
    if size != identity["ContentLength"]:
        raise ValueError("Incomplete backup")
    # ETags for simple uploads are MD5s. Multipart/SSE identities are still pinned;
    # TLS, exact length, optional publisher SHA256, archive validation and restore
    # protect downloads where an ETag is not a content checksum.
    etag = identity["ETag"].strip('"')
    expected = metadata.get("sha256")
    opaque_encryption = identity.get("ServerSideEncryption") == "aws:kms" or identity.get("SSECustomerAlgorithm")
    if not expected and not opaque_encryption and re.fullmatch(r"[a-fA-F0-9]{32}", etag):
        md5 = hashlib.md5(usedforsecurity=False)
        with destination.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                md5.update(chunk)
        if md5.hexdigest() != etag.lower():
            raise ValueError("Object checksum mismatch")
    if expected and digest.hexdigest() != expected:
        raise ValueError("Publisher checksum mismatch")
    return {"bucket": bucket, "key": key, "version_id": version, "etag": identity["ETag"],
            "size": size, "sha256": digest.hexdigest(),
            "source_application_revision": metadata.get("application-revision")}


async def connect():
    import asyncpg
    import people_gator_api.schemas  # initialize schema/settings imports in application order
    from people_gator_api.settings import settings
    config = settings.persistence.postgres
    if not re.fullmatch(r"staging_[a-f0-9]{16}", config.database):
        raise ValueError("Preparation requires an isolated staging generation database")
    return await asyncpg.connect(host=config.host, port=config.port, user=config.user,
                                 password=config.password, database=config.database)


async def validate_data(connection):
    invalid = await connection.fetchval("""SELECT count(*) FROM pg_demo_face_embeddings e
        JOIN pg_demo_face_models m ON m.stub=e.model_id WHERE vector_dims(e.embedding)<>m.embedding_dim""")
    if invalid:
        raise ValueError("Embedding/model dimension mismatch")
    # Execute a representative real vector query and a linked evidence join.
    await connection.fetch("""SELECT e.face_id FROM pg_demo_face_embeddings e
        JOIN pg_demo_faces f ON f.id=e.face_id JOIN pg_demo_image_occurrences o ON o.id=f.id
        JOIN pg_demo_sources s ON s.id=o.source_id
        ORDER BY e.embedding <=> e.embedding LIMIT 1""")
    await connection.fetch("""SELECT t.id FROM pg_demo_text_mentions t
        JOIN pg_demo_entities e ON e.id=t.entity_id JOIN pg_demo_sources s ON s.id=t.source_id LIMIT 1""")


def media_key(value):
    if (not isinstance(value, str) or not value or value.startswith("/") or "\\" in value
            or any(part in {"", ".", ".."} for part in value.split("/"))):
        raise ValueError("Invalid media transfer key")
    if "peoplegator_api" in value.split("/"):
        raise ValueError("Authentication objects cannot be copied as media")
    return value


async def media_plan(connection, source):
    """(kind, source key, destination key) for each object the restored rows reference.

    Destination keys come from the application's canonical helpers for this
    generation; source keys replace only the configured prefix. Nothing is
    listed, so unreferenced objects in a large source bucket are never read.
    """
    from people_gator_api.media.image_content import image_content_key
    from people_gator_api.media.page_image import page_image_key
    from people_gator_api.media.page_layout import page_layout_key
    from people_gator_api.settings import settings
    root = source.get("prefix", "").strip("/")
    if root:
        media_key(root)
    origins = {"scan": (source.get("page_image_prefix", "images/ndk"), settings.page_image.key_prefix),
               "layout": (source.get("page_layout_prefix", "page-layouts"), settings.page_layout.key_prefix),
               "image": (source.get("image_prefix", "images"), settings.image_content.key_prefix)}

    def entry(kind, destination):
        origin, target = origins[kind]
        target = media_key(target.strip("/")) + "/"
        if not destination.startswith(target):
            raise ValueError("Canonical media key is outside its configured prefix")
        relative = media_key(destination[len(target):])
        source_key = posixpath.join(*filter(None, (root, media_key(origin.strip("/")))), relative)
        return kind, media_key(source_key), media_key(destination)

    plan = {}
    for page in await connection.fetch("SELECT library, document_id, page_id FROM pg_demo_pages ORDER BY id"):
        for kind, helper in (("scan", page_image_key), ("layout", page_layout_key)):
            item = entry(kind, helper(page["library"], page["document_id"], page["page_id"]))
            plan[item[2]] = item
    for row in await connection.fetch("SELECT s.url FROM pg_demo_images i JOIN pg_demo_sources s ON s.id=i.id ORDER BY i.id"):
        item = entry("image", image_content_key(str(row["url"])))
        plan[item[2]] = item
    return list(plan.values())


def absent(error):
    code = (getattr(error, "response", None) or {}).get("Error", {}).get("Code")
    return isinstance(error, FileNotFoundError) or code in {"NoSuchKey", "404", "NotFound"}


async def copy_objects(client, filesystem, bucket, plan, *, concurrency=8, max_object_mib=256, progress=None):
    """Copy planned objects with a fixed worker pool and pinned source identity.

    An object already absent at the source is a reported gap (for example, a
    page registered before its scan was uploaded). An object that changes or
    disappears after it was identified fails the preparation. Memory is bounded
    by ``concurrency * max_object_mib``.
    """
    progress = progress or sys.stderr
    limit = max_object_mib * 1024 * 1024
    copied, missing = set(), {"scan": 0, "layout": 0, "image": 0}
    checked = 0

    def transfer(key, identity):
        try:
            response = client.get_object(Bucket=bucket, Key=key, IfMatch=identity["ETag"])
        except Exception:
            raise ValueError("Source media changed or disappeared during transfer") from None
        try:
            raw = response["Body"].read(limit + 1)
        finally:
            response["Body"].close()
        if len(raw) != identity["ContentLength"] or response.get("ETag") != identity["ETag"]:
            raise ValueError("Source media changed or was truncated during transfer")
        return raw

    async def copy(kind, key, destination):
        nonlocal checked
        try:
            identity = await asyncio.to_thread(client.head_object, Bucket=bucket, Key=key)
        except Exception as error:
            if not absent(error):
                raise
            missing[kind] += 1
        else:
            if (not isinstance(identity.get("ETag"), str) or not identity["ETag"]
                    or not isinstance(identity.get("ContentLength"), int)):
                raise ValueError("Source media needs an object identity")
            if identity["ContentLength"] > limit:
                raise ValueError("Source media object exceeds the configured transfer limit")
            await filesystem.write_bytes(destination, await asyncio.to_thread(transfer, key, identity))
            copied.add(destination)
        checked += 1
        if checked % 100 == 0 or checked == len(plan):
            print(f"media {checked}/{len(plan)} checked, {len(copied)} copied, "
                  f"{sum(missing.values())} absent at source", file=progress, flush=True)

    pending = iter(plan)

    async def worker():
        for item in pending:
            await copy(*item)

    workers = [asyncio.create_task(worker()) for _ in range(min(concurrency, len(plan)) or 1)]
    try:
        await asyncio.gather(*workers)
    except BaseException:
        for task in workers:
            task.cancel()
        await asyncio.gather(*workers, return_exceptions=True)
        raise
    return {"copied": copied, "missing": missing}


async def preserve(connection, filesystem, source, transfer=None):
    """Keep restored rows, graph identities, vectors and referenced original media intact."""
    revision = await connection.fetchval("SELECT version_num FROM alembic_version")
    if not isinstance(revision, str) or not re.fullmatch(r"[a-zA-Z0-9_]{1,64}", revision):
        raise ValueError("Missing/invalid source migration history")
    await validate_data(connection)
    plan = await media_plan(connection, source)
    settings = {**TRANSFER, **(transfer or {})}
    result = await copy_objects(s3_client(source), filesystem, source["bucket"], plan, **settings)
    missing_scans = await validate_page_media(connection, filesystem, expected_keys=result["copied"])
    return {"source_schema_revision": revision, "data_mode": "original", "referenced_media": len(plan),
            "media_objects": len(result["copied"]), "missing_source_media": result["missing"],
            "missing_page_scans": missing_scans}


async def read_auth(filesystem, key: str):
    from botocore.exceptions import ClientError
    try:
        value = json.loads(await filesystem.read_bytes(key))
        if not isinstance(value, dict):
            raise ValueError("Malformed staging authentication object")
        return value
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") not in {"NoSuchKey", "404", "NotFound"}:
            raise
        return None


async def provision_auth(filesystem, supplied: dict):
    import people_gator_api.schemas
    import argon2
    from joserfc.jwk import ECKey, KeySet
    from people_gator_api.settings import settings
    users_path = settings.jwk.users_path
    initial_users = await read_auth(filesystem, users_path)
    users = dict(initial_users) if initial_users is not None else {}
    for username, scopes in EXAMPLE_SCOPES.items():
        if username not in users:
            record = supplied["users"][username]
            argon2.extract_parameters(record["hash"])
            users[username] = {"hash": record["hash"], "scopes": [f"people-gator:{s}" for s in scopes]}
    if users != initial_users:
        await filesystem.write_bytes(users_path, json.dumps(users).encode())
    keys_path = settings.api_keys.keys_path
    existing_keys = await read_auth(filesystem, keys_path)
    keys = dict(existing_keys) if existing_keys is not None else {}
    initial_keys = supplied.get("api_keys", {}) if existing_keys is None else {}
    for identifier, record in initial_keys.items():
        if identifier in keys:
            continue
        from people_gator_api.services.api_key_service import APIKeyRecord
        validated = APIKeyRecord.model_validate(record)
        argon2.extract_parameters(validated.hash)
        if validated.username not in users or not validated.scopes.issubset(users[validated.username]["scopes"]):
            raise ValueError("API key must belong to a staging user and its permitted scopes")
        keys[identifier] = validated.model_dump(mode="json")
    if keys != existing_keys:
        await filesystem.write_bytes(keys_path, json.dumps(keys).encode())
    jwks = settings.jwk.key_path
    if await read_auth(filesystem, jwks) is None:
        key = ECKey.generate_key("P-256", parameters={"alg": "ES256", "use": "sig"}, auto_kid=True)
        await filesystem.write_bytes(jwks, json.dumps(KeySet([key]).as_dict(private=True)).encode())


def staging_filesystem():
    import people_gator_api.schemas
    from people_gator_api.settings import settings
    from people_gator_api.services.filesystem_service import get_filesystem
    if settings.storage.s3 is None or settings.storage.local is not None:
        raise ValueError("Staging preparation requires explicit S3 storage; local storage is forbidden")
    return get_filesystem()


async def validate_storage(connection, filesystem):
    """Read actual bucket objects before activation; no local/read-through fallback."""
    from people_gator_api.settings import settings
    for key in (settings.jwk.users_path, settings.api_keys.keys_path, settings.jwk.key_path):
        if await read_auth(filesystem, key) is None:
            raise ValueError("Missing staging S3 authentication object")
    await validate_page_media(connection, filesystem)


async def validate_page_media(connection, filesystem, *, expected_keys=()):
    from botocore.exceptions import ClientError
    from people_gator_api.media.page_image import page_image_key
    from people_gator_api.media.page_layout import page_layout_key
    from people_gator_api.schemas.pero import PageLayoutModel
    from PIL import Image
    async def optional_bytes(key):
        try:
            return await filesystem.read_bytes(key)
        except FileNotFoundError:
            pass
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") not in {"NoSuchKey", "404", "NotFound"}:
                raise
        if key in expected_keys:
            raise ValueError("Copied source media is missing from the staging destination")
        return None

    missing_scans = 0
    for page in await connection.fetch("SELECT * FROM pg_demo_pages ORDER BY id"):
        image = await optional_bytes(page_image_key(page["library"], page["document_id"], page["page_id"]))
        if image is None:
            missing_scans += 1  # Preserve registered pages with no source scan yet.
        else:
            Image.open(io.BytesIO(image)).verify()
        layout = await optional_bytes(page_layout_key(page["library"], page["document_id"], page["page_id"]))
        if layout is not None:
            PageLayoutModel.model_validate_json(layout)
    return missing_scans


async def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["download", "copy", "auth", "validate"])
    parser.add_argument("--exact-key", default="")
    args = parser.parse_args()
    inputs = json.load(sys.stdin)
    if args.action == "download":
        config = inputs["backup-source.json"]
        bucket = config.get("bucket", "peoplegator-db-backup")
        prefix = config.get("prefix", "production/db-backups/")
        client = s3_client(config)
        key = select_backup(client, bucket, prefix, args.exact_key)
        result = download(client, bucket, key, Path("/work/snapshot.dump"))
        if not re.fullmatch(r"[a-f0-9]{40}", result.get("source_application_revision") or ""):
            raise ValueError("Backup publisher must record application-revision metadata")
        result["backup_date"] = backup_date(key, prefix).isoformat()
        Path("/work/provenance.json").write_text(json.dumps(result))
    elif args.action == "auth":
        await provision_auth(staging_filesystem(), inputs["credential-input.json"])
    else:
        filesystem = staging_filesystem()
        connection = await connect()
        try:
            if args.action == "copy":
                result = await preserve(connection, filesystem, inputs["media-source.json"], inputs.get("transfer"))
                print(json.dumps(result))
            else:
                await validate_data(connection)
                await validate_storage(connection, filesystem)
        finally:
            await connection.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as error:
        # Exception bodies can contain SQL, OCR or credentials. No private logs in Actions.
        print(f"Private staging preparation failed ({type(error).__name__}); active data was not selected for this operation", file=sys.stderr)
        sys.exit(1)
