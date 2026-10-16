"""Backup publication failures must never expose data or replace a dated object."""
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError
import pytest

from people_gator_api.backup import core


CONFIG = {"database": {"host": "db", "port": 5432, "user": "reader", "password": "private-sentinel",
                       "database": "source", "sslmode": "require"},
          "storage": {"endpoint_url": "https://s3.example.test", "region": "test", "bucket": "backup-fixture",
                      "prefix": "production/db-backups/", "access_key_id": "id", "secret_access_key": "private-sentinel"},
          "application_revision": "a" * 40}


def failure(status):
    return ClientError({"Error": {"Code": str(status)}, "ResponseMetadata": {"HTTPStatusCode": status}}, "fixture")


def test_publish_validates_dump_before_conditional_upload_and_cleans_private_files(tmp_path):
    raw = b"PGDMP complete synthetic archive"
    client = Mock()
    client.head_object.side_effect = [failure(404), {"ContentLength": len(raw), "Metadata": {
        "sha256": hashlib.sha256(raw).hexdigest(), "application-revision": "a" * 40}}]
    work = []
    def tool(args, environment):
        assert "AWS_SECRET_ACCESS_KEY" not in environment
        assert "PGOPTIONS" not in environment
        assert environment["PGHOST"] == "db"
        assert environment["PGDATABASE"] == "source"
        if args == ["pg_dump", "--version"]:
            return b"pg_dump (PostgreSQL) 16.13"
        if args[0] == "pg_dump":
            path = Path(args[-1].removeprefix("--file="))
            work.append(path.parent)
            assert Path(environment["PGPASSFILE"]).stat().st_mode & 0o777 == 0o600
            path.write_bytes(raw)
        return b""
    with patch.object(core, "run_tool", side_effect=tool), patch.dict(os.environ, {
            "PGOPTIONS": "private-sentinel", "AWS_SECRET_ACCESS_KEY": "ambient"}):
        result = core.publish(CONFIG, client=client, now=datetime(2026, 10, 16, tzinfo=timezone.utc))
    assert result["key"].endswith("peoplegator-prod-2026-10-16.dump")
    assert client.put_object.call_args.kwargs["IfNoneMatch"] == "*"
    assert all(not path.exists() for path in work)


def test_existing_date_or_dump_failure_never_uploads():
    client = Mock()
    with pytest.raises(core.BackupExists), patch.object(core, "run_tool") as tool:
        core.publish(CONFIG, client=client)
    tool.assert_not_called()
    client.put_object.assert_not_called()
    client.head_object.side_effect = failure(404)
    with pytest.raises(core.BackupError), patch.object(core, "run_tool", side_effect=core.BackupError("fixture")):
        core.publish(CONFIG, client=client)
    client.put_object.assert_not_called()


def test_multipart_failure_aborts_and_completion_is_conditional(tmp_path):
    path = tmp_path / "archive"
    path.write_bytes(b"PGDMP" + b"a" * 25)
    client = Mock()
    client.create_multipart_upload.return_value = {"UploadId": "private-upload"}
    client.upload_part.return_value = {"ETag": "part"}
    client.complete_multipart_upload.side_effect = failure(412)
    with pytest.raises(core.BackupExists):
        core.upload_archive(client, CONFIG["storage"], "key", path, {}, part_size=10)
    assert client.complete_multipart_upload.call_args.kwargs["IfNoneMatch"] == "*"
    client.abort_multipart_upload.assert_called_once()
    client.delete_object.assert_not_called()
    client.put_object.assert_not_called()
    client.head_object.assert_not_called()


@pytest.mark.parametrize("status", [400, 403, 500, 412])
def test_failed_or_unsupported_conditional_upload_has_no_unconditional_fallback(tmp_path, status):
    path = tmp_path / "archive"
    path.write_bytes(b"PGDMP")
    client = Mock()
    client.put_object.side_effect = failure(status)
    with pytest.raises((core.BackupError, ClientError)):
        core.upload_archive(client, CONFIG["storage"], "key", path, {})
    assert client.put_object.call_count == 1
    client.delete_object.assert_not_called()


