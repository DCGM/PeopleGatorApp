"""Reviewed-main staging lifecycle on the shared host primitives.

Normal deployments retain the active database and never restore or seed. Only
explicit ``snapshot-init``/``refresh`` prepare an independent database from an
verified latest S3 backup (or an explicitly configured legacy local archive). Storage, media and authentication objects are
managed externally; deployment never copies, provisions or validates them.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import tempfile

from . import snapshots

from .core import DeployError
from .config import private_file
from .release import env_keys
from .host import INSTALL_DIR, Host, IneligibleRun, positive_int, routed_readiness, summary, write_private

def validate_snapshot(value, *, inputs=False):
    if (not isinstance(value, dict) or set(value) != {"path", "sha256", "application_revision"}
            or not isinstance(value.get("path"), str) or not Path(value["path"]).is_absolute()
            or ".." in Path(value["path"]).parts
            or not re.fullmatch(r"[a-f0-9]{64}", str(value.get("sha256", "")))
            or not re.fullmatch(r"[a-f0-9]{40}", str(value.get("application_revision", "")))):
        raise DeployError("snapshot needs an absolute path, sha256 (64 lowercase hex characters) "
                          "and application_revision (40 lowercase hex characters)")
    if inputs and not private_file(Path(value["path"])):
        raise DeployError("snapshot.path must name an owned private regular archive file")
    return value


class StagingConfigurationError(DeployError):
    """Fixed operator guidance safe to print without private input values."""


class Staging(Host):
    def __init__(self, config: dict):
        super().__init__(config)
        staging = config.get("staging")
        if not isinstance(staging, dict) or not staging.get("state_dir"):
            raise StagingConfigurationError(
                "Missing staging settings; run people-gator-deploy staging configure with state_dir and runtime_file."
            )
        self.staging_root = Path(staging["state_dir"])
        if not self.staging_root.is_absolute() or self.staging_root.is_relative_to(self.root):
            raise DeployError("Staging state must be absolute and outside shared infrastructure state")
        self.host = staging.get("host", "staging.peoplegator.dev")
        if not re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)*", self.host):
            raise DeployError("Staging needs its independent hostname")
        self.worker_label = "people-gator.staging.worker=" + hashlib.sha256(str(self.staging_root.resolve()).encode()).hexdigest()[:16]
        self.settings = staging

    def diagnostic_path(self):
        # Raw diagnostics remain outside Actions, collectors and utility installations.
        return self.staging_root / "last-error.log"

    def validate_inputs(self):
        runtime = Path(self.config.get("runtime_file", ""))
        if not runtime.is_absolute() or not private_file(runtime):
            raise StagingConfigurationError("runtime_file must name an owned private API environment file; "
                                           "run people-gator-deploy staging configure --input <private-json>")
        # Storage settings are opaque external application configuration. Only
        # database ownership and fixed deployment settings belong to this tool.
        keys = env_keys(runtime)
        if any(key.startswith("PEOPLE_GATOR_API__PERSISTENCE") for key in keys):
            raise DeployError(f"{runtime}: persistence settings are managed by staging; remove them from runtime_file")

    def snapshot_input(self):
        if "snapshot_source_file" in self.config:
            return snapshots.read_source(self.config["snapshot_source_file"])
        if "snapshot" not in self.config:
            raise StagingConfigurationError("The staging descriptor needs snapshot_source_file for snapshot-init/refresh (or a legacy snapshot); "
                                           "run people-gator-deploy staging configure --input <private-json>")
        return validate_snapshot(self.config["snapshot"], inputs=True)

    def runtime_environment(self, values):
        # Used only by the database validator; no externally managed storage or
        # authentication configuration is passed to this operation-scoped worker.
        return {
            "PEOPLE_GATOR_API__PERSISTENCE": json.dumps({"postgres": {
                "host": "preview-postgres", "port": 5432, "user": values["DB_USER"],
                "password": values["DB_PASSWORD"], "database": values["DB_NAME"], "schema_mode": "validate"}, "weaviate": None}),
            "PEOPLE_GATOR_API__OTEL__ENABLED": "false",
            # API settings require a storage selection even for SQL-only work.
            # This disposable local setting never references application storage.
            "PEOPLE_GATOR_API__STORAGE": '{"local":{"root":"/tmp/database-tools"},"s3":null}',
        }

    def compose_staging(self, env_file: Path, *args: str) -> list[str]:
        return ["docker", "compose", "--project-name", self.config.get("project", "people-gator-staging"), "--env-file", str(env_file),
                "-f", str(INSTALL_DIR / "compose.staging.yaml"), *args]

    def private_command(self, args, *, input_text=None, input_file=None, progress=None):
        # Staging commands may process private source data. Never relay subprocess
        # output (migrations, restore, Compose interpolation); keep it private.
        return self.docker.run(args, input=input_text, stdin=input_file, timeout=7200,
                               diagnostic=self.diagnostic_path(), progress=progress)

    def eligible_main(self, run_id: int | None = None):
        self.check_access()
        if run_id is None:
            runs = self.api("actions/workflows/pr-ci.yml/runs?branch=main&event=push&status=success&per_page=1")["workflow_runs"]
            if not runs:
                raise DeployError("No successful main build exists")
            run_id = runs[0]["id"]
        try:
            run = self.ci_run(run_id, event="push", branch="main")
        except IneligibleRun:
            raise IneligibleRun("Staging requires a successful CI build of the current main revision") from None
        main_sha = self.api("git/ref/heads/main")["object"]["sha"]
        if run["head_sha"] != main_sha:
            raise IneligibleRun("Staging requires a successful CI build of the current main revision")
        return run

    def fence(self, run):
        """Stale or retried attempts stop before migration and before activation."""
        current = self.eligible_main(run["id"])
        if current["run_attempt"] != run["run_attempt"]:
            raise DeployError("Build attempt changed during staging operation")
        version = [positive_int(run["id"]), positive_int(run["run_attempt"])]
        attempted = self.staging_root / "attempted.json"
        if attempted.exists() and json.loads(attempted.read_text())["version"] > version:
            raise DeployError("A newer staging build already attempted deployment")
        write_private(attempted, json.dumps({"version": version, "sha": run["head_sha"]}))

    def values(self, generation: dict, images: dict, sha: str):
        identity = generation["generation"]
        if not re.fullmatch(r"[a-f0-9]{16}", identity) or not re.fullmatch(r"[a-f0-9]{64}", generation["password"]):
            raise DeployError("Invalid staging generation state")
        return {"COMMIT_SHA": sha, "STAGING_HOST": self.host,
                "PREVIEW_LOG_ADDRESS": f"127.0.0.1:{self.config.get('preview_log_port', 24224)}",
                "DB_NAME": f"staging_{identity}", "DB_USER": f"staging_{identity}",
                "DB_PASSWORD": generation["password"], "RUNTIME_FILE": self.config["runtime_file"],
                "DATABASE_NETWORK": self.config.get("database_network", "people-gator-preview-db"),
                "WEB_NETWORK": self.config.get("web_network", "web"),
                "CERTIFICATE_RESOLVER": self.config.get("certificate_resolver", "tlschallenge"),
                "CORS_ORIGIN_REGEX": f"^https://{re.escape(self.host)}$",
                "FRONTEND_IMAGE": images["frontend"], "BACKEND_IMAGE": images["backend"],
                "TELEMETRY_FILE": self.config.get("telemetry_file", "/dev/null"),
                "APPLICATION_OTEL_NETWORK": self.config.get("otel_network", self.config.get("web_network", "web"))}

    def provision(self, values):
        name, password = values["DB_NAME"], values["DB_PASSWORD"]
        self.sql(f"""CREATE ROLE {name} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD '{password}';
