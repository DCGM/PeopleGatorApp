from datetime import UTC, datetime

import pytest

from people_gator_api.cli.weaviate_backup import (
    BackupConfig,
    backup_id,
    cluster_is_healthy,
    prune_local_backups,
    seconds_until_backup_due,
)


def test_backup_id_is_stable_and_api_safe() -> None:
    assert backup_id(datetime(2026, 9, 7, 12, 34, 56, tzinfo=UTC)) == (
        "people-gator-20260907-123456-utc"
    )


def test_cluster_is_healthy_requires_loaded_ready_leader() -> None:
    healthy_node = {
        "dbLoaded": True,
        "leaderId": "people-gator-weaviate-dev",
        "ready": True,
        "status": "HEALTHY",
    }

    assert cluster_is_healthy(
        {"synchronized": True, "statistics": [healthy_node]}
    )
    assert not cluster_is_healthy(
        {"synchronized": True, "statistics": [{**healthy_node, "leaderId": ""}]}
    )
    assert not cluster_is_healthy(
        {"synchronized": False, "statistics": [healthy_node]}
    )


def test_backup_config_rejects_non_positive_intervals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WEAVIATE_BACKUP_INTERVAL_SECONDS", "0")

    with pytest.raises(ValueError, match="must be greater than zero"):
        BackupConfig.from_environment()


def test_prune_local_backups_keeps_newest_scheduler_backups(tmp_path) -> None:
    expected = tmp_path / "people-gator-20260907-120000-utc"
    expected.mkdir()
    old_backup = tmp_path / "people-gator-20260906-120000-utc"
    old_backup.mkdir()
    unrelated = tmp_path / "manual-backup"
    unrelated.mkdir()

    removed = prune_local_backups(tmp_path, keep_count=1)

    assert removed == [old_backup]
    assert expected.is_dir()
    assert not old_backup.exists()
    assert unrelated.is_dir()


def test_seconds_until_backup_due_uses_latest_successful_backup(tmp_path) -> None:
    successful = tmp_path / "people-gator-20260907-120000-utc"
    successful.mkdir()
    (successful / "backup_config.json").write_text(
        '{"status":"SUCCESS"}',
        encoding="utf-8",
    )
    incomplete = tmp_path / "people-gator-20260907-130000-utc"
    incomplete.mkdir()
    (incomplete / "backup_config.json").write_text(
        '{"status":"STARTED"}',
        encoding="utf-8",
    )

    delay = seconds_until_backup_due(
        tmp_path,
        86400,
        now=datetime(2026, 9, 7, 14, 0, tzinfo=UTC),
    )

    assert delay == 79200