def test_storage_never_inherits_app_or_ambient_credentials():
    with patch("boto3.client") as client, patch.dict(os.environ, {"AWS_ACCESS_KEY_ID": "ambient"}):
        core.client_for(CONFIG["storage"])
    assert client.call_args.kwargs["aws_access_key_id"] == "id"
    incomplete = copy.deepcopy(CONFIG)
    del incomplete["storage"]["secret_access_key"]
    with pytest.raises(core.BackupError):
        core.validate_publisher(incomplete)


def test_cli_suppresses_private_json_and_provider_errors(tmp_path):
    config = tmp_path / "private.json"
    config.write_text('{"private-sentinel": not-json}')
    config.chmod(0o600)
    result = subprocess.run([sys.executable, "-m", "people_gator_api.backup", "publish", "--config", str(config)],
                            text=True, capture_output=True)
    assert result.returncode == 1
    assert "private-sentinel" not in result.stdout + result.stderr
    assert "Traceback" not in result.stderr


def test_private_file_permissions_and_literal_fields(tmp_path):
    path = tmp_path / "private.json"
    path.write_text(json.dumps(CONFIG))
    path.chmod(0o644)
    with pytest.raises(core.BackupError, match="permissions"):
        core.read_config(path)
    for field in ("prefix", "endpoint_url", "secret_access_key"):
        invalid = copy.deepcopy(CONFIG)
        invalid["storage"][field] = "private-sentinel\n"
        with pytest.raises(core.BackupError):
            core.validate_publisher(invalid)


def test_verified_postgres_tls_uses_explicit_trust_and_ignores_ambient_override(tmp_path):
    database = {**CONFIG["database"], "sslmode": "verify-full"}
    with patch.dict(os.environ, {"PGSSLROOTCERT": "untrusted-ambient"}):
        environment = core.database_environment(database, tmp_path)
    assert environment["PGSSLROOTCERT"] == "system"
    database["sslrootcert"] = None
    core.validate_database(database)
    assert core.database_environment(database, tmp_path)["PGSSLROOTCERT"] == "system"
    database["sslrootcert"] = "/run/private/db-ca.crt"
    assert core.database_environment(database, tmp_path)["PGSSLROOTCERT"] == "/run/private/db-ca.crt"
    database.update(sslmode="require", sslrootcert="system")
    with pytest.raises(core.BackupError):
        core.validate_database(database)


def test_conditional_race_conflict_is_not_misreported_as_existing_backup(tmp_path):
    path = tmp_path / "archive"
    path.write_bytes(b"PGDMP")
    client = Mock()
    client.put_object.side_effect = failure(409)
    with pytest.raises(core.BackupError, match="conflicted") as error:
        core.upload_archive(client, CONFIG["storage"], "key", path, {})
    assert not isinstance(error.value, core.BackupExists)


@pytest.mark.parametrize("multipart", [False, True])
@pytest.mark.parametrize("casing", [str.lower, str.title, str.upper])
def test_upload_accepts_metadata_header_casing_without_changing_values(tmp_path, multipart, casing):
    raw = b"PGDMP synthetic archive"
    path = tmp_path / "archive"
    path.write_bytes(raw)
    metadata = {"sha256": hashlib.sha256(raw).hexdigest(), "application-revision": "a" * 40}
    client = Mock()
    client.head_object.return_value = {"ContentLength": len(raw), "Metadata": {casing(k): v for k, v in metadata.items()}}
    client.create_multipart_upload.return_value = {"UploadId": "upload"}
    client.upload_part.return_value = {"ETag": "part"}
    result = core.upload_archive(client, CONFIG["storage"], "key", path, metadata,
                                 part_size=10 if multipart else 1024)
    assert result["sha256"] == metadata["sha256"]
    request = client.complete_multipart_upload if multipart else client.put_object
    assert request.call_args.kwargs["IfNoneMatch"] == "*"
    client.delete_object.assert_not_called()


@pytest.mark.parametrize("metadata", [None, {"sha256": 123}, {"sha256": "a", "Sha256": "b"}])
def test_invalid_or_conflicting_metadata_is_rejected_without_exposing_values(metadata):
    with pytest.raises(core.BackupError, match="backup object metadata"):
        core.object_metadata({"Metadata": metadata})
