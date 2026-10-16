"""Daily UTC publishing with a shared process lock and explicit retry behavior."""
from contextlib import contextmanager
from datetime import datetime, time as day_time, timedelta, timezone
import fcntl
import os
from pathlib import Path
import re
import time

from .core import (BackupError, BackupExists, client_for, head_or_none, object_key, object_metadata,
                   publish, read_config, require, validate_publisher)


@contextmanager
def agent_lock(path: Path):
    parent = path.parent
    parent.mkdir(mode=0o700, exist_ok=True)
    require(not parent.is_symlink() and parent.stat().st_mode & 0o077 == 0,
            "Backup lock needs a private mode-700 directory")
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise BackupError("Another backup operation holds this agent lock") from None
        yield
    finally:
        os.close(descriptor)


def utc_schedule(value):
    require(isinstance(value, str) and re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", value),
            "Daily backup time must be HH:MM in UTC")
    return day_time.fromisoformat(value)


def next_due(now, at, completed_day=None):
    require(now.tzinfo is not None, "Schedule clock must include a timezone")
    now = now.astimezone(timezone.utc)
    day = now.date()
    if completed_day is not None and completed_day >= day:
        day = completed_day + timedelta(days=1)
    return datetime.combine(day, at, timezone.utc)


def verify_existing(client, config, day):
    stored = head_or_none(client, config["storage"], object_key(config["storage"], day))
    metadata = object_metadata(stored or {})
    require(stored is not None and type(stored.get("ContentLength")) is int and stored["ContentLength"] >= 5
            and isinstance(metadata, dict)
            and isinstance(metadata.get("sha256"), str) and re.fullmatch(r"[a-f0-9]{64}", metadata["sha256"])
            and isinstance(metadata.get("application-revision"), str)
            and re.fullmatch(r"[a-f0-9]{40}", metadata["application-revision"]),
            "Existing dated backup lacks valid publisher metadata; operator inspection is required")


def serve(config_path: Path, at: str, retry_seconds: int, lock_file: Path, *, clock=None, sleep=None):
    require(config_path != Path("-"), "Scheduled backups require a private configuration file")
    require(type(retry_seconds) is int and 1 <= retry_seconds <= 86400, "Retry delay must be 1 to 86400 seconds")
    at = utc_schedule(at)
    clock = clock or (lambda: datetime.now(timezone.utc))
    sleep = sleep or time.sleep
    completed_day = None
    with agent_lock(lock_file):
        while True:
            current = clock()
            require(current.tzinfo is not None, "Schedule clock must include a timezone")
            now = current.astimezone(timezone.utc)
            due = next_due(now, at, completed_day)
            if now < due:
                sleep(min(60, (due - now).total_seconds()))
                continue
            try:
                config = validate_publisher(read_config(config_path))
                client = client_for(config["storage"])
                try:
                    publish(config, client=client, now=now)
                    event = "Backup published and verified"
                except BackupExists:
                    verify_existing(client, config, now.date())
                    event = "Existing dated backup metadata verified"
                # Retain the operation's start date if it completes after midnight.
                completed_day = now.date()
                print(now.strftime("%Y-%m-%dT%H:%M:%SZ ") + event, flush=True)
            except Exception:
                # Credentials, provider error bodies and PostgreSQL output stay private.
                print(now.strftime("%Y-%m-%dT%H:%M:%SZ ") + "Backup attempt failed; retrying after configured delay", flush=True)
                sleep(retry_seconds)
