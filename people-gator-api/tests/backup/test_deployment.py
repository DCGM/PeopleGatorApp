"""Deployment boundaries are part of the backup credential contract."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.skipif(shutil.which("docker") is None, reason="Docker Compose is required")
def test_opt_in_agent_preserves_project_and_isolates_private_config(tmp_path):
    for name in ("compose.dev.yaml", "compose.live-preview.yaml", "deploy/backup/compose.agent.yaml"):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, path)
    (tmp_path / ".env").write_text("AWS_ACCESS_KEY_ID=application-only-sentinel\nPOSTGRES_PASSWORD=fixture\n")
    environment = {key: value for key, value in os.environ.items() if not key.startswith(("COMPOSE_", "BACKUP_", "AWS_"))}
    def render(files):
        args = ["docker", "compose", "--project-directory", str(tmp_path), "--env-file", "/dev/null"]
        for name in files:
            args += ["-f", str(tmp_path / name)]
        result = subprocess.run([*args, "--profile", "backups", "config", "--format", "json"],
                                env=environment, capture_output=True, check=True)
        return json.loads(result.stdout)
    rendered = render(["compose.live-preview.yaml", "deploy/backup/compose.agent.yaml"])
    assert rendered["name"] == "people-gator-live-preview"
    agent = rendered["services"]["backup-agent"]
    assert agent["profiles"] == ["backups"]
    assert agent.get("environment", {}) == {}
    assert agent["read_only"] and agent["cap_drop"] == ["ALL"]
    assert set(agent["networks"]) == {"backup-source"}
    mounts = agent["volumes"]
    assert {mount["target"] for mount in mounts} == {"/state", "/run/backup-publisher.json"}
    private = next(mount for mount in mounts if mount["type"] == "bind")
    assert private["read_only"] and not private["bind"]["create_host_path"]
    assert private["source"] == "/opt/people-gator-staging/backup-publisher.json"
    for name in ("frontend", "backend", "db"):
        encoded = json.dumps(rendered["services"][name])
        assert "backup-publisher" not in encoded and "backup-restore" not in encoded
    standalone = render(["deploy/backup/compose.agent.yaml"])
    assert standalone["services"]["backup-agent"]["build"]["context"] == str(tmp_path)


def test_three_identity_policies_keep_backup_reader_read_only_and_buckets_separate():
    directory = ROOT / "deploy" / "backup"
    policies = {name: json.loads((directory / (name + "-policy.example.json")).read_text()) for name in ("publisher", "restore", "staging")}
    for name, policy in policies.items():
        resources = [statement["Resource"] for statement in policy["Statement"]]
        bucket = "peoplegator-staging" if name == "staging" else "peoplegator-db-backup"
        assert all(resource in {"arn:aws:s3:::" + bucket, "arn:aws:s3:::" + bucket + "/*",
                               "arn:aws:s3:::" + bucket + "/production/db-backups/*"} for resource in resources)
        actions = {action for statement in policy["Statement"] for action in statement["Action"]}
        assert "s3:ListBucket" in actions
        if name == "restore":
            assert actions == {"s3:ListBucket", "s3:GetObject", "s3:GetObjectVersion"}
        if name == "publisher":
            assert "s3:PutObject" in actions and "s3:AbortMultipartUpload" in actions
            assert "s3:DeleteObject" not in actions
        if name == "staging":
            assert {"s3:GetObject", "s3:PutObject", "s3:DeleteObject"} <= actions
