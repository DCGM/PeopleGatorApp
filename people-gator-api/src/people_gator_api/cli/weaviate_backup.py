"""Periodically create and verify native Weaviate backups."""

import json
import logging
import os
import re
import shutil
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_SUCCESS = "SUCCESS"
_TERMINAL_STATUSES = {_SUCCESS, "FAILED", "CANCELED"}


@dataclass(frozen=True)
class BackupConfig:
    api_url: str
    backend: str
    interval_seconds: float
    retry_seconds: float
    timeout_seconds: float
    poll_seconds: float = 10.0
    local_path: Path | None = None
    keep_count: int = 3

    @classmethod
    def from_environment(cls) -> "BackupConfig":
        return cls(
            api_url=os.getenv(
                "WEAVIATE_BACKUP_API_URL",
                "http://people-gator-weaviate-dev:8080",
            ).rstrip("/"),
            backend=os.getenv("WEAVIATE_BACKUP_BACKEND", "s3"),
            interval_seconds=_positive_float(
                "WEAVIATE_BACKUP_INTERVAL_SECONDS", 86400
            ),
            retry_seconds=_positive_float("WEAVIATE_BACKUP_RETRY_SECONDS", 300),
            timeout_seconds=_positive_float(
                "WEAVIATE_BACKUP_TIMEOUT_SECONDS", 21600
            ),
            poll_seconds=_positive_float("WEAVIATE_BACKUP_POLL_SECONDS", 10),
            local_path=_optional_path("WEAVIATE_BACKUP_LOCAL_PATH"),
            keep_count=_positive_int("WEAVIATE_BACKUP_KEEP_COUNT", 3),
        )


