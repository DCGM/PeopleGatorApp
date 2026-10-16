from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from people_gator_api.backup import core, scheduler
from .test_publisher import CONFIG


def utc(day, hour, minute=0):
    return datetime(2026, 10, day, hour, minute, tzinfo=timezone.utc)


def test_due_time_uses_utc_date_and_preserves_next_day_when_attempt_crosses_midnight():
    at = scheduler.utc_schedule("02:00")
    assert scheduler.next_due(utc(16, 1), at) == utc(16, 2)
    assert scheduler.next_due(utc(16, 3), at) == utc(16, 2)  # missed schedule: catch up
    assert scheduler.next_due(utc(16, 3), at, utc(16, 0).date()) == utc(17, 2)
    assert scheduler.next_due(utc(17, 0), at, utc(16, 0).date()) == utc(17, 2)
    assert scheduler.next_due(utc(17, 3), at, utc(16, 0).date()) == utc(17, 2)
    with pytest.raises(core.BackupError):
        scheduler.utc_schedule("24:00")


def config_file(tmp_path):
    path = tmp_path / "publisher.json"
    path.write_text(json.dumps(CONFIG))
    path.chmod(0o600)
    return path


def run_agent(tmp_path, times, publish, *, client=None, sleeps=None):
    clock = iter(times)
    with patch.object(scheduler, "publish", side_effect=publish), patch.object(scheduler, "client_for", return_value=client or Mock()):
        with pytest.raises(StopIteration):
            scheduler.serve(config_file(tmp_path), "02:00", 300, tmp_path / "state" / "agent.lock",
                            clock=lambda: next(clock), sleep=(sleeps or []).append)


def test_start_before_due_then_catchup_and_success_does_not_repeat_same_day(tmp_path):
    calls = []
    run_agent(tmp_path, [utc(16, 1, 59), utc(16, 2), utc(16, 3), utc(17, 2)],
              lambda config, **kwargs: calls.append(kwargs["now"]))
    assert calls == [utc(16, 2), utc(17, 2)]


def test_failed_attempt_retries_after_midnight_without_marking_next_day_complete(tmp_path, capsys):
    calls = []
    def publish(config, **kwargs):
        calls.append(kwargs["now"])
        if len(calls) == 1:
            raise RuntimeError("private-provider-sentinel")
    run_agent(tmp_path, [utc(16, 23, 59), utc(17, 0, 4), utc(17, 2)], publish)
    assert calls == [utc(16, 23, 59), utc(17, 2)]
    assert "retrying" in capsys.readouterr().out


def test_completed_yesterday_after_midnight_still_runs_today_at_due(tmp_path):
    calls = []
    run_agent(tmp_path, [utc(16, 23, 59), utc(17, 0, 4), utc(17, 2)],
              lambda config, **kwargs: calls.append(kwargs["now"]))
    assert calls == [utc(16, 23, 59), utc(17, 2)]


def test_restart_verifies_existing_publisher_metadata_and_rejects_corrupt_dates(tmp_path, capsys):
    good = {"ContentLength": 50, "Metadata": {"sha256": "a" * 64, "application-revision": "b" * 40}}
    client = Mock()
    client.head_object.side_effect = [{"ContentLength": 0, "Metadata": {}}, good]
    attempts = []
    def publish(config, **kwargs):
        attempts.append(kwargs["now"])
        raise core.BackupExists("private-provider-sentinel")
    run_agent(tmp_path, [utc(16, 3), utc(16, 3, 5), utc(16, 4)], publish, client=client)
    assert len(attempts) == 2
    output = capsys.readouterr().out
    assert "retrying" in output and "metadata verified" in output
    assert "private-provider-sentinel" not in output


def test_manual_and_scheduled_work_share_lock_without_changing_existing_files(tmp_path):
    lock = tmp_path / "state" / "agent.lock"
    with scheduler.agent_lock(lock):
        with pytest.raises(core.BackupError, match="Another"):
            with scheduler.agent_lock(lock):
                pytest.fail("Concurrent operation acquired lock")
    with scheduler.agent_lock(lock):
        pass


def test_agent_reloads_explicit_credentials_on_retry_without_exposing_errors(tmp_path, capsys):
    path = config_file(tmp_path)
    times = iter([utc(16, 3), utc(16, 3, 5)])
    observed = []
    def publish(config, **kwargs):
        observed.append(config["storage"]["secret_access_key"])
        if len(observed) == 1:
            updated = {**CONFIG, "storage": {**CONFIG["storage"], "secret_access_key": "rotated-private"}}
            replacement = path.with_suffix(".new")
            replacement.write_text(json.dumps(updated))
            replacement.chmod(0o600)
            replacement.replace(path)
            raise RuntimeError("private-provider-sentinel")
    with patch.object(scheduler, "publish", side_effect=publish), patch.object(scheduler, "client_for"):
        with pytest.raises(StopIteration):
            scheduler.serve(path, "02:00", 300, tmp_path / "state" / "agent.lock",
                            clock=lambda: next(times), sleep=lambda seconds: None)
    assert observed == ["private-sentinel", "rotated-private"]
    assert "private-provider-sentinel" not in capsys.readouterr().out
