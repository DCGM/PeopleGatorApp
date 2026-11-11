"""Consistent public Python lifecycle API for PR previews, staging and tagged releases.

Every CLI operation maps to one ``Environment`` method with the same semantics:

* read-only: ``preflight``, ``status``, ``check``, ``logs``
* lifecycle: ``update``, ``start``, ``stop``
* environment specific: PR ``cleanup``/``reconcile``; staging ``snapshot_init``/``refresh``;
  release ``database_migrate``/``recover``.

Settings come from ``DEPLOY_*`` variables (see :mod:`config`). Nothing is
installed or provisioned on the host: every operation first checks that the
operator-run infrastructure (Docker, networks and the shared PostgreSQL) is up,
then works under the environment's ``environment.lock``.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import re

from . import STATE_SCHEMA
from . import config
from .core import DeployError, lock, write_json
from .docker import Docker
from .host import positive_int

class Environment:
    def __init__(self, name):
        self.name = name
        self.settings = config.load(name)
        self.root = Path(self.settings["state_dir"])
        self.docker = Docker(self.settings.get("docker_context"))

    def command(self, operation):
        return f"people-gator-deploy {self.name} {operation}"

    @contextmanager
    def environment_lock(self):
        with lock(self.root / "environment.lock"):
            yield

    def journal(self, operation, phase, **extra):
        write_json(self.root / "operation.json", {"schema_version": STATE_SCHEMA, "operation": operation,
                                                  "phase": phase, **extra})

    # Controllers -------------------------------------------------------------

    def controller(self):
        if self.name == "release":
            from .release import Release
            result = Release(dict(self.settings))
        elif self.name == "staging":
            from .staging import Staging
            result = Staging(dict(self.settings))
        else:
            from .preview import Preview
            result = Preview(dict(self.settings))
        result.docker = self.docker
        return result

    def prerequisites(self, *, private=True):
        """Publish secret files and check the operator-run infrastructure, without changing it."""
        if private:
            self.root.mkdir(parents=True, mode=0o700, exist_ok=True)
            config.materialize(config.files(self.name, self.settings), self.root)
        self.docker.run(["docker", "info", "--format", "{{.Name}}"], timeout=30)
        version = self.docker.run(["docker", "compose", "version", "--short"], timeout=30).strip().lstrip("v")
        numbers = re.match(r"(\d+)\.(\d+)", version)
        if not numbers or tuple(map(int, numbers.groups())) < (2, 32):
            raise DeployError("Docker Compose 2.32+ is required")
        # The backend joins the collector's network only when OTel is configured.
        for key in ("web_network", "database_network", *(["otel_network"] if "otel" in self.settings else [])):
            try:
                self.docker.run(["docker", "network", "inspect", self.settings[key]], timeout=30)
            except DeployError:
                raise DeployError(f"{self.name}: Docker network {self.settings[key]!r} does not exist in context "
                                  f"{self.docker.context!r}; create it (deploy/GITHUB-SETUP.md)") from None
        controller = self.controller()
        host = self.settings.get("domain") or self.settings["host"]
        result = {"environment": self.name, "state_dir": str(self.root), "host": host, "configured": True,
                  "database": controller.check_database()}
        if self.name == "release" and self.settings["migration"] != self.settings["postgres"]:
            result["migration_database"] = controller.check_database("migration")
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a") as output:
                output.write(f"host={host}\n")
        return result

    def instance(self, controller, pr):
        """(compose.env, compose-command factory) for the selected application instance."""
        if self.name == "pr":
            if pr is None:
                raise DeployError("Select a preview instance with --pr <number>")
            number = positive_int(pr)
            directory = self.root / f"pr-{number}"
            return directory / "compose.env", lambda *args: controller.compose(number, directory / "compose.env", *args)
        if self.name == "staging":
            return self.root / "compose.env", lambda *args: controller.compose_staging(self.root / "compose.env", *args)
        return self.root / "compose.env", lambda *args: controller.compose_release(self.root / "compose.env", *args)

    def active(self, controller, pr):
        env, compose = self.instance(controller, pr)
        if not env.is_file():
            raise DeployError(f"{self.name}: {env}; no active application; run {self.command('update')} with a verified build")
        return compose

    def instances(self):
        """Preview numbers for PR; one implicit instance otherwise."""
        if self.name != "pr":
            return [None]
        return [positive_int(m[1]) for p in sorted(self.root.glob("pr-*"))
                if p.is_dir() and (m := re.fullmatch(r"pr-([1-9][0-9]*)", p.name))]

    def readiness(self, controller, pr):
        if self.name == "pr":
            controller.readiness(positive_int(pr))
        else:
            controller.readiness()

    # Read-only operations ------------------------------------------------------

    def preflight(self):
        """Settings, secret files and infrastructure for CI, before any mutation."""
        return self.prerequisites()

    def status(self, pr=None):
        """Configured, running and healthy are reported separately and never changed."""
        result = {"environment": self.name, "state_dir": str(self.root), "configured": True}
        controller = self.controller()
        numbers = self.instances() if pr is None else [positive_int(pr)]
        instances = []
        for number in numbers:
            env, compose = self.instance(controller, number)
            entry = {"running": False, "healthy": False, **({"pr": number} if number else {})}
            state = env.parent / "state.json"
            if state.exists():
                saved = json.loads(state.read_text())
                entry.update({key: saved[key] for key in ("sha", "images", "tag", "commit", "version") if key in saved})
            if env.is_file():
                services = self.docker.run(compose("ps", "--format", "json"), timeout=30)
                records = [json.loads(line) for line in services.splitlines() if line.strip()]
                if len(records) == 1 and isinstance(records[0], list):
                    records = records[0]
                entry["running"] = len(records) >= 2 and all(r.get("State") == "running" for r in records)
                if entry["running"]:
                    try:
                        if self.name == "pr":
                            from .host import routed_readiness
                            routed_readiness(controller.host(number), attempts=1)
                        else:
                            controller.readiness(attempts=1)
                        entry["healthy"] = True
                    except DeployError:
                        pass
            instances.append(entry)
        if self.name == "pr":
            result["instances"] = instances
        else:
            result.update(instances[0])
        return result

    def check(self, pr=None):
        """Full runtime-role database check plus routed readiness; nonzero when unhealthy."""
        self.prerequisites()
        controller = self.controller()
        if self.name == "pr" and pr is None:
            controller.check_access()
            return {"environment": self.name, "configured": True, "access": True}
        compose = self.active(controller, pr)
        self.docker.run(compose("run", "--rm", "--no-deps", "check"), diagnostic=controller.diagnostic_path())
        self.readiness(controller, pr)
        return {"environment": self.name, "configured": True, "healthy": True,
                **({"pr": positive_int(pr)} if pr else {})}

    def logs(self, pr=None, *, tail=200):
        """Explicit private operator action; callers must keep the output private."""
        compose = self.active(self.controller(), pr)
        return self.docker.run(compose("logs", "--no-color", "--tail", str(positive_int(tail))), timeout=60)

    # Lifecycle -------------------------------------------------------------------

    def require_fresh_application_project(self):
        """A first deployment cannot adopt another application's Compose stack."""
        if self.name == "pr":
            return  # deploy_pr removes the selected PR's old containers before redeployment.
        if (self.root / "compose.env").exists() or (self.root / "activation.json").exists():
            return  # Retained applications and interrupted activations are ours.
        project = "people-gator-" + self.name
        resources = self.docker.run(["docker", "ps", "-aq", "--filter",
                                     "label=com.docker.compose.project=" + project])
        if resources.strip():
            raise DeployError(f"Containers of Compose project {project} already exist without owned application "
                              f"state; remove them before {self.command('update')}")

    def update(self, *, sha=None, pr=None, tag=None, backup_record=None):
        """Deploy the images built for ``sha``."""
        if self.name == "pr" and (not sha or pr is None):
            raise DeployError("pr update requires --pr <open-PR-number> and --sha <tested-commit>")
        if self.name == "staging" and not sha:
            raise DeployError("staging update requires --sha <current-main-commit>")
        if self.name == "release" and not tag:
            raise DeployError("release update requires --tag <release-tag>")
        return self._deploy("update", sha=sha, pr=pr, tag=tag, backup_record=backup_record)

    def snapshot_init(self, *, sha=None):
        """Explicit one-time staging population from a verified snapshot."""
        if not sha:
            raise DeployError("staging snapshot-init requires --sha <current-main-commit>")
        return self._deploy("snapshot-init", sha=sha)

    def refresh(self, *, sha=None, backup_record=None):
        """Replace staging data with a new snapshot generation (explicit destructive intent)."""
        if not sha:
            raise DeployError("staging refresh requires --sha <current-main-commit>")
        self.private_record(backup_record, "refresh", "retained-state backup and replacement intent")
        return self._deploy("refresh", sha=sha)

    def recover(self, *, backup_record=None, compatibility_reviewed=False):
        """Release-only explicit recovery to the retained previous images."""
        self.private_record(backup_record, "recover", "the backup taken before the failed or replaced release")
        if not compatibility_reviewed:
            raise DeployError("recover requires --compatibility-reviewed: images cannot undo migrations; "
                              "the database check must accept the retained image")
        return self._deploy("recover", backup_record=backup_record)

    def private_record(self, record, operation, meaning):
        if not record or not Path(record).is_absolute() or not config.private_file(Path(record)):
            raise DeployError(f"{operation} requires --backup-record <absolute private mode-600 file> recording {meaning}")

    def _deploy(self, operation, **options):
        self.prerequisites()
        with self.environment_lock():
            if operation == "snapshot-init" and (self.root / "state.json").exists():
                raise DeployError(f"Staging snapshot already initialized; replacing it requires "
                                  f"{self.command('refresh')} --backup-record <path>")
            self.require_fresh_application_project()
            controller = self.controller()
            self.journal(operation, "preparing", **{k: v for k, v in options.items() if k in {"sha", "pr", "tag"} and v})
            with self.docker.registry():
                try:
                    if self.name == "pr":
                        result = {"deployed": controller.deploy(options["sha"], options["pr"])}
                    elif self.name == "staging":
                        controller.deploy(options["sha"], refresh=operation in {"refresh", "snapshot-init"})
                        result = {}
                    elif operation == "recover":
                        result = controller.recover()
                    else:
                        result = controller.deploy(options["tag"], sha=options.get("sha"),
                                                   backup_record=options.get("backup_record"))
                except BaseException:
                    self.journal(operation, "failed")
                    raise
            self.journal(operation, "complete")
        return {"environment": self.name, "operation": operation, "complete": True, **(result or {})}

    def stop(self, pr=None):
        self.prerequisites(private=False)
        with self.environment_lock():
            controller = self.controller()
            for number in (self.instances() if self.name == "pr" and pr is None else [pr]):
                self.docker.run(self.active(controller, number)("stop", "--timeout", "30"))
        return {"environment": self.name, "stopped": True, "data_preserved": True}

    def start(self, pr=None):
        """Restart the recorded images after the same schema and readiness gates as deployment."""
        self.prerequisites()
        with self.environment_lock():
            controller = self.controller()
            compose = self.active(controller, pr)
            self.docker.run(compose("run", "--rm", "--no-deps", "check"), diagnostic=controller.diagnostic_path())
            self.docker.run(compose("up", "-d", "--wait", "--wait-timeout", "180", "backend", "frontend"))
            self.readiness(controller, pr)
        return {"environment": self.name, "started": True, "healthy": True}

    def cleanup(self, pr):
        """Remove one closed PR preview, including its database, role and storage."""
        if pr is None:
            raise DeployError("cleanup requires --pr <closed-PR-number>")
        self.prerequisites(private=False)  # a dead PostgreSQL would leave a half-removed preview
        with self.environment_lock():
            removed = self.controller().cleanup(pr)
        return {"environment": self.name, "pr": positive_int(pr), "removed": removed}

    def reconcile(self):
        """Remove previews whose PRs GitHub reports closed; API errors never imply closure."""
        self.prerequisites(private=False)
        with self.environment_lock():
            removed = self.controller().reconcile()
        return {"environment": self.name, "removed": removed}

    def database_migrate(self, *, backup_record=None):
        """Release-only explicit migration with the migration role, then a full runtime-role check."""
        self.private_record(backup_record, "database-migrate", "a completed pre-migration backup")
        self.prerequisites()
        with self.environment_lock():
            controller = self.controller()
            compose = self.active(controller, None)
            self.docker.run(compose("run", "--rm", "--no-deps", "migrate"), diagnostic=controller.diagnostic_path())
            self.docker.run(compose("run", "--rm", "--no-deps", "check"), diagnostic=controller.diagnostic_path())
        return {"environment": self.name, "migrated": True}

    # Dispatch ------------------------------------------------------------------------

    def execute(self, operation, **options):
        handlers = {
            "preflight": lambda: self.preflight(),
            "status": lambda: self.status(options.get("pr")),
            "check": lambda: self.check(options.get("pr")),
            "logs": lambda: self.logs(options.get("pr"), tail=options.get("tail") or 200),
            "update": lambda: self.update(sha=options.get("sha"), pr=options.get("pr"), tag=options.get("tag"),
                                          backup_record=options.get("backup_record")),
            "start": lambda: self.start(options.get("pr")),
            "stop": lambda: self.stop(options.get("pr")),
            "cleanup": lambda: self.cleanup(options.get("pr")),
            "reconcile": self.reconcile,
            "snapshot-init": lambda: self.snapshot_init(sha=options.get("sha")),
            "refresh": lambda: self.refresh(sha=options.get("sha"), backup_record=options.get("backup_record")),
            "database-migrate": lambda: self.database_migrate(backup_record=options.get("backup_record")),
            "recover": lambda: self.recover(backup_record=options.get("backup_record"),
                                            compatibility_reviewed=options.get("compatibility_reviewed", False)),
        }
        if operation not in handlers or operation not in OPERATIONS[self.name]:
            raise DeployError(f"Unsupported {self.name} operation: {operation}")
        return handlers[operation]()


COMMON = ("preflight", "status", "check", "logs", "update", "start", "stop")
OPERATIONS = {
    "pr": (*COMMON, "cleanup", "reconcile"),
    "staging": (*COMMON, "snapshot-init", "refresh"),
    "release": (*COMMON, "database-migrate", "recover"),
}
