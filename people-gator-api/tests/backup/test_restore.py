import copy
import hashlib
import io
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from people_gator_api.backup import core, restore
from .test_publisher import CONFIG


KEY = CONFIG["storage"]["prefix"] + "peoplegator-prod-2026-10-16.dump"
RESTORE = {"database": {**CONFIG["database"], "database": "postgres", "user": "provisioner"},
           "storage": CONFIG["storage"], "target": {"database": "recovered", "user": "recovery_owner", "password": "target-secret"}}


def client_for(raw=b"PGDMP fixture", **overrides):
    identity = {"ETag": '"identity"', "VersionId": "version", "ContentLength": len(raw), "Metadata": {
        "sha256": hashlib.sha256(raw).hexdigest(), "application-revision": "a" * 40}, **overrides}
    client = Mock()
    client.head_object.return_value = identity
    client.get_object.return_value = {**identity, "Body": io.BytesIO(raw)}
    return client


def test_selection_uses_paginated_exact_calendar_dates_and_never_upload_order():
    client = Mock()
    prefix = CONFIG["storage"]["prefix"]
    keys = ["peoplegator-prod-2026-10-15.dump", "peoplegator-prod-2026-02-30.dump", "peoplegator-prod-2026-10-17.dump.partial",
            "peoplegator-prod-2026-10-16.dump", "nested/peoplegator-prod-2027-10-17.dump"]
    client.get_paginator.return_value.paginate.return_value = [
        {"Contents": [{"Key": prefix + key} for key in keys[:2]]},
        {"Contents": [{"Key": prefix + key} for key in keys[2:]]}]
    assert restore.select_backup(client, CONFIG["storage"]) == KEY
    assert restore.select_backup(client, CONFIG["storage"], KEY) == KEY
    with pytest.raises(core.BackupError):
        restore.select_backup(client, CONFIG["storage"], prefix + "../secret")


@pytest.mark.parametrize("failure", ["checksum", "size", "get-identity", "after-identity", "metadata", "not-custom"])
def test_bad_or_changed_backup_fails_before_database_access_and_closes_body(tmp_path, failure):
    tmp_path.chmod(0o700)
    raw = b"invalid archive" if failure == "not-custom" else b"PGDMP fixture"
    client = client_for(raw)
    response = client.get_object.return_value
    if failure == "checksum":
        client.head_object.return_value["Metadata"]["sha256"] = "b" * 64
    if failure == "size":
        response["Body"] = io.BytesIO(raw[:-1])
    if failure == "get-identity":
        response["ETag"] = '"changed"'
    if failure == "after-identity":
        before = client.head_object.return_value
        client.head_object.side_effect = [before, {**before, "ETag": '"changed"'}]
    if failure == "metadata":
        client.head_object.return_value["Metadata"] = {}
    with patch.object(restore, "run_tool") as tool, pytest.raises(core.BackupError):
        restore.restore(RESTORE, tmp_path / "report", exact_key=KEY, client=client)
    tool.assert_not_called()
    if failure != "metadata":
        assert response["Body"].closed
    assert not (tmp_path / "report").exists()


def test_restore_authenticates_as_target_owner_and_cleans_only_new_database(tmp_path):
    tmp_path.chmod(0o700)
    commands = []
    def tool(args, environment):
        commands.append((args, dict(environment)))
        if args == ["pg_restore", "--version"]:
            return b"pg_restore (PostgreSQL) 16.13"
        if args[0] == "psql":
            query = args[-1]
            if "FROM pg_database" in query:
                return b"0"
            if "FROM pg_roles" in query:
                return b"t"
            return b"fixture_revision" if "SELECT version_num" in query else b""
        if args[0] == "pg_restore" and "--list" not in args:
            assert environment["PGUSER"] == "recovery_owner"
            assert "--dbname=recovered" in args
            assert "provisioner" not in Path(environment["PGPASSFILE"]).read_text()
            raise core.BackupError("Injected restore failure")
        return b""
    with patch.object(restore, "run_tool", side_effect=tool), pytest.raises(core.BackupError, match="Injected"):
        restore.restore(RESTORE, tmp_path / "report", exact_key=KEY, client=client_for())
    drops = [(args, env) for args, env in commands if args[0] == "psql" and "DROP DATABASE" in args[-1]]
    assert len(drops) == 1
    assert 'DROP DATABASE "recovered"' in drops[0][0][-1]
    assert drops[0][1]["PGDATABASE"] == "postgres"
    assert drops[0][1]["PGUSER"] == "provisioner"


def test_existing_target_report_or_privileged_owner_never_creates_or_drops_database(tmp_path):
    tmp_path.chmod(0o700)
    for failure in ("report", "database", "owner"):
        report = tmp_path / failure
        if failure == "report":
            report.write_text("preserve")
        calls = []
        def tool(args, environment):
            calls.append(args)
            if args == ["pg_restore", "--version"]:
                return b"PostgreSQL 16.13"
            if args[0] == "psql":
                if "FROM pg_database" in args[-1]:
                    return b"1" if failure == "database" else b"0"
                return b"f"
            return b""
        with patch.object(restore, "run_tool", side_effect=tool), pytest.raises((core.BackupError, FileExistsError)):
            restore.restore(RESTORE, report, exact_key=KEY, client=client_for())
        assert not any("CREATE DATABASE" in str(args) or "DROP DATABASE" in str(args) for args in calls)
        if failure == "report":
            assert report.read_text() == "preserve"


def test_successful_restore_records_private_provenance_without_credentials(tmp_path):
    tmp_path.chmod(0o700)
    def tool(args, environment):
        if args == ["pg_restore", "--version"]:
            return b"PostgreSQL 16.13"
        if args[0] == "psql":
            if "FROM pg_database" in args[-1]:
                return b"0"
            if "FROM pg_roles" in args[-1]:
                return b"t"
            if "SELECT version_num" in args[-1]:
                return b"fixture_revision"
        return b""
    report = tmp_path / "report"
    with patch.object(restore, "run_tool", side_effect=tool):
        result = restore.restore(RESTORE, report, exact_key=KEY, client=client_for())
    assert result["schema_revision"] == "fixture_revision"
    assert report.stat().st_mode & 0o777 == 0o600
    assert "target-secret" not in report.read_text()
    assert "private-sentinel" not in report.read_text()
