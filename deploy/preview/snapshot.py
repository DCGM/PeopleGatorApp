#!/usr/bin/env python3
"""Private staging preparation worker, run with the candidate backend's dependencies.

Never run on active data. Transfer credentials are mounted only for download and
sanitize, never on the API. All worker output is suppressed by the controller.
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
import re
import sys
import tempfile
import uuid


BACKUP_NAME = re.compile(r"peoplegator-prod-(\d{4}-\d{2}-\d{2})\.dump")
EXAMPLE_SCOPES = {
    "staging-viewer": ["browse"],
    "staging-annotator": ["browse", "annotate"],
    "staging-importer": ["browse", "ingest"],
    "staging-admin": ["browse", "annotate", "ingest", "admin"],
}

# Explicit classification: schema additions require a sanitizer review.
SANITIZED_COLUMNS = {
    "pg_demo_users": 'id display_name is_active external_subject external_issuer email'.split(),
    "pg_demo_api_keys": 'id identifier display_name user_id'.split(),
    "pg_demo_entities": 'id user_id last_touched_at last_touched_by_user_id last_touched_by_api_key_id kind name name_normalized description short_description wikidata_id nlcr_authority_id search_document'.split(),
    "pg_demo_aliases": 'id entity_id name name_normalized search_document'.split(),
    "pg_demo_sources": 'id last_touched_at last_touched_by_user_id last_touched_by_api_key_id url source_type'.split(),
    "pg_demo_documents": 'id library document_id name name_normalized'.split(),
    "pg_demo_pages": 'id library document_id page_id'.split(),
    "pg_demo_images": 'id'.split(),
    "pg_demo_text_mentions": 'id source_id entity_id entity_link_state entity_link_verified_by_user_id entity_link_verified_at mention mention_normalized context'.split(),
    "pg_demo_image_occurrences": 'id source_id entity_id entity_link_state entity_link_verified_by_user_id entity_link_verified_at occurrence_type roi'.split(),
    "pg_demo_faces": 'id user_id identifier confidence keypoints keypoint_types'.split(),
    "pg_demo_face_models": 'stub embedding_dim'.split(),
    "pg_demo_face_embeddings": 'face_id model_id embedding'.split(),
    "alembic_version": ["version_num"],
}


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


def download(client, bucket: str, key: str, destination: Path) -> dict:
    identity = client.head_object(Bucket=bucket, Key=key)
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
    if any(after.get(field) != identity.get(field) for field in ("ETag", "VersionId", "ContentLength")):
        raise ValueError("Backup changed during download")
    if size != identity["ContentLength"]:
        raise ValueError("Incomplete backup")
    # ETags for simple uploads are MD5s. Multipart/SSE identities are still pinned;
    # TLS, exact length, optional publisher SHA256, archive validation and restore
    # protect downloads where an ETag is not a content checksum.
    etag = identity["ETag"].strip('"')
    if re.fullmatch(r"[a-fA-F0-9]{32}", etag):
        md5 = hashlib.md5(usedforsecurity=False)
        with destination.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                md5.update(chunk)
        if md5.hexdigest() != etag.lower():
            raise ValueError("Object checksum mismatch")
    expected = identity.get("Metadata", {}).get("sha256")
    if expected and digest.hexdigest() != expected:
        raise ValueError("Publisher checksum mismatch")
    return {"bucket": bucket, "key": key, "version_id": version, "etag": identity["ETag"],
            "size": size, "sha256": digest.hexdigest(),
            "source_application_revision": identity.get("Metadata", {}).get("application-revision")}


async def connect():
    import asyncpg
    import people_gator_api.schemas  # initialize schema/settings imports in application order
    from people_gator_api.settings import settings
    config = settings.persistence.postgres
    if not re.fullmatch(r"staging_[a-f0-9]{16}", config.database):
        raise ValueError("Preparation requires an isolated staging generation database")
    return await asyncpg.connect(host=config.host, port=config.port, user=config.user,
                                 password=config.password, database=config.database)


def pseudonym(kind: str, identity) -> str:
    return f"{kind}-{hashlib.sha256(str(identity).encode()).hexdigest()[:20]}"


async def sanitize(connection, filesystem, source: dict, policy: dict) -> dict:
    """Snapshot administration, deliberately SQL-based; never application seeding.

    Reject unclassified schema additions. Preserve graph UUIDs, model dimensions,
    verification and attribution FKs; pseudonymize text. Only explicitly permitted
    pages keep pixels/faces/vectors; other pages get blank scans and lose biometric
    occurrences. OCR is always replaced with an empty valid layout.
    """
    from people_gator_api.media.page_image import page_image_key
    from people_gator_api.media.page_layout import page_layout_key
    from people_gator_api.schemas.sources import document_url, page_url
    from PIL import Image

    extra_schemas = await connection.fetch("""SELECT nspname FROM pg_namespace
        WHERE nspname NOT IN ('public','information_schema') AND left(nspname,3)<>'pg_'""")
    if extra_schemas:
        raise ValueError("Unclassified snapshot schema")
    routines = await connection.fetchval("""SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE n.nspname='public' AND p.proname NOT IN ('demo_unaccent','pg_demo_clear_entity_link')
        AND NOT EXISTS (SELECT FROM pg_depend d WHERE d.classid='pg_proc'::regclass
            AND d.objid=p.oid AND d.deptype='e')""")
    if routines:
        raise ValueError("Unclassified snapshot routine")
    columns = await connection.fetch("""SELECT table_name, column_name FROM information_schema.columns
        WHERE table_schema='public'""")
    allowed = SANITIZED_COLUMNS
    for row in columns:
        if row["column_name"] not in allowed.get(row["table_name"], set()):
            raise ValueError("Unclassified snapshot table/column; extend reviewed sanitizer first")
    if await connection.fetchval("SELECT count(*) FROM pg_demo_sources WHERE source_type NOT IN ('source','page','document','image')"):
        raise ValueError("Unclassified source type")
    revision = await connection.fetchval("SELECT version_num FROM alembic_version")
    if not revision or not re.fullmatch(r"[a-z0-9_]{1,64}", revision):
        raise ValueError("Missing/invalid source migration history")
    # An operator must explicitly classify biometric content; the safe default is none.
    permitted = {uuid.UUID(value) for value in policy.get("permitted_page_ids", [])}
    pages = await connection.fetch("SELECT * FROM pg_demo_pages ORDER BY id")
    if not permitted.issubset({row["id"] for row in pages}):
        raise ValueError("Media policy names a missing page")
    client = s3_client(source) if permitted else None
    source_prefix = source.get("prefix", "").strip("/")
    if source_prefix and (".." in source_prefix.split("/") or "\\" in source_prefix):
        raise ValueError("Invalid media import prefix")
    async with connection.transaction():
        await connection.execute("""UPDATE pg_demo_users SET display_name='Historical staging actor ' || id,
            external_subject='historical-' || id, external_issuer='urn:people-gator:staging:history',
            email=NULL, is_active=false""")
        if "pg_demo_api_keys" in {r["table_name"] for r in columns}:
            await connection.execute("""UPDATE pg_demo_api_keys SET identifier='historical-' || id,
                display_name='Historical staging key ' || id""")
        await connection.execute("""UPDATE pg_demo_entities SET name='Staging entity ' || id,
            description=NULL, short_description=NULL, wikidata_id=NULL, nlcr_authority_id=NULL""")
        await connection.execute("UPDATE pg_demo_aliases SET name='Staging alias ' || id")
        await connection.execute("UPDATE pg_demo_text_mentions SET mention='Redacted staging mention', context=NULL")
        # Non-page image/source URLs must never resolve to private production media.
        await connection.execute("UPDATE pg_demo_sources SET url='https://staging.invalid/source/' || id")
        await connection.execute("""DELETE FROM pg_demo_image_occurrences WHERE source_id NOT IN
            (SELECT id FROM pg_demo_pages WHERE id=ANY($1::uuid[]))""", list(permitted))
        await connection.execute("UPDATE pg_demo_faces SET identifier='Staging face ' || id")
        from people_gator_api.schemas.enums import FaceKeypointType, EntityType
        await connection.execute("UPDATE pg_demo_faces SET keypoint_types=$1::varchar[]", [str(k) for k in FaceKeypointType])
        await connection.execute("UPDATE pg_demo_entities SET kind=NULL WHERE NOT (kind=ANY($1::varchar[]))", [str(k) for k in EntityType])
        # ROI carries arbitrary JSON: retain only validated numeric geometry.
        rows = await connection.fetch("SELECT id, roi FROM pg_demo_image_occurrences")
        from people_gator_api.schemas.common import BoundingBox
        for row in rows:
            roi = BoundingBox.model_validate_json(row["roi"]).model_dump(mode="json")
            await connection.execute("UPDATE pg_demo_image_occurrences SET roi=$1::jsonb WHERE id=$2",
                                     json.dumps(roi), row["id"])
        for table in ("pg_demo_documents", "pg_demo_pages"):
            for row in await connection.fetch(f"SELECT * FROM {table}"):
                library = pseudonym("staging", row["library"])
                await connection.execute(f"UPDATE {table} SET library=$1 WHERE id=$2", library, row["id"])
                url = (page_url(library, row["document_id"], row["page_id"]) if table.endswith("pages")
                       else document_url(library, row["document_id"]))
                await connection.execute("UPDATE pg_demo_sources SET url=$1 WHERE id=$2", url, row["id"])
        if any(r["table_name"] == "pg_demo_documents" and r["column_name"] == "name" for r in columns):
            await connection.execute("UPDATE pg_demo_documents SET name='Staging document ' || id")
        for page in pages:
            library = pseudonym("staging", page["library"])
            if page["id"] in permitted:
                # Read canonical source keys only; no recursive source copy or credentials.
                key = page_image_key(page["library"], page["document_id"], page["page_id"])
                request_key = f"{source_prefix}/{key}" if source_prefix else key
                response = client.get_object(Bucket=source["bucket"], Key=request_key)
                try:
                    raw = response["Body"].read()
                finally:
                    response["Body"].close()
                image = Image.open(io.BytesIO(raw))
                image.load()
                image = image.convert("RGB")  # strip EXIF/comments and original metadata
                for occurrence in await connection.fetch("SELECT o.roi, f.keypoints FROM pg_demo_image_occurrences o LEFT JOIN pg_demo_faces f ON f.id=o.id WHERE o.source_id=$1", page["id"]):
                    roi = json.loads(occurrence["roi"])
                    if roi["x"] + roi["width"] > image.width or roi["y"] + roi["height"] > image.height:
                        raise ValueError("Permitted face ROI is outside its imported image")
                    if occurrence["keypoints"] and any(not (0 <= x < image.width and 0 <= y < image.height) for x, y in occurrence["keypoints"]):
                        raise ValueError("Permitted face keypoints are outside its imported image")
            else:
                image = Image.new("RGB", (1200, 1600), "white")
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=95)
            await filesystem.write_bytes(page_image_key(library, page["document_id"], page["page_id"]), buffer.getvalue())
            layout = {"id": str(page["page_id"]), "page_size": [image.height, image.width],
                      "regions": [], "reading_order": {}}
            await filesystem.write_bytes(page_layout_key(library, page["document_id"], page["page_id"]),
                                         json.dumps(layout).encode())
        await validate_data(connection)
    return {"source_schema_revision": revision, "pages": len(pages), "permitted_pages": len(permitted),
            "policy_sha256": hashlib.sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest()}


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


def write_auth(path: Path, value: dict):
    if path.exists() and json.loads(path.read_text()) == value:
        return
    descriptor, name = tempfile.mkstemp(prefix=".credential-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump(value, stream)
            stream.flush()
            if os.geteuid() == 0:
                os.fchown(stream.fileno(), 10001, 10001)
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def provision_auth(root: Path, supplied: dict):
    import people_gator_api.schemas
    import argon2
    from joserfc.jwk import ECKey, KeySet
    root.mkdir(parents=True, exist_ok=True)
    users_path = root / "users.json"
    users = json.loads(users_path.read_text()) if users_path.exists() else {}
    for username, scopes in EXAMPLE_SCOPES.items():
        if username not in users:
            record = supplied["users"][username]
            argon2.extract_parameters(record["hash"])
            users[username] = {"hash": record["hash"], "scopes": [f"people-gator:{s}" for s in scopes]}
    write_auth(users_path, users)
    keys_path = root / "api-keys.json"
    keys = json.loads(keys_path.read_text()) if keys_path.exists() else {}
    initial_keys = supplied.get("api_keys", {}) if not keys_path.exists() else {}
    for identifier, record in initial_keys.items():
        if identifier in keys:
            continue
        from people_gator_api.services.api_key_service import APIKeyRecord
        validated = APIKeyRecord.model_validate(record)
        argon2.extract_parameters(validated.hash)
        if validated.username not in users or not validated.scopes.issubset(users[validated.username]["scopes"]):
            raise ValueError("API key must belong to a staging user and its permitted scopes")
        keys[identifier] = validated.model_dump(mode="json")
    write_auth(keys_path, keys)
    jwks = root / "jwks.json"
    if not jwks.exists():
        key = ECKey.generate_key("P-256", parameters={"alg": "ES256", "use": "sig"}, auto_kid=True)
        write_auth(jwks, KeySet([key]).as_dict(private=True))


def own_data(root: Path):
    for directory, _, files in os.walk(root):
        os.chown(directory, 10001, 10001)
        os.chmod(directory, 0o700)
        for name in files:
            os.chown(Path(directory) / name, 10001, 10001)
            os.chmod(Path(directory) / name, 0o600)


async def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["download", "sanitize", "auth", "validate"])
    parser.add_argument("--exact-key", default="")
    args = parser.parse_args()
    if args.action == "download":
        config = json.loads(Path("/private/backup-source.json").read_text())
        bucket = config.get("bucket", "peoplegator-ingest")
        prefix = config.get("prefix", "production/db-backups/")
        client = s3_client(config)
        key = select_backup(client, bucket, prefix, args.exact_key)
        result = download(client, bucket, key, Path("/work/snapshot.dump"))
        if not re.fullmatch(r"[a-f0-9]{40}", result.get("source_application_revision") or ""):
            raise ValueError("Backup publisher must record application-revision metadata")
        result["backup_date"] = backup_date(key, prefix).isoformat()
        Path("/work/provenance.json").write_text(json.dumps(result))
    elif args.action == "auth":
        provision_auth(Path("/data/peoplegator_api"), json.loads(Path("/private/credential-input.json").read_text()))
        own_data(Path("/data/peoplegator_api"))
    else:
        connection = await connect()
        try:
            if args.action == "sanitize":
                from people_gator_api.filesystem.local import LocalFilesystem
                policy = json.loads(Path("/private/media-policy.json").read_text())
                source_path = Path("/private/media-source.json")
                source = json.loads(source_path.read_text()) if source_path.exists() else {}
                result = await sanitize(connection, LocalFilesystem("/data"), source, policy)
                own_data(Path("/data"))
                print(json.dumps(result))
            else:
                await validate_data(connection)
        finally:
            await connection.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as error:
        # Exception bodies can contain SQL, OCR or credentials. No private logs in Actions.
        print(f"Private staging preparation failed ({type(error).__name__}); active data was not selected for this operation", file=sys.stderr)
        sys.exit(1)
