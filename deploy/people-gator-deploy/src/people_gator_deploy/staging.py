"""Reviewed-main staging lifecycle on the shared host primitives.

Normal deployments retain the active database/media/credentials and never
download, restore or seed. Only explicit ``snapshot-init``/``refresh`` prepare
a new database/media generation from a verified original-data backup, and the
pair is switched together only after validation and routed readiness.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import secrets
import shutil
import tempfile
from urllib.parse import urlsplit

from .core import DeployError
from .host import INSTALL_DIR, Host, IneligibleRun, positive_int, routed_readiness, summary, write_private

# Bounded referenced-media transfer; memory is bounded by concurrency * object size.
TRANSFER_DEFAULTS = {"concurrency": 8, "max_object_mib": 256}
# Example staging accounts provisioned once into the staging bucket.
ACCOUNTS = ("staging-viewer", "staging-annotator", "staging-importer", "staging-admin")
# Descriptor sections used only by snapshot-init/refresh, and the worker input each feeds.
SNAPSHOT_INPUTS = {"backup_source": "backup-source.json", "media_source": "media-source.json",
                   "accounts": "credential-input.json"}
SOURCE_REQUIRED = {"endpoint_url", "region", "bucket", "access_key_id", "secret_access_key"}
SOURCE_OPTIONAL = {"backup_source": {"prefix"},
                   "media_source": {"prefix", "image_prefix", "page_image_prefix", "page_layout_prefix"}}


def https_endpoint(value):
    endpoint = urlsplit(value) if isinstance(value, str) else None
    return bool(endpoint and endpoint.scheme == "https" and endpoint.hostname and not endpoint.username
                and not endpoint.password and not endpoint.query and not endpoint.fragment
                and endpoint.path in {"", "/"})


def validate_section(name, value):
    """Shape of one snapshot section; raises DeployError naming the descriptor field."""
    if name == "accounts":
        users = value.get("users") if isinstance(value, dict) else None
        if not isinstance(users, dict) or set(users) != set(ACCOUNTS):
            raise DeployError(f"accounts.users must define exactly {', '.join(ACCOUNTS)}")
        for user, record in users.items():
            if not isinstance(record, dict) or not str(record.get("hash", "")).startswith("$argon2id$"):
                raise DeployError(f"accounts.users.{user}.hash must be an Argon2id hash")
        keys = value.get("api_keys", {})
        if not isinstance(keys, dict) or set(value) - {"users", "api_keys"}:
            raise DeployError("accounts supports only users and api_keys")
        for identifier, record in keys.items():
            if (not isinstance(record, dict) or record.get("username") not in users
                    or not str(record.get("hash", "")).startswith("$argon2id$")):
                raise DeployError(f"accounts.api_keys.{identifier} needs a staging username and Argon2id hash")
        return value
    if (not isinstance(value, dict) or not SOURCE_REQUIRED.issubset(value)
            or set(value) - SOURCE_REQUIRED - SOURCE_OPTIONAL[name]
            or any(not isinstance(value[key], str) or not value[key].strip() for key in SOURCE_REQUIRED)):
        raise DeployError(f"{name} needs {', '.join(sorted(SOURCE_REQUIRED))} "
                          f"(optional: {', '.join(sorted(SOURCE_OPTIONAL[name]))})")
    if not https_endpoint(value["endpoint_url"]):
        raise DeployError(f"{name}.endpoint_url must be an explicit HTTPS S3-compatible endpoint")
    return value


class StagingConfigurationError(DeployError):
    """Fixed operator guidance safe to print without private input values."""


class Staging(Host):
    def __init__(self, config: dict):
        super().__init__(config)
        staging = config.get("staging")
        if not isinstance(staging, dict) or not staging.get("state_dir"):
            raise StagingConfigurationError(
                "Missing staging settings; run people-gator-deploy staging configure with state_dir and storage."
            )
        self.staging_root = Path(staging["state_dir"])
        if not self.staging_root.is_absolute() or self.staging_root.is_relative_to(self.root):
            raise DeployError("Staging state must be absolute and outside shared infrastructure state")
        self.host = staging.get("host", "staging.peoplegator.dev")
        if not re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)*", self.host):
            raise DeployError("Staging needs its independent hostname")
        self.worker_label = "people-gator.staging.worker=" + hashlib.sha256(str(self.staging_root.resolve()).encode()).hexdigest()[:16]
        self.settings = staging
        transfer = {**TRANSFER_DEFAULTS, **config.get("media_transfer", {})}
        if (set(transfer) != set(TRANSFER_DEFAULTS)
                or not all(isinstance(v, int) and not isinstance(v, bool) for v in transfer.values())
                or not 1 <= transfer["concurrency"] <= 64 or not 1 <= transfer["max_object_mib"] <= 4096):
            raise DeployError("media_transfer supports concurrency 1-64 and max_object_mib 1-4096")
        self.transfer = transfer

    def diagnostic_path(self):
        # Raw diagnostics remain outside Actions, collectors and utility installations.
        return self.staging_root / "last-error.log"

    def storage(self):
        """One explicit staging bucket, never an implicit/local storage default."""
        if not isinstance(self.config.get("storage"), dict):
            raise StagingConfigurationError(
                "The staging descriptor needs storage (the staging S3 bucket); "
                "add it with people-gator-deploy staging configure --input <private-json>."
            )
        return self.validate_storage({"local": None, "s3": self.config["storage"]})

    def snapshot_input(self, name):
        """A snapshot section, required only by snapshot-init/refresh."""
        if name not in self.config:
            raise StagingConfigurationError(
                f"The staging descriptor needs {name} for snapshot-init/refresh; "
                "add it with people-gator-deploy staging configure --input <private-json>."
            )
        value = validate_section(name, self.config[name])
        if name != "accounts":
            target = self.storage()["s3"]
            if (value["endpoint_url"].rstrip("/") == target["endpoint_url"].rstrip("/")
                    and value["bucket"] == target["bucket_name"]):
                raise DeployError(f"{name} must be separate from the staging storage bucket")
        return value

    @staticmethod
    def validate_storage(config):
        if set(config) != {"s3", "local"} or config["local"] is not None or not isinstance(config["s3"], dict):
            raise DeployError("Staging requires explicit S3 storage with local: null")
        s3 = config["s3"]
        required = {"endpoint_url", "region", "bucket_name", "access_key_id", "secret_access_key"}
        if (not required.issubset(s3) or set(s3) - required - {"timeout_seconds"}
                or any(not isinstance(s3[key], str) or not s3[key].strip() for key in required)):
            raise DeployError("Incomplete/unsupported staging S3 configuration")
        if not https_endpoint(s3["endpoint_url"]):
            raise DeployError("An explicit S3-compatible endpoint is required")
        if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", s3["bucket_name"]):
            raise DeployError("Invalid staging bucket name")
        timeout = s3.get("timeout_seconds", 30)
        if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise DeployError("Invalid staging S3 timeout")
        return config

    @staticmethod
    def storage_identity(config):
        return {key: config["s3"][key] for key in ("endpoint_url", "region", "bucket_name")}

    def runtime_environment(self, values):
        prefix = values["MEDIA_PREFIX"]
        return {
            "PEOPLE_GATOR_API__PERSISTENCE": json.dumps({"postgres": {
                "host": "preview-postgres", "port": 5432, "user": values["DB_USER"],
                "password": values["DB_PASSWORD"], "database": values["DB_NAME"], "schema_mode": "validate"}, "weaviate": None}),
            "PEOPLE_GATOR_API__STORAGE": values["STAGING_STORAGE"],
            "PEOPLE_GATOR_API__IMAGE_CONTENT__KEY_PREFIX": prefix + "/images",
            "PEOPLE_GATOR_API__PAGE_IMAGE__KEY_PREFIX": prefix + "/images/ndk",
            "PEOPLE_GATOR_API__PAGE_LAYOUT__KEY_PREFIX": prefix + "/page-layouts",
            "PEOPLE_GATOR_API__PAGE_IMAGE_CACHE__KEY_PREFIX": prefix + "/cache/page-images",
            "PEOPLE_GATOR_API__ALIGNED_FACE_CROP__CACHE_KEY_PREFIX": prefix + "/cache/aligned-face-crops",
            "PEOPLE_GATOR_API__JWK__USERS_PATH": "peoplegator_api/users.json",
            "PEOPLE_GATOR_API__API_KEYS__KEYS_PATH": "peoplegator_api/api-keys.json",
            "PEOPLE_GATOR_API__JWK__KEY_PATH": "peoplegator_api/jwks.json",
            "PEOPLE_GATOR_API__JWK__ISSUER": "https://" + self.host,
            "PEOPLE_GATOR_API__JWK__AUDIENCE": self.host,
            "PEOPLE_GATOR_API__OTEL__ENABLED": "false",
        }

    def compose_staging(self, env_file: Path, *args: str) -> list[str]:
        return ["docker", "compose", "--project-name", "people-gator-staging", "--env-file", str(env_file),
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
        storage = self.storage()
        if generation.get("storage") != self.storage_identity(storage):
            raise DeployError("Staging S3 bucket identity changed")
        return {"COMMIT_SHA": sha, "STAGING_HOST": self.host,
                "PREVIEW_LOG_ADDRESS": f"127.0.0.1:{self.config.get('preview_log_port', 24224)}",
                "DB_NAME": f"staging_{identity}", "DB_USER": f"staging_{identity}",
                "DB_PASSWORD": generation["password"], "MEDIA_PREFIX": f"generations/{identity}",
                "STAGING_STORAGE": json.dumps(storage),
                "DATABASE_NETWORK": self.config.get("database_network", "people-gator-preview-db"),
                "WEB_NETWORK": self.config.get("web_network", "web"),
                "CERTIFICATE_RESOLVER": self.config.get("certificate_resolver", "tlschallenge"),
                "CORS_ORIGIN_REGEX": f"^https://{re.escape(self.host)}$",
                "FRONTEND_IMAGE": images["frontend"], "BACKEND_IMAGE": images["backend"]}

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

    def worker(self, action, values, directory, *, work=None, exact_key=""):
        sections = {"download": ["backup_source"], "auth": ["accounts"],
                    "copy": ["media_source"], "validate": []}[action]
        # Descriptor sections reach their operation's worker only via stdin.
        inputs = {SNAPSHOT_INPUTS[name]: self.snapshot_input(name) for name in sections}
        memory = self.transfer["concurrency"] * self.transfer["max_object_mib"] + 512
        args = ["docker", "run", "--rm", "--log-driver", "none", "--read-only", "--cap-drop", "ALL",
                "--label", self.worker_label, "--security-opt", "no-new-privileges:true",
                "--memory", f"{memory}m", "--pids-limit", "256",
                # Only download needs to write the private host work directory.
                "--user", "0:0" if action == "download" else "10001:10001",
                "--tmpfs", "/tmp:size=256m,mode=1777", "--entrypoint", "python",
                "--mount", f"type=bind,src={INSTALL_DIR / 'snapshot.py'},dst=/snapshot.py,readonly"]
        if action in {"auth", "copy", "validate"}:
            # The database network is internal. A separate network provides S3
            # egress without attaching PostgreSQL to a public-facing network.
            args += ["--network", self.config.get("web_network", "web")]
            if action != "auth":
                args += ["--network", values["DATABASE_NETWORK"]]
            environment = directory / "worker.env"
            settings = self.runtime_environment(values)
            write_private(environment, "".join(f"{k}={v}\n" for k, v in settings.items()))
            args += ["--env-file", str(environment)]
        if action == "copy":
            inputs["transfer"] = self.transfer
        if work:
            args += ["--mount", f"type=bind,src={work},dst=/work"]
        args += ["--interactive", values["BACKEND_IMAGE"], "/snapshot.py", action]
        if exact_key:
            args += ["--exact-key", exact_key]
        progress = directory / f"{action}.progress.log" if action in {"download", "copy"} else None
        if progress:
            print(f"Staging {action} progress (private): {progress}", flush=True)
        return self.private_command(args, input_text=json.dumps(inputs), progress=progress)

    def prepare(self, generation, values, directory, exact_key):
        # Fresh work/database/media on every explicit attempt; partial generations
        # are never reused. Old failed generations remain private for inspection.
        work = Path(tempfile.mkdtemp(prefix="snapshot-", dir=self.staging_root))
        try:
            self.worker("download", values, directory, work=work, exact_key=exact_key)
            archive = work / "snapshot.dump"
            with archive.open("rb") as stream:
                if stream.read(5) != b"PGDMP":
                    raise DeployError("Selected backup is not a PostgreSQL custom archive")
            # pg_restore uses the shared service's PG16 tools and staging ownership.
            with archive.open("rb") as stream:
                self.private_command(self.infra("exec", "-T", "postgres", "pg_restore", "--list"), input_file=stream)
            provenance = json.loads((work / "provenance.json").read_text())
            self.provision(values)
            with archive.open("rb") as stream:
                self.private_command(self.infra("exec", "-T", "postgres", "pg_restore", "--exit-on-error",
                    "--single-transaction", "--no-owner", "--no-privileges", "--no-comments", "--no-security-labels",
                    "-U", "preview_admin", "--role", values["DB_USER"], "-d", values["DB_NAME"]), input_file=stream)
            report = json.loads(self.worker("copy", values, directory))
            generation["provenance"] = {**provenance, **report}
            write_private(directory / "provenance.json", json.dumps(generation["provenance"]))
            self.worker("auth", values, directory)
        finally:
            # Dump never survives a completed/failed operation or enters CI artifacts.
            shutil.rmtree(work)

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
        # before another attempt can write the independent credential store.
        ids = self.command(["docker", "ps", "-aq", "--filter", "label=" + self.worker_label]).split()
        if ids:
            if any(not re.fullmatch(r"[a-f0-9]{12,64}", value) for value in ids):
                raise DeployError("Invalid abandoned-worker identity")
            self.command(["docker", "rm", "-f", *ids])

    def deploy(self, run_id=None, *, refresh=False, exact_key=""):
        if exact_key and not refresh:
            raise DeployError("--exact-key is only valid for snapshot-init/refresh")
        if refresh:
            # Every snapshot section is checked before any lookup or mutation.
            for name in SNAPSHOT_INPUTS:
                self.snapshot_input(name)
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
        storage = self.storage_identity(self.storage())
        if old and old.get("storage") != storage:
            raise DeployError("Retained staging requires its original S3 bucket; moving buckets needs a data migration")
        images = {part: self.image(part, run) for part in ("frontend", "backend")}
        self.fence(run)
        generation = {"generation": secrets.token_hex(8), "password": secrets.token_hex(32), "storage": storage} if refresh else dict(old)
        directory = self.staging_root / ("generation-" + generation["generation"])
        directory.mkdir(mode=0o700, exist_ok=True)
        candidate = directory / "candidate.env"
        values = self.values(generation, images, run["head_sha"])
        write_private(candidate, self.dotenv(values))
        write_private(directory / "candidate.json", json.dumps({**generation, "sha": run["head_sha"], "images": images}))
        if refresh:
            self.prepare(generation, values, directory, exact_key)
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
                self.recover_activation()  # old DB/media never migrated or overwritten
            # Normal migrations may already have upgraded the retained schema.
            # Retain the journal; an operator must choose a compatible recovery.
            raise
        if old:
            write_private(self.staging_root / "previous.json", json.dumps(old))
            shutil.copyfile(self.staging_root / "compose.env", self.staging_root / "previous.env")
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
            text += (f"\nBackup: `{provenance['bucket']}/{provenance['key']}` · `{provenance['backup_date']}` · "
                     f"media objects: {provenance.get('media_objects')} · "
                     f"missing scans: {provenance.get('missing_page_scans')}\n")
        summary(text)
