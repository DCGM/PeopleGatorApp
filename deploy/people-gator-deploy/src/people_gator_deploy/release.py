"""Tagged application releases: exact tested commit and digests on a production stack.

A release tag selects its commit through the GitHub API (annotated or
lightweight). The commit must be on main and have a successful main-push CI
run; that run's images are promoted by digest. Routine updates never seed,
restore or replace data. Migrations require a recorded backup, then a full
runtime-role check, backend startup and routed readiness gate activation.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import secrets

from .core import DeployError
from .host import INSTALL_DIR, Host, IneligibleRun, positive_int, routed_readiness, summary, write_private
from . import config as descriptors

TAG = re.compile(r"v[0-9]+(?:\.[0-9]+){0,3}(?:[-+][0-9A-Za-z.-]{1,64})?")
FIXED = {"PEOPLE_GATOR_API__HOST", "PEOPLE_GATOR_API__PORT", "PEOPLE_GATOR_API__DEBUG", "PEOPLE_GATOR_API__RELOAD",
         "PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__SCHEMA_MODE", "PEOPLE_GATOR_API__CORS__ALLOW_ORIGIN_REGEX"}


def env_keys(path: Path) -> set[str]:
    keys = set()
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, _ = line.partition("=")
        if not separator or not re.fullmatch(r"PEOPLE_GATOR_API__[A-Z0-9_]+", key):
            raise DeployError(f"{path}: only PEOPLE_GATOR_API__* KEY=value lines are supported")
        keys.add(key)
    return keys


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

    # Installation -------------------------------------------------------

    def validate_inputs(self):
        runtime, migration = Path(self.config["runtime_file"]), Path(self.config["migration_file"])
        if runtime.resolve() == migration.resolve():
            raise DeployError("runtime_file and migration_file must be separate private files")
        for path in (runtime, migration):
            if not descriptors.private_file(path):
                raise DeployError(f"{path}: needs an owned mode-600 API environment file")
            overridden = env_keys(path) & FIXED
            if overridden:
                raise DeployError(f"{path}: remove deployment-fixed settings {', '.join(sorted(overridden))}")
        if not any(key.startswith("PEOPLE_GATOR_API__PERSISTENCE") for key in env_keys(migration)):
            raise DeployError(f"{migration}: define the migration role's PostgreSQL connection")
        keys = env_keys(runtime)
        for prefix in ("PEOPLE_GATOR_API__PERSISTENCE", "PEOPLE_GATOR_API__STORAGE"):
            if not any(key.startswith(prefix) for key in keys):
                raise DeployError(f"{runtime}: define {prefix}* for the runtime role and private storage")

    def install(self):
        """External PostgreSQL/storage/proxy are checked, never created or deleted."""
        self.validate_inputs()
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)

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

    def eligible(self, tag: str, *, commit: str | None = None, run_id: int | None = None) -> tuple[str, dict]:
        self.check_access()
        resolved = self.tag_commit(tag)
        if commit and commit != resolved:
            raise DeployError(f"Release tag {tag} moved from {commit} to {resolved}; refusing a moved tag")
        if not self.contains(resolved, "main"):
            raise DeployError(f"Release tag {tag} ({resolved}) is not on main; only reviewed main commits are released")
        if run_id is None:
            runs = self.api(f"actions/workflows/pr-ci.yml/runs?head_sha={resolved}&event=push&branch=main"
                            "&status=success&per_page=20")["workflow_runs"]
            if not runs:
                raise IneligibleRun(f"No successful main-push PR CI run built {resolved}; push it to main and "
                                    "wait for CI, or pass --run-id")
            run_id = max(run["id"] for run in runs)
        run = self.ci_run(run_id, event="push", branch="main")
        if run["head_sha"] != resolved:
            raise IneligibleRun(f"Run {run_id} built {run['head_sha']}, not tagged commit {resolved}")
        return resolved, run

    # Deployment ---------------------------------------------------------

    def values(self, tag: str, commit: str, images: dict) -> dict:
        return {"RELEASE_TAG": tag, "COMMIT_SHA": commit, "RELEASE_HOST": self.host,
                "BACKEND_IMAGE": images["backend"], "FRONTEND_IMAGE": images["frontend"],
                "RUNTIME_FILE": self.config["runtime_file"], "MIGRATION_FILE": self.config["migration_file"],
                "DATABASE_NETWORK": self.config["database_network"], "WEB_NETWORK": self.config["web_network"],
                "CERTIFICATE_RESOLVER": self.config.get("certificate_resolver", "tlschallenge"),
                "CORS_ORIGIN_REGEX": f"^https://{re.escape(self.host)}$",
                "BACKEND_MEMORY": self.config.get("backend_memory", "4g")}

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
        if pending.get("previous"):
            write_private(self.root / "previous.json", json.dumps(pending["previous"]))
            write_private(self.root / "previous.env", pending["previous_environment"])
        write_private(self.root / "state.json", json.dumps(record))
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

    def deploy(self, tag: str, *, commit: str | None = None, run_id: int | None = None, backup_record=None) -> dict:
        self.validate_inputs()
        self.reconcile_activation()
        journal = self.root / "activation.json"
        if journal.exists() and self.pending_activation()["record"]["tag"] != tag:
            raise DeployError(f"{journal}: an interrupted activation of another tag needs operator review; "
                              "inspect status, then rerun that tag's update or use recover")
        resolved, run = self.eligible(tag, commit=commit, run_id=run_id)
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
            if not backup_record or not descriptors.private_file(Path(backup_record)):
                raise DeployError(f"Release {tag} needs a schema migration (or the database is unreachable). Take and "
                                  "verify a database backup, then rerun with --backup-record <private file>; "
                                  "see `release check` diagnostics in " + str(self.diagnostic_path()))
            self.command(self.compose_release(candidate, "run", "--rm", "--no-deps", "migrate"))
            self.command(self.compose_release(candidate, "run", "--rm", "--no-deps", "check"))
        record = {"tag": tag, "commit": resolved, "images": images,
                  "version": [positive_int(run["id"]), positive_int(run["run_attempt"])],
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
        self.validate_inputs()
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
