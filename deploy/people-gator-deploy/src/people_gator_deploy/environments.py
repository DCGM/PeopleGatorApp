"""Consistent public Python lifecycle API for PR previews, staging and tagged releases.

Every CLI operation maps to one ``Environment`` method with the same semantics:

* read-only: ``preflight``, ``status``, ``check``, ``logs``, ``migration_inspect``
* lifecycle: ``install``, ``update``, ``uninstall``, ``start``, ``stop``
* environment specific: PR ``cleanup``/``reconcile``; staging ``snapshot_init``/``refresh``;
  release ``database_migrate``/``recover``; shared ``infra_upgrade`` and ``adopt``.

Lock order: per-environment ``environment.lock`` first, then the shared
infrastructure ``controller.lock`` (shared for environment work, exclusive for
infrastructure changes and legacy controllers). Package installation uses its
own lock and never waits on either.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re

from . import STATE_SCHEMA
from . import config
from .core import DeployError, lock, write_json
from .docker import Docker
from .host import positive_int

LEGACY_FIELDS = {
    "pr": ("domain", "users_file", "database_network", "web_network", "certificate_resolver",
           "preview_log_port", "otel_network", "otel_http_endpoint", "pgadmin_host", "pgadmin_email"),
    "staging": ("host", "private_dir"),
}


class Environment:
    def __init__(self, name, path=None):
        if name not in config.ENVIRONMENTS:
            raise DeployError(f"Unknown environment {name!r}; choose one of {', '.join(config.ENVIRONMENTS)}")
        self.name = name
        self.path = config.selected(name, path)
        self.settings = config.read(name, self.path)
        self.root = Path(self.settings["state_dir"])
        self.docker = Docker(self.settings["docker_context"])
        self.identity = hashlib.sha256(str(self.path.resolve()).encode()).hexdigest()

    def command(self, operation):
        return f"people-gator-deploy {self.name} {operation} --config '{self.path}'"

    # Ownership and state ---------------------------------------------------

    @property
    def infrastructure_root(self) -> Path | None:
        if self.name == "release":
            return None
        return Path(self.settings["infrastructure"]["state_dir"])

    def marker(self):
        path = self.root / "owned.json"
        if not path.exists():
            return None
        if not config.private_file(path):
            raise DeployError(f"{self.name}: {path}; ownership marker must be private and owned by this account")
        value = json.loads(path.read_text())
        if value.get("schema_version") != STATE_SCHEMA:
            raise DeployError(f"{path}; unsupported state schema; upgrade the utility or explicitly migrate state")
        if value.get("owner") != self.identity or value.get("environment") != self.name:
            raise DeployError(f"{path}; resources belong to another descriptor; run {self.command('migration-inspect')}")
        return value

    def mark(self, phase, **extra):
        previous = self.marker() or {}
        write_json(self.root / "owned.json", {**previous, **extra, "schema_version": STATE_SCHEMA,
                                              "owner": self.identity, "environment": self.name, "phase": phase})

    def require_installed(self):
        marker = self.marker()
        if not marker or marker.get("phase") != "installed":
            raise DeployError(f"{self.name}: {self.path}; resources are not installed; run {self.command('install')}")
        return marker

    def infrastructure_owner(self):
        path = self.infrastructure_root / "infrastructure-owned.json"
        return json.loads(path.read_text()) if path.exists() else None

    @contextmanager
    def environment_lock(self, *, installed=True):
        # Refuse before the lock file could create directories for an uninstalled environment.
        if installed:
            self.require_installed()
        with lock(self.root / "environment.lock"):
            yield

    def shared_lock(self, *, exclusive=False):
        # Preserve the original controller.lock inode throughout host transition.
        root = self.infrastructure_root or self.root
        return lock(root / "controller.lock", shared=not exclusive)

    def journal(self, operation, phase, **extra):
        write_json(self.root / "operation.json", {"schema_version": STATE_SCHEMA, "operation": operation,
                                                  "phase": phase, **extra})

    # Controllers -------------------------------------------------------------

    def controller(self):
        values = dict(self.settings)
        if self.name == "release":
            from .release import Release
            result = Release(values)
        else:
            infra = values["infrastructure"]
            values["infrastructure_project"] = infra["project"]
            values["state_dir"] = infra["state_dir"]
            if self.name == "staging":
                from .staging import Staging
                values["staging"] = {"state_dir": str(self.root), "private_dir": values["private_dir"],
                                     "host": values["host"]}
                result = Staging(values)
            else:
                from .preview import Preview
                values["previews_dir"] = str(self.root)
                result = Preview(values)
        result.docker = self.docker
        return result

    def prerequisites(self, *, private=True):
        """Validate what every operation needs, without changing anything."""
        config.read(self.name, self.path, inputs=private)
        self.docker.run(["docker", "info", "--format", "{{.Name}}"], timeout=30)
        version = self.docker.run(["docker", "compose", "version", "--short"], timeout=30).strip().lstrip("v")
        numbers = re.match(r"(\d+)\.(\d+)", version)
        if not numbers or tuple(map(int, numbers.groups())) < (2, 32):
            raise DeployError("Docker Compose 2.32+ is required")
        for key in ("web_network", "otel_network", *(("database_network",) if self.name == "release" else ())):
            if self.settings.get(key):
                try:
                    self.docker.run(["docker", "network", "inspect", self.settings[key]], timeout=30)
                except DeployError:
                    raise DeployError(f"{self.name}: Docker network {self.settings[key]!r} ({key}) is unavailable "
                                      f"in context {self.settings['docker_context']!r}; create it or fix {self.path}") from None

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
        """Configuration completeness and host prerequisites for CI, before any mutation."""
        self.prerequisites()
        marker = self.marker()
        result = {"environment": self.name, "config": str(self.path), "scope": config.installation()["scope"],
                  "configured": True, "provisioned": bool(marker and marker.get("phase") == "installed")}
        if not result["provisioned"]:
            raise DeployError(f"{self.name}: {self.path}; configured but not installed; an operator must run {self.command('install')}")
        if self.name != "release" and not (self.infrastructure_root / "infrastructure.env").is_file():
            raise DeployError(f"{self.infrastructure_root}/infrastructure.env; shared infrastructure is uninitialized; "
                              f"its owner must run people-gator-deploy <environment> install")
        return result

    def status(self, pr=None):
        """Configured, provisioned, running and healthy are reported separately and never changed."""
        marker = self.marker()
        result = {"environment": self.name, "config": str(self.path), "scope": config.installation()["scope"],
                  "configured": True, "provisioned": bool(marker and marker.get("phase") == "installed"),
                  "phase": (marker or {}).get("phase", "not-installed")}
        if not result["provisioned"]:
            return result
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
        self.require_installed()
        controller = self.controller()
        if self.name == "pr" and pr is None:
            controller.check_access()
            controller.sql("SELECT 1;")
            return {"environment": self.name, "configured": True, "provisioned": True, "access": True}
        compose = self.active(controller, pr)
        with self.shared_lock():
            self.docker.run(compose("run", "--rm", "--no-deps", "check"), diagnostic=controller.diagnostic_path())
            self.readiness(controller, pr)
        return {"environment": self.name, "configured": True, "provisioned": True, "healthy": True,
                **({"pr": positive_int(pr)} if pr else {})}

    def logs(self, pr=None, *, tail=200):
        """Explicit private operator action; callers must keep the output private."""
        self.require_installed()
        compose = self.active(self.controller(), pr)
        return self.docker.run(compose("logs", "--no-color", "--tail", str(positive_int(tail))), timeout=60)

    # Lifecycle -------------------------------------------------------------------

    def install(self):
        """Provision managed resources once; repeating it changes nothing."""
        self.prerequisites()
        self.root.mkdir(parents=True, mode=0o700, exist_ok=True)
        with self.environment_lock(installed=False), self.shared_lock(exclusive=True):
            old = self.marker()
            if old and old.get("phase") == "installed":
                return {"environment": self.name, "installed": True, "changed": False}
            # Refuse silent adoption, including data that predates the package.
            existing = [p for p in self.root.iterdir()
                        if p.name not in {"environment.lock", "controller.lock", "owned.json"}]
            if existing and not old:
                raise DeployError(f"{self.root}; existing resources require {self.command('migration-inspect')} "
                                  "--legacy-config <path>, then explicit adopt")
            controller = self.controller()
            infra = self.settings.get("infrastructure", {})
            owner = self.infrastructure_owner() if self.name != "release" else None
            # Refusals happen before this environment records any ownership.
            if infra.get("mode") == "managed" and owner and owner.get("owner") != self.identity:
                raise DeployError(f"{self.infrastructure_root}; shared infrastructure belongs to another "
                                  "environment; configure infrastructure.mode=external")
            if infra.get("mode") == "external" and not (self.infrastructure_root / "infrastructure.env").is_file():
                raise DeployError(f"{self.infrastructure_root}/infrastructure.env; external infrastructure is "
                                  "uninitialized; its owning environment must run install first")
            self.mark("installing")
            if self.name == "release":
                controller.install()
            else:
                if infra["mode"] == "managed":
                    if not owner:
                        if (self.infrastructure_root / "infrastructure.env").exists():
                            raise DeployError(f"{self.infrastructure_root}; existing infrastructure requires explicit adopt")
                        # Do not adopt an existing Compose project based only on a matching name.
                        resources = self.docker.run(["docker", "ps", "-aq", "--filter",
                                                     "label=com.docker.compose.project=" + infra["project"]])
                        if resources.strip():
                            raise DeployError(f"Existing {infra['project']} containers require explicit adopt")
                        write_json(self.infrastructure_root / "infrastructure-owned.json",
                                   {"owner": self.identity, "environment": self.name,
                                    "project": infra["project"], "schema_version": STATE_SCHEMA})
                    controller.init()
                else:
                    controller.sql("SELECT 1;")
            self.mark("installed")
        return {"environment": self.name, "installed": True, "changed": True}

    def update(self, *, run_id=None, tag=None, commit=None, backup_record=None):
        """Deploy a verified application build with already provisioned resources."""
        if self.name == "pr" and not run_id:
            raise DeployError("pr update requires --run-id <successful-PR-CI-run>")
        if self.name == "release" and not tag:
            raise DeployError("release update requires --tag <release-tag>")
        return self._deploy("update", run_id=run_id, tag=tag, commit=commit, backup_record=backup_record)

    def snapshot_init(self, *, run_id=None, exact_key=""):
        """Explicit one-time staging population from a verified snapshot."""
        if (self.root / "state.json").exists():
            raise DeployError(f"Staging snapshot already initialized; replacing it requires {self.command('refresh')} --backup-record <path>")
        return self._deploy("snapshot-init", run_id=run_id, exact_key=exact_key)

    def refresh(self, *, run_id=None, exact_key="", backup_record=None):
        """Replace staging data with a new snapshot generation (explicit destructive intent)."""
        self.private_record(backup_record, "refresh", "retained-state backup and replacement intent")
        return self._deploy("refresh", run_id=run_id, exact_key=exact_key)

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
            self.require_installed()
            controller = self.controller()
            self.journal(operation, "preparing", **{k: v for k, v in options.items() if k in {"run_id", "tag", "commit"} and v})
            # Long snapshot preparation holds the shared lock only in shared mode,
            # so previews keep deploying; infrastructure upgrades wait.
            with self.shared_lock(), self.docker.registry():
                try:
                    if self.name == "pr":
                        result = {"deployed": controller.deploy(options["run_id"])}
                    elif self.name == "staging":
                        controller.deploy(options.get("run_id"), refresh=operation in {"refresh", "snapshot-init"},
                                          exact_key=options.get("exact_key", ""))
                        result = {}
                    elif operation == "recover":
                        result = controller.recover()
                    else:
                        result = controller.deploy(options["tag"], commit=options.get("commit"),
                                                   run_id=options.get("run_id"),
                                                   backup_record=options.get("backup_record"))
                except BaseException:
                    self.journal(operation, "failed")
                    raise
            self.journal(operation, "complete")
        return {"environment": self.name, "operation": operation, "complete": True, **(result or {})}

    def uninstall(self):
        """Stop/remove this environment's containers; keep configuration, databases, media and credentials."""
        self.prerequisites(private=False)
        with self.environment_lock(), self.shared_lock():
            self.require_installed()
            controller = self.controller()
            for number in self.instances():
                env, compose = self.instance(controller, number)
                if env.is_file():
                    self.docker.run(compose("down", "--remove-orphans", "--timeout", "30"))
            # Shared/external infrastructure is never stopped here, even by its owner.
            self.mark("uninstalled")
        return {"environment": self.name, "uninstalled": True, "data_preserved": True,
                "infrastructure_preserved": True, "reinstall": self.command("install")}

    def stop(self, pr=None):
        self.prerequisites(private=False)
        with self.environment_lock(), self.shared_lock():
            self.require_installed()
            controller = self.controller()
            for number in (self.instances() if self.name == "pr" and pr is None else [pr]):
                self.docker.run(self.active(controller, number)("stop", "--timeout", "30"))
        return {"environment": self.name, "stopped": True, "data_preserved": True}

    def start(self, pr=None):
        """Restart the recorded images after the same schema and readiness gates as deployment."""
        self.prerequisites()
        with self.environment_lock(), self.shared_lock():
            self.require_installed()
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
        with self.environment_lock(), self.shared_lock():
            self.require_installed()
            removed = self.controller().cleanup(pr)
        return {"environment": self.name, "pr": positive_int(pr), "removed": removed}

    def reconcile(self):
        """Remove previews whose PRs GitHub reports closed; API errors never imply closure."""
        with self.environment_lock(), self.shared_lock():
            self.require_installed()
            removed = self.controller().reconcile()
        return {"environment": self.name, "removed": removed}

    def database_migrate(self, *, backup_record=None):
        """Release-only explicit migration with the migration role, then a full runtime-role check."""
        self.private_record(backup_record, "database-migrate", "a completed pre-migration backup")
        self.prerequisites()
        with self.environment_lock():
            self.require_installed()
            controller = self.controller()
            compose = self.active(controller, None)
            self.docker.run(compose("run", "--rm", "--no-deps", "migrate"), diagnostic=controller.diagnostic_path())
            self.docker.run(compose("run", "--rm", "--no-deps", "check"), diagnostic=controller.diagnostic_path())
        return {"environment": self.name, "migrated": True}

    def infra_upgrade(self):
        """Explicit upgrade of managed shared infrastructure, preserving passwords and data."""
        self.prerequisites()
        with self.environment_lock(), self.shared_lock(exclusive=True):
            self.require_installed()
            if self.name == "release" or self.settings["infrastructure"]["mode"] != "managed":
                raise DeployError("Only the managed infrastructure owner may explicitly upgrade it")
            owner = self.infrastructure_owner()
            if not owner or owner.get("owner") != self.identity:
                raise DeployError(f"{self.infrastructure_root}; shared infrastructure belongs to another environment")
            self.controller().init()
        return {"environment": self.name, "infrastructure": "upgraded"}

    # Existing-host transition ------------------------------------------------------

    def migration_inspect(self, legacy_config):
        """Dry-run mapping of a legacy deploy/preview host configuration; changes nothing."""
        if self.name == "release":
            raise DeployError("Release adoption uses explicit private runtime/migration inputs; no legacy release exists")
        legacy_config = Path(legacy_config) if legacy_config else None
        if not legacy_config or not legacy_config.is_absolute() or not legacy_config.is_file():
            raise DeployError("migration-inspect/adopt requires --legacy-config <absolute legacy config.json>")
        old = json.loads(legacy_config.read_text())
        legacy = old if self.name == "pr" else {**old, **old.get("staging", {})}
        expected = old["state_dir"] if self.name == "pr" else old.get("staging", {}).get("state_dir")
        problems = []
        if expected != str(self.root):
            problems.append(f"state_dir must stay {expected}")
        if old.get("repository", "").lower() != self.settings["repository"].lower():
            problems.append("repository differs")
        if old["state_dir"] != str(self.infrastructure_root):
            problems.append(f"infrastructure.state_dir must stay {old['state_dir']} (preserves controller.lock and credentials)")
        if self.settings["infrastructure"]["project"] != "people-gator-preview-infra":
            problems.append("infrastructure.project must stay people-gator-preview-infra")
        for field in LEGACY_FIELDS[self.name]:
            if field in legacy and legacy[field] != self.settings.get(field):
                problems.append(f"{field} differs from the legacy value")
        owner = self.infrastructure_owner()
        mode = self.settings["infrastructure"]["mode"]
        if mode == "managed" and owner and owner.get("owner") != self.identity:
            problems.append("shared infrastructure is already owned by another environment; use mode=external")
        return {"environment": self.name, "config": str(self.path), "legacy_config": str(legacy_config),
                "legacy_config_sha256": hashlib.sha256(legacy_config.read_bytes()).hexdigest(),
                "state_dir": str(self.root), "infrastructure_mode": mode, "adoptable": not problems,
                "problems": problems, "preserves_data": True, "preserves_controller_lock": True, "deploys": False,
                "steps": ["Disable and drain old lifecycle callers for this environment",
                          "Back up private config/state and the database; record it in a private --backup-record file",
                          "adopt: write ownership markers only; no paths move and no services restart",
                          "Enable package workflows; keep old controller bundles until no job or mount uses them"]}

    def adopt(self, legacy_config, *, backup_record=None, dry_run=False):
        plan = self.migration_inspect(legacy_config)
        if dry_run or not plan["adoptable"]:
            if not plan["adoptable"] and not dry_run:
                raise DeployError(f"{self.name} adoption refused: " + "; ".join(plan["problems"]))
            return plan
        self.private_record(backup_record, "adopt", "the completed backup and drained old callers")
        with self.environment_lock(installed=False), self.shared_lock(exclusive=True):
            old = self.marker()
            if old and old.get("phase") == "installed":
                return {**plan, "changed": False}
            write_json(self.root / "adoption.json", plan)
            if self.settings["infrastructure"]["mode"] == "managed" and not self.infrastructure_owner():
                write_json(self.infrastructure_root / "infrastructure-owned.json",
                           {"schema_version": STATE_SCHEMA, "owner": self.identity, "environment": self.name,
                            "project": self.settings["infrastructure"]["project"]})
            self.mark("installed", adopted=True)
        return {**plan, "changed": True}

    # Dispatch ------------------------------------------------------------------------

    def execute(self, operation, **options):
        handlers = {
            "preflight": lambda: self.preflight(),
            "status": lambda: self.status(options.get("pr")),
            "check": lambda: self.check(options.get("pr")),
            "logs": lambda: self.logs(options.get("pr"), tail=options.get("tail") or 200),
            "install": self.install,
            "update": lambda: self.update(run_id=options.get("run_id"), tag=options.get("tag"),
                                          commit=options.get("commit"), backup_record=options.get("backup_record")),
            "uninstall": self.uninstall,
            "start": lambda: self.start(options.get("pr")),
            "stop": lambda: self.stop(options.get("pr")),
            "infra-upgrade": self.infra_upgrade,
            "migration-inspect": lambda: self.migration_inspect(options.get("legacy_config")),
            "adopt": lambda: self.adopt(options.get("legacy_config"), backup_record=options.get("backup_record"),
                                        dry_run=options.get("dry_run", False)),
            "cleanup": lambda: self.cleanup(options.get("pr")),
            "reconcile": self.reconcile,
            "snapshot-init": lambda: self.snapshot_init(run_id=options.get("run_id"), exact_key=options.get("exact_key", "")),
            "refresh": lambda: self.refresh(run_id=options.get("run_id"), exact_key=options.get("exact_key", ""),
                                            backup_record=options.get("backup_record")),
            "database-migrate": lambda: self.database_migrate(backup_record=options.get("backup_record")),
            "recover": lambda: self.recover(backup_record=options.get("backup_record"),
                                            compatibility_reviewed=options.get("compatibility_reviewed", False)),
        }
        if operation not in handlers or operation not in OPERATIONS[self.name]:
            raise DeployError(f"Unsupported {self.name} operation: {operation}")
        return handlers[operation]()


COMMON = ("configure", "migrate-config", "preflight", "status", "check", "logs",
          "install", "update", "uninstall", "start", "stop")
OPERATIONS = {
    "pr": (*COMMON, "cleanup", "reconcile", "infra-upgrade", "migration-inspect", "adopt"),
    "staging": (*COMMON, "snapshot-init", "refresh", "infra-upgrade", "migration-inspect", "adopt"),
    "release": (*COMMON, "database-migrate", "recover"),
}
