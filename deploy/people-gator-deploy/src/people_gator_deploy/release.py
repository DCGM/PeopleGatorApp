"""Tagged application releases: exact tested commit and digests on a production stack.

A release tag selects its commit through the GitHub API (annotated or
lightweight). The commit must be on main and must be the one this workflow run
tested and published as ``sha-<commit>`` images, which are pinned by digest.
Routine updates never seed, restore or replace data. Migrations require a
recorded backup, then a full runtime-role check, backend startup and routed
readiness gate activation.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import secrets

from .core import DeployError
from .host import INSTALL_DIR, Host, routed_readiness, summary, write_private
from . import config

TAG = re.compile(r"v[0-9]+(?:\.[0-9]+){0,3}(?:[-+][0-9A-Za-z.-]{1,64})?")


class Release(Host):
    def __init__(self, config: dict):
        super().__init__(config)
        self.host = config["host"]
        self.project = config.get("project", "people-gator-release")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", self.project):
            raise DeployError("Invalid release Compose project")

    def diagnostic_path(self):
        return self.root / "last-error.log"

    def compose_release(self, env_file: Path, *args: str) -> list[str]:
        return ["docker", "compose", "--project-name", self.project, "--env-file", str(env_file),
                "-f", str(INSTALL_DIR / "compose.release.yaml"), *args]

    # Provenance ---------------------------------------------------------

    def tag_commit(self, tag: str) -> str:
        if not TAG.fullmatch(tag or ""):
            raise DeployError(f"Release tag {tag!r} does not match the documented v<major>.<minor>.<patch> pattern")
        ref = self.api(f"git/ref/tags/{tag}")["object"]
        for _ in range(4):  # annotated tags may point at other tag objects
            if ref["type"] == "commit":
                return ref["sha"]
            if ref["type"] != "tag":
                raise DeployError(f"Release tag {tag} does not reference a commit")
            ref = self.api(f"git/tags/{ref['sha']}")["object"]
        raise DeployError(f"Release tag {tag} has too many tag indirections")

    def contains(self, base: str, head: str) -> bool:
        """True when ``head`` includes ``base`` (equal or descendant)."""
        return self.api(f"compare/{base}...{head}")["status"] in {"identical", "ahead"}

    def eligible(self, tag: str, *, sha: str | None = None) -> tuple[str, dict]:
        self.check_access()
        resolved = self.tag_commit(tag)
        if sha and sha != resolved:
            raise DeployError(f"Release tag {tag} moved from {sha} to {resolved}; refusing a moved tag")
        if not self.contains(resolved, "main"):
            raise DeployError(f"Release tag {tag} ({resolved}) is not on main; only reviewed main commits are released")
        return resolved, self.build(resolved)

    # Deployment ---------------------------------------------------------

    def values(self, tag: str, commit: str, images: dict) -> dict:
        return {"RELEASE_TAG": tag, "COMMIT_SHA": commit, "RELEASE_HOST": self.host,
                "BACKEND_IMAGE": images["backend"], "FRONTEND_IMAGE": images["frontend"],
                "RUNTIME_FILE": self.config["runtime_file"], "MIGRATION_FILE": self.config["migration_file"],
                "DATABASE_NETWORK": self.config.get("database_network", "db"),
                "WEB_NETWORK": self.config.get("web_network", "web"),
                "CORS_ORIGIN_REGEX": f"^https://{re.escape(self.host)}$",
                "BACKEND_MEMORY": self.config.get("backend_memory", "4g"),
                "TELEMETRY_FILE": self.config.get("telemetry_file", "/dev/null"),
                "APPLICATION_OTEL_NETWORK": self.config["otel_network"] if "otel" in self.config else self.config.get("web_network", "web")}

    def state(self, name="state.json"):
        path = self.root / name
        return json.loads(path.read_text()) if path.exists() else None

    def readiness(self, attempts=30):
        routed_readiness(self.host, attempts=attempts)

    def schema_current(self, candidate: Path) -> bool:
        """The runtime-role check passes only when the schema matches this image's head."""
        try:
            self.command(self.compose_release(candidate, "run", "--rm", "--no-deps", "check"))
            return True
        except DeployError:
            return False

    def pending_activation(self):
        pending = self.state("activation.json")
        if pending and "record" not in pending:
            # Read journals written by the original package before its commit
            # protocol included the full environment and recovery target.
            pending = {"record": {k: v for k, v in pending.items() if k != "candidate"},
                       "environment": Path(pending["candidate"]).read_text()}
        return pending

    def finish_activation(self, pending):
        """Complete the file publication idempotently after routed readiness."""
        record = pending["record"]
        # State is the commit point. Before it succeeds, recovery must still
        # find the older rollback pair. Afterward, the journal can finish every
        # remaining write before update/recover selects a release.
        write_private(self.root / "state.json", json.dumps(record))
        if pending.get("previous"):
            write_private(self.root / "previous.json", json.dumps(pending["previous"]))
            write_private(self.root / "previous.env", pending["previous_environment"])
        write_private(self.root / "compose.env", pending["environment"])
        history = self.root / "history.jsonl"
        lines = history.read_text().splitlines() if history.exists() else []
        if not lines or json.loads(lines[-1]) != record:
            # Atomic replacement also prevents a partial JSONL tail on interruption.
            write_private(history, "".join(line + "\n" for line in lines) + json.dumps(record) + "\n")
        (self.root / "activation.json").unlink()

    def reconcile_activation(self):
        pending = self.pending_activation()
        if pending and self.state() == pending["record"]:
            # State is the commit point. A retry must finish publishing compose
            # and history before returning "already deployed" or accepting a tag.
            self.finish_activation(pending)

    def activate(self, candidate: Path, record: dict):
        current = self.state()
        record = {**record, "activation": secrets.token_hex(16)}
        # Recovering an uncommitted candidate reactivates the current healthy
        # release. Keep its older recovery target rather than replacing it with
        # a duplicate of itself.
        replaced = current if current and any(current.get(key) != record.get(key)
                                              for key in ("tag", "commit", "images")) else None
        pending = {"record": record, "environment": candidate.read_text(), "previous": replaced,
                   "previous_environment": (self.root / "compose.env").read_text() if replaced else None}
        write_private(self.root / "activation.json", json.dumps(pending))
        self.command(self.compose_release(candidate, "config", "--quiet"))
        self.command(self.compose_release(candidate, "up", "-d", "--wait", "--wait-timeout", "300", "backend"))
        self.command(self.compose_release(candidate, "up", "-d", "--wait", "--wait-timeout", "180", "frontend"))
        self.readiness()
        self.finish_activation(pending)

    def deploy(self, tag: str, *, sha: str | None = None, backup_record=None) -> dict:
        self.reconcile_activation()
        journal = self.root / "activation.json"
        if journal.exists() and self.pending_activation()["record"]["tag"] != tag:
            raise DeployError(f"{journal}: an interrupted activation of another tag needs operator review; "
                              "inspect status, then rerun that tag's update or use recover")
        resolved, run = self.eligible(tag, sha=sha)
        current = self.state()
        if current and current["tag"] == tag:
            if current["commit"] != resolved:
                raise DeployError(f"Release tag {tag} was deployed at {current['commit']} and now names {resolved}; "
                                  "moved tags are rejected")
            print(f"Release {tag} ({resolved}) is already deployed")
            return {"tag": tag, "commit": resolved, "changed": False}
        if current and not self.contains(current["commit"], resolved):
            raise DeployError(f"Release {tag} ({resolved}) does not contain the deployed {current['tag']} "
                              f"({current['commit']}); older or diverged retries cannot replace it without recover")
        images = {part: self.image(part, run) for part in ("frontend", "backend")}
        candidate = self.root / "candidate.env"
        write_private(candidate, self.dotenv(self.values(tag, resolved, images)))
        self.command(self.compose_release(candidate, "config", "--quiet"))
        if not self.schema_current(candidate):
            if not backup_record or not config.private_file(Path(backup_record)):
                raise DeployError(f"Release {tag} needs a schema migration (or the database is unreachable). Take and "
                                  "verify a database backup, then rerun with --backup-record <private file>; "
                                  "see `release check` diagnostics in " + str(self.diagnostic_path()))
            self.command(self.compose_release(candidate, "run", "--rm", "--no-deps", "migrate"))
            self.command(self.compose_release(candidate, "run", "--rm", "--no-deps", "check"))
        record = {"tag": tag, "commit": resolved, "images": images,
                  "version": [int(run.get("id") or 0), int(run.get("run_attempt") or 0)],
                  **({"backup_record": str(backup_record)} if backup_record else {})}
        self.activate(candidate, record)
        url = f"https://{self.host}"
        print(f"Release {tag} ready: {url} · {resolved}")
        summary(f"Release {tag}: [{url}]({url}) · `{resolved}`\n\n"
                + "".join(f"- {part}: `{image}`\n" for part, image in images.items()) + "\n")
        return {"tag": tag, "commit": resolved, "images": images, "changed": True}

    def recover(self) -> dict:
        """Reactivate the retained previous images when the database check accepts them.

        Changing images never undoes migrations: an older image whose check
        rejects the current schema is refused, and no downgrade is attempted.
        """
        self.reconcile_activation()
        pending = self.pending_activation()
        if pending and pending["record"].get("recovered"):
            # Retry the same recovery if its startup/readiness was interrupted.
            previous, environment = pending["record"], pending["environment"]
        else:
            # A failed candidate never became the committed release. Recover
            # the last healthy state, rather than skipping back one more release.
            previous = self.state() if pending else self.state("previous.json")
            env = self.root / ("compose.env" if pending else "previous.env")
            environment = env.read_text() if env.exists() else None
        if not previous or environment is None:
            raise DeployError("No retained previous release to recover")
        candidate = self.root / "recovery.env"
        write_private(candidate, environment)
        if not self.schema_current(candidate):
            raise DeployError(f"The retained release {previous['tag']} rejects the current database schema; "
                              "restore the recorded backup into the database explicitly or roll forward")
        record = {**previous, "recovered": True}
        self.activate(candidate, record)
        print(f"Recovered release {previous['tag']} ({previous['commit']})")
        return {"tag": previous["tag"], "commit": previous["commit"], "recovered": True}