CREATE DATABASE {name} OWNER {name} ALLOW_CONNECTIONS false;
REVOKE ALL ON DATABASE {name} FROM PUBLIC;
GRANT CONNECT, TEMPORARY ON DATABASE {name} TO {name};
ALTER DATABASE {name} ALLOW_CONNECTIONS true;
""")
        self.sql("CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS pg_trgm; "
                 "CREATE EXTENSION IF NOT EXISTS unaccent; REVOKE CREATE ON SCHEMA public FROM PUBLIC;", database=name)

    def worker(self, action, values, directory):
        if action != "validate":
            raise DeployError("Staging workers validate databases only; storage is managed externally")
        environment = directory / "worker.env"
        write_private(environment, "".join(f"{k}={v}\n" for k, v in self.runtime_environment(values).items()))
        args = ["docker", "run", "--rm", "--log-driver", "none", "--read-only", "--cap-drop", "ALL",
                "--label", self.worker_label, "--security-opt", "no-new-privileges:true",
                "--memory", "512m", "--pids-limit", "256", "--user", "10001:10001",
                "--tmpfs", "/tmp:size=128m,mode=1777", "--entrypoint", "python",
                "--mount", f"type=bind,src={INSTALL_DIR / 'snapshot.py'},dst=/snapshot.py,readonly",
                "--network", values["DATABASE_NETWORK"], "--env-file", str(environment),
                values["BACKEND_IMAGE"], "/snapshot.py"]
        return self.private_command(args)

    def prepare(self, generation, values, directory):
        source = self.snapshot_input()
        if "snapshot_source_file" not in self.config:
            return self.prepare_archive(generation, values, directory, source)
        # No persistent archive cache: every snapshot operation resolves anew.
        # TemporaryDirectory is mode 700; the streamed archive is mode 600.
        with tempfile.TemporaryDirectory(prefix="snapshot-", dir=self.staging_root) as temporary:
            try:
                print("Staging: discovering the latest dated production database backup", flush=True)
                client = snapshots.client_for(source)
                key = snapshots.select_backup(client, source)
                path = Path(temporary) / "snapshot.dump"
                print("Staging: downloading and verifying the selected backup privately", flush=True)
                provenance = snapshots.download(client, source, key, path)
            except DeployError:
                raise
            except Exception:
                # SDK errors may contain private endpoints or identifiers.
                raise DeployError("Snapshot gathering failed; check source read-only ListBucket/GetObject/GetObjectVersion "
                                  "access, endpoint connectivity and available private disk space") from None
            print("Staging: backup verified; preparing an isolated candidate database", flush=True)
            self.prepare_archive(generation, values, directory,
                {"path": str(path), "sha256": provenance["sha256"],
                 "application_revision": provenance["application_revision"]})
            try:
                snapshots.unchanged(client, source, provenance)
            except DeployError:
                raise
            except Exception:
                raise DeployError("Cannot recheck backup identity after restore; check source read access and connectivity") from None
            generation["provenance"].pop("path", None)
            generation["provenance"].update(provenance)
            write_private(directory / "provenance.json", json.dumps(generation["provenance"]))

    def prepare_archive(self, generation, values, directory, snapshot):
        path = Path(snapshot["path"])
        # Hold one inode throughout checksum verification, archive inspection and
        # restore. Replacing the path cannot change the selected archive; writes
        # to the open inode are rejected before the candidate can be activated.
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb", buffering=0) as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid() or before.st_mode & 0o077:
                raise DeployError("snapshot.path must name an owned private regular archive file")
            if stream.read(5) != b"PGDMP":
                raise DeployError("Selected snapshot is not a PostgreSQL custom archive")
            stream.seek(0)
            if hashlib.file_digest(stream, "sha256").hexdigest() != snapshot["sha256"]:
                raise DeployError("Snapshot SHA-256 does not match the expected checksum")
            stream.seek(0)
            self.private_command(self.infra("exec", "-T", "postgres", "pg_restore", "--list"), input_file=stream)
            stream.seek(0)
            self.provision(values)
            self.private_command(self.infra("exec", "-T", "postgres", "pg_restore", "--exit-on-error",
                "--single-transaction", "--no-owner", "--no-privileges", "--no-comments", "--no-security-labels",
                "-U", "preview_admin", "--role", values["DB_USER"], "-d", values["DB_NAME"]), input_file=stream)
            after = os.fstat(stream.fileno())
            if any(getattr(before, key) != getattr(after, key) for key in ("st_size", "st_mtime_ns", "st_ctime_ns")):
                raise DeployError("Snapshot changed during verification or restore")
        report = json.loads(self.worker("validate", values, directory))
        generation["provenance"] = {"path": str(path), "sha256": snapshot["sha256"], "size": before.st_size,
                                    "source_application_revision": snapshot["application_revision"], **report}
        write_private(directory / "provenance.json", json.dumps(generation["provenance"]))

    def readiness(self, attempts=30):
        routed_readiness(self.host, extra={"/staging-login.html": b"<form>"}, attempts=attempts)

    def recover_activation(self, *, refresh_requested=False):
        journal = self.staging_root / "activation.json"
        if not journal.exists():
            return
        active = self.staging_root / "state.json"
        pending = json.loads(journal.read_text())
        if active.exists() and json.loads(active.read_text()).get("activation") == pending["activation"]:
            state = json.loads(active.read_text())
            write_private(self.staging_root / "compose.env", self.dotenv(self.values(state, state["images"], state["sha"])))
            journal.unlink()  # success recorded before interruption
            return
        if not pending.get("refresh"):
            if refresh_requested:
                raise DeployError("Resolve interrupted retained-database deployment by retrying update before refresh")
            return  # Retry migration/check with a current image; never roll back an upgraded schema
        previous = self.staging_root / "compose.env"
        if previous.exists():
            self.command(self.compose_staging(previous, "up", "-d", "--wait", "--wait-timeout", "180", "backend", "frontend"))
            self.readiness()
        else:
            self.command(self.compose_staging(Path(pending["candidate"]), "down", "--timeout", "30"))
        journal.unlink()

    def reap_workers(self):
        # A killed runner/controller can leave a detached preparation worker alive.
        # Holding the environment lock, remove only our explicitly labelled workers
        # before another attempt can validate or activate a database candidate.
        ids = self.command(["docker", "ps", "-aq", "--filter", "label=" + self.worker_label]).split()
        if ids:
            if any(not re.fullmatch(r"[a-f0-9]{12,64}", value) for value in ids):
                raise DeployError("Invalid abandoned-worker identity")
            self.command(["docker", "rm", "-f", *ids])

    def deploy(self, run_id=None, *, refresh=False):
        self.validate_inputs()
        if refresh:
            self.snapshot_input()
        self.staging_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.reap_workers()
        self.recover_activation(refresh_requested=refresh)
        run = self.eligible_main(run_id)
        active_path = self.staging_root / "state.json"
        old = json.loads(active_path.read_text()) if active_path.exists() else None
        if not old and not refresh:
            raise StagingConfigurationError(
                "Explicit snapshot initialization is required before normal staging deployment: "
                "run people-gator-deploy staging snapshot-init (or staging.yml operation=snapshot-init)."
            )
        if not (self.root / "infrastructure.env").is_file():
            raise DeployError("Shared infrastructure must be installed first")
        images = {part: self.image(part, run) for part in ("frontend", "backend")}
        self.fence(run)
        generation = {"generation": secrets.token_hex(8), "password": secrets.token_hex(32)} if refresh else dict(old)
        directory = self.staging_root / ("generation-" + generation["generation"])
        directory.mkdir(mode=0o700, exist_ok=True)
        candidate = directory / "candidate.env"
        values = self.values(generation, images, run["head_sha"])
        write_private(candidate, self.dotenv(values))
        write_private(directory / "candidate.json", json.dumps({**generation, "sha": run["head_sha"], "images": images}))
        if refresh:
            self.prepare(generation, values, directory)
        self.fence(run)  # before any candidate migration
        self.command(self.compose_staging(candidate, "run", "--rm", "--no-deps", "migrate"))
        self.worker("validate", values, directory)
        self.fence(run)  # before application replacement
        self.command(self.compose_staging(candidate, "config", "--quiet"))
        self.command(self.compose_staging(candidate, "run", "--rm", "--no-deps", "check"))
        self.fence(run)  # full check can overlap a new main push too
        activation = secrets.token_hex(16)
        write_private(self.staging_root / "activation.json", json.dumps({"activation": activation, "candidate": str(candidate), "refresh": refresh}))
        try:
            self.command(self.compose_staging(candidate, "up", "-d", "--wait", "--wait-timeout", "180", "backend"))
            self.command(self.compose_staging(candidate, "up", "-d", "--wait", "--wait-timeout", "180", "frontend"))
            self.readiness()
        except BaseException:
            if refresh:
                self.recover_activation()  # old database never migrated or overwritten
            # Normal migrations may already have upgraded the retained schema.
            # Retain the journal; an operator must choose a compatible recovery.
            raise
        if old:
            write_private(self.staging_root / "previous.json", json.dumps(old))
            write_private(self.staging_root / "previous.env", (self.staging_root / "compose.env").read_text())
        generation.update(sha=run["head_sha"], images=images, version=[run["id"], run["run_attempt"]], activation=activation)
        # State is the commit point. The journal reconstructs compose.env on recovery.
        write_private(active_path, json.dumps(generation))
        write_private(self.staging_root / "compose.env", self.dotenv(values))
        (self.staging_root / "activation.json").unlink()
        url = f"https://{self.host}"
        print(f"Staging ready: {url} · {run['head_sha']}")
        text = f"Staging: [{url}]({url}) · `{run['head_sha']}`\n\n" + "".join(
            f"- {part}: `{image}`\n" for part, image in images.items())
        if refresh:
            provenance = generation["provenance"]
            text += f"\nDatabase snapshot SHA-256: `{provenance['sha256']}`\n"
        summary(text)