def _positive_float(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    value = default if raw_value is None else float(raw_value)
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


def _positive_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    value = default if raw_value is None else int(raw_value)
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


def _optional_path(name: str) -> Path | None:
    raw_value = os.getenv(name)
    return None if not raw_value else Path(raw_value)


def backup_id(now: datetime | None = None) -> str:
    timestamp = now or datetime.now(UTC)
    return timestamp.astimezone(UTC).strftime("people-gator-%Y%m%d-%H%M%S-utc")


def _request_json(
    url: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    encoded_body = None if body is None else json.dumps(body).encode("utf-8")
    request = Request(
        url,
        data=encoded_body,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - URL is operator-controlled configuration.
        payload = cast(object, json.load(response))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Unexpected response from Weaviate: {payload!r}")
    return cast(dict[str, Any], payload)


def cluster_is_healthy(payload: dict[str, Any]) -> bool:
    statistics = payload.get("statistics")
    if payload.get("synchronized") is not True or not isinstance(statistics, list):
        return False
    if not statistics:
        return False
    for raw_node in cast(list[object], statistics):
        if not isinstance(raw_node, dict):
            return False
        node = cast(dict[str, object], raw_node)
        if not (
            node.get("dbLoaded") is True
            and node.get("ready") is True
            and node.get("status") == "HEALTHY"
            and bool(node.get("leaderId"))
        ):
            return False
    return True


def wait_for_healthy_cluster(config: BackupConfig) -> None:
    deadline = time.monotonic() + config.timeout_seconds
    statistics_url = f"{config.api_url}/v1/cluster/statistics"
    while True:
        try:
            if cluster_is_healthy(
                _request_json(statistics_url, timeout_seconds=config.poll_seconds)
            ):
                return
        except (HTTPError, URLError, TimeoutError, RuntimeError, ValueError) as exc:
            logger.warning("Weaviate health check failed: %s", exc)
        if time.monotonic() >= deadline:
            raise TimeoutError("Timed out waiting for a healthy Weaviate cluster")
        time.sleep(config.poll_seconds)


def create_and_wait_for_backup(config: BackupConfig) -> str:
    current_backup_id = backup_id()
    backup_url = f"{config.api_url}/v1/backups/{config.backend}"
    logger.info("Starting Weaviate backup %s", current_backup_id)
    _request_json(
        backup_url,
        method="POST",
        body={"id": current_backup_id},
        timeout_seconds=30.0,
    )

    deadline = time.monotonic() + config.timeout_seconds
    status_url = f"{backup_url}/{current_backup_id}"
    while True:
        response = _request_json(status_url, timeout_seconds=30.0)
        status = str(response.get("status", "")).upper()
        if status in _TERMINAL_STATUSES:
            if status != _SUCCESS:
                error = response.get("error") or "no error details returned"
                raise RuntimeError(
                    f"Weaviate backup {current_backup_id} ended as {status}: {error}"
                )
            logger.info("Weaviate backup %s completed successfully", current_backup_id)
            return current_backup_id
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"Timed out waiting for Weaviate backup {current_backup_id}"
            )
        time.sleep(config.poll_seconds)


def prune_local_backups(directory: Path, keep_count: int) -> list[Path]:
    """Remove old full backups created by this scheduler only."""
    if not directory.is_dir():
        raise RuntimeError(f"Backup directory does not exist: {directory}")
    backup_name = re.compile(r"people-gator-\d{8}-\d{6}-utc")
    candidates = sorted(
        (
            path
            for path in directory.iterdir()
            if path.is_dir()
            and not path.is_symlink()
            and backup_name.fullmatch(path.name)
        ),
        key=lambda path: path.name,
        reverse=True,
    )
    removed: list[Path] = []
    for old_backup in candidates[keep_count:]:
        shutil.rmtree(old_backup)
        removed.append(old_backup)
        logger.info("Removed expired Weaviate backup %s", old_backup.name)
    return removed


def seconds_until_backup_due(
    directory: Path,
    interval_seconds: float,
    *,
    now: datetime | None = None,
) -> float:
    """Avoid creating another full backup after a scheduler restart."""
    if not directory.is_dir():
        return 0.0
    latest_started_at: datetime | None = None
    for path in directory.glob("people-gator-????????-??????-utc"):
        config_path = path / "backup_config.json"
        if not path.is_dir() or path.is_symlink() or not config_path.is_file():
            continue
        try:
            payload = cast(object, json.loads(config_path.read_text("utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        backup_config = cast(dict[str, object], payload)
        if backup_config.get("status") != _SUCCESS:
            continue
        try:
            started_at = datetime.strptime(
                path.name,
                "people-gator-%Y%m%d-%H%M%S-utc",
            ).replace(tzinfo=UTC)
        except ValueError:
            continue
        if latest_started_at is None or started_at > latest_started_at:
            latest_started_at = started_at
    if latest_started_at is None:
        return 0.0
    current_time = now or datetime.now(UTC)
    elapsed_seconds = (current_time.astimezone(UTC) - latest_started_at).total_seconds()
    return max(0.0, interval_seconds - elapsed_seconds)


def run_scheduler(config: BackupConfig) -> None:
    if config.backend == "filesystem" and config.local_path is not None:
        initial_delay_seconds = seconds_until_backup_due(
            config.local_path,
            config.interval_seconds,
        )
        if initial_delay_seconds > 0:
            logger.info(
                "Latest backup is current; next backup starts in %.0f seconds",
                initial_delay_seconds,
            )
            time.sleep(initial_delay_seconds)

    while True:
        delay_seconds = config.retry_seconds
        try:
            wait_for_healthy_cluster(config)
            create_and_wait_for_backup(config)
            if config.backend == "filesystem" and config.local_path is not None:
                prune_local_backups(config.local_path, config.keep_count)
            delay_seconds = config.interval_seconds
        except (HTTPError, URLError, TimeoutError, RuntimeError, ValueError) as exc:
            logger.exception(
                "Scheduled Weaviate backup failed; retrying in %.0f seconds: %s",
                delay_seconds,
                exc,
            )
        time.sleep(delay_seconds)


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    run_scheduler(BackupConfig.from_environment())


if __name__ == "__main__":
    main()
