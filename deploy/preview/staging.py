#!/usr/bin/env python3
"""Reviewed-main staging lifecycle. Shares the preview controller host lock.

Normal deploys retain the active database/media. Only explicit refresh retrieves
production backups. No infrastructure initialization or garbage collection here.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
from urllib.parse import urlsplit

# Sibling modules run from immutable, exactly verified controller releases.
# Never write __pycache__ there: re-publication rejects unexpected files.
sys.dont_write_bytecode = True
from preview import Controller, INSTALL_DIR, positive_int, write_private


class StagingConfigurationError(ValueError):
    """Fixed operator guidance safe to print without private input values."""


class OperationCancelled(Exception):
    """The runner cancelled this job (SIGINT/SIGTERM)."""


def cancelled(signum, frame):
    raise OperationCancelled()


class Staging(Controller):
    def __init__(self, config: dict):
        super().__init__(config)
        staging = config.get("staging")
        if not isinstance(staging, dict) or not all(staging.get(key) for key in ("state_dir", "private_dir")):
            raise StagingConfigurationError(
                "Missing staging host settings. An operator must add the staging section "
                "to the installed preview config, preserving existing settings. "
                "See deploy/preview/STAGING.md; repository .env files are not loaded by the controller."
            )
        self.staging_root = Path(staging["state_dir"])
        if not self.staging_root.is_absolute() or self.staging_root.is_relative_to(self.root):
            raise ValueError("Staging state must be absolute and outside preview state")
        self.host = staging.get("host", "staging.peoplegator.dev")
        if not re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)*", self.host) or self.host.endswith("." + self.domain):
            raise ValueError("Staging needs its independent hostname")
        self.worker_label = "people-gator.staging.worker=" + hashlib.sha256(str(self.staging_root.resolve()).encode()).hexdigest()[:16]
        self.settings = staging
        private = Path(staging["private_dir"])
        if not private.is_absolute() or private.is_relative_to(self.root) or private.is_relative_to(self.staging_root):
            raise ValueError("Private staging inputs must live outside release/preview/state directories")
        if "auth_volume" in staging:
            raise ValueError("Staging requires S3 storage; remove the local auth volume configuration")

    def storage(self):
        """One explicit staging bucket, never an implicit/local storage default."""
        path = Path(self.settings["private_dir"]) / "storage.json"
        if not path.is_file():
            raise StagingConfigurationError(
                "Missing private staging storage.json. Run configure_staging.py as the deployment "
                "runner with explicit S3 settings; see deploy/preview/STAGING.md."
            )
        return self.validate_storage(json.loads(path.read_text()))

    @staticmethod
    def validate_storage(config):
        if set(config) != {"s3", "local"} or config["local"] is not None or not isinstance(config["s3"], dict):
            raise ValueError("Staging requires explicit S3 storage with local: null")
        s3 = config["s3"]
        required = {"endpoint_url", "region", "bucket_name", "access_key_id", "secret_access_key"}
        if (not required.issubset(s3) or set(s3) - required - {"timeout_seconds"}
                or any(not isinstance(s3[key], str) or not s3[key].strip() for key in required)):
            raise ValueError("Incomplete/unsupported staging S3 configuration")
        endpoint = urlsplit(s3["endpoint_url"])
        if (endpoint.scheme != "https" or not endpoint.hostname or endpoint.username
                or endpoint.password or endpoint.query or endpoint.fragment or endpoint.path not in {"", "/"}):
            raise ValueError("An explicit S3-compatible endpoint is required")
        if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", s3["bucket_name"]):
            raise ValueError("Invalid staging bucket name")
        timeout = s3.get("timeout_seconds", 30)
        if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Invalid staging S3 timeout")
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

    def command(self, args, *, sql=None):
        # Staging commands may process private source data. Never relay subprocess
        # output on failure (including migrations, restore, Compose interpolation).
        try:
            return self.private_command(args, input_text=sql)
        except RuntimeError:
            raise RuntimeError("Staging operation failed; candidate diagnostics retained privately") from None

    def private_command(self, args, *, input_text=None, input_file=None):
        environment = {k: v for k, v in os.environ.items() if not k.startswith(("COMPOSE_", "PEOPLE_GATOR_API__"))}
        for key in ("STAGING_HOST", "MEDIA_PREFIX", "STAGING_STORAGE", "DB_NAME", "DB_USER", "DB_PASSWORD", "BACKEND_IMAGE",
                    "FRONTEND_IMAGE", "CORS_ORIGIN_REGEX", "COMMIT_SHA", "DATABASE_NETWORK", "WEB_NETWORK",
                    "CERTIFICATE_RESOLVER", "PREVIEW_LOG_ADDRESS"):
            environment.pop(key, None)
        options = {"stdin": input_file} if input_file else {"input": input_text}
        result = subprocess.run(args, **options, text=True, capture_output=True, env=environment, timeout=7200)
        if result.returncode:
            # Raw diagnostics remain outside Actions, collectors and release bundles.
            diagnostic = self.staging_root / "last-error.log"
            write_private(diagnostic, result.stdout + result.stderr)
            raise RuntimeError("Private staging command failed")
        return result.stdout

    def eligible_main(self, run_id: int | None = None):
        self.check_access()
        if run_id is None:
            runs = self.api("actions/workflows/pr-ci.yml/runs?branch=main&event=push&status=success&per_page=1")["workflow_runs"]
            if not runs:
                raise ValueError("No successful main build exists")
            run_id = runs[0]["id"]
        run = self.api(f"actions/runs/{positive_int(run_id)}")
        workflow = self.api(f"actions/workflows/{positive_int(run['workflow_id'])}")
        main_sha = self.api("git/ref/heads/main")["object"]["sha"]
        if (run.get("conclusion") != "success" or run.get("event") != "push" or run.get("head_branch") != "main"
                or workflow.get("path") != ".github/workflows/pr-ci.yml"
                or (run.get("head_repository") or {}).get("full_name", "").lower() != self.repository.lower()
                or not re.fullmatch(r"[a-f0-9]{40}", run.get("head_sha", "")) or run["head_sha"] != main_sha):
            raise ValueError("Staging requires a successful CI build of the current main revision")
        return run

    def fence(self, run):
        current = self.eligible_main(run["id"])
        if current["run_attempt"] != run["run_attempt"]:
            raise ValueError("Build attempt changed during staging operation")
        version = [positive_int(run["id"]), positive_int(run["run_attempt"])]
        attempted = self.staging_root / "attempted.json"
        if attempted.exists() and json.loads(attempted.read_text())["version"] > version:
            raise ValueError("A newer staging build already attempted deployment")
        write_private(attempted, json.dumps({"version": version, "sha": run["head_sha"]}))

    def values(self, generation: dict, images: dict, sha: str):
        identity = generation["generation"]
        if not re.fullmatch(r"[a-f0-9]{16}", identity) or not re.fullmatch(r"[a-f0-9]{64}", generation["password"]):
            raise ValueError("Invalid staging generation state")
        storage = self.storage()
        if generation.get("storage") != self.storage_identity(storage):
            raise ValueError("Staging S3 bucket identity changed or legacy local state was supplied")
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
        # Credentials are explicit and supplied only to their operation via stdin.
        files = {"download": ["backup-source.json"], "auth": ["credential-input.json"],
                 "copy": ["media-source.json"], "sanitize": ["media-policy.json", "media-source.json"], "validate": []}[action]
        args = ["docker", "run", "--rm", "--log-driver", "none", "--read-only", "--cap-drop", "ALL",
                "--label", self.worker_label, "--security-opt", "no-new-privileges:true",
                # Only download needs to write the private host work directory.
                "--user", "0:0" if action == "download" else "10001:10001",
                "--tmpfs", "/tmp:size=256m,mode=1777", "--entrypoint", "python",
                "--mount", f"type=bind,src={INSTALL_DIR / 'snapshot.py'},dst=/snapshot.py,readonly"]
        if action in {"auth", "copy", "sanitize", "validate"}:
            # The database network is internal. A separate network provides S3
            # egress without attaching PostgreSQL to a public-facing network.
            args += ["--network", self.config.get("web_network", "web")]
            if action != "auth":
                args += ["--network", values["DATABASE_NETWORK"]]
            environment = directory / "worker.env"
            config = self.runtime_environment(values)
            write_private(environment, "".join(f"{k}={v}\n" for k, v in config.items()))
            args += ["--env-file", str(environment)]
        for name in files:
            path = Path(self.settings["private_dir"]) / name
            if action == "sanitize" and name == "media-source.json" and not path.exists():
                continue  # allowed only when the policy permits no source images
            if not path.is_file():
                raise ValueError(f"Provision private staging input {name} first")
        # Host inputs stay mode-600; container UID 10001 receives only JSON stdin.
        inputs = {name: json.loads((Path(self.settings["private_dir"]) / name).read_text())
                  for name in files if (Path(self.settings["private_dir"]) / name).exists()}
        for name in ("backup-source.json", "media-source.json"):
            if name in inputs:
                source = inputs[name]
                target = json.loads(values["STAGING_STORAGE"])["s3"]
                if (source["endpoint_url"].rstrip("/") == target["endpoint_url"].rstrip("/")
                        and source.get("bucket", "peoplegator-db-backup") == target["bucket_name"]):
                    raise ValueError("Snapshot source must be separate from the staging S3 bucket")
        if work:
            args += ["--mount", f"type=bind,src={work},dst=/work"]
        args += ["--interactive", values["BACKEND_IMAGE"], "/snapshot.py", action]
        if exact_key:
            args += ["--exact-key", exact_key]
        return self.command(args, sql=json.dumps(inputs))

    def prepare(self, generation, values, directory, env_file, exact_key):
        # Fresh work/database/media on every explicit attempt; partial generations
        # are never reused. Old failed generations remain private for inspection.
        work = Path(tempfile.mkdtemp(prefix="snapshot-", dir=self.staging_root))
        try:
            self.worker("download", values, directory, work=work, exact_key=exact_key)
            archive = work / "snapshot.dump"
            with archive.open("rb") as stream:
                if stream.read(5) != b"PGDMP":
                    raise ValueError("Latest backup is not a PostgreSQL custom archive")
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

    def readiness(self):
        for path in ("/api/v1/health", "/healthz", "/staging-login.html", "/"):
            for attempt in range(30):
                try:
                    with urllib.request.urlopen(f"https://{self.host}{path}", timeout=5) as response:
                        body = response.read(1024 * 1024)
                        if path == "/api/v1/health" and json.loads(body).get("status") != "ok":
                            raise ValueError("API readiness returned an unexpected body")
                        if path == "/staging-login.html" and b"<form>" not in body:
                            raise ValueError("Staging sign-in page is unavailable")
                        if path == "/" and b"<html" not in body.lower():
                            raise ValueError("Frontend readiness did not return HTML")
                    break
                except Exception:
                    if attempt == 29:
                        raise RuntimeError("Staging HTTPS readiness failed") from None
                    time.sleep(2)

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
                raise ValueError("Resolve interrupted retained-database deployment by retrying deploy before refresh")
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
        # Holding the host lock, remove only our explicitly labelled workers before
        # another attempt can write the independent credential store.
        ids = self.command(["docker", "ps", "-aq", "--filter", "label=" + self.worker_label]).split()
        if ids:
            if any(not re.fullmatch(r"[a-f0-9]{12,64}", value) for value in ids):
                raise ValueError("Invalid abandoned-worker identity")
            self.command(["docker", "rm", "-f", *ids])

    def operate(self, run_id=None, *, refresh=False, exact_key=""):
        # Runner cancellation signals only this process tree; a detached
        # preparation worker would keep transferring. Remove our labelled
        # workers while this process still holds the host lock.
        previous = {number: signal.signal(number, cancelled) for number in (signal.SIGINT, signal.SIGTERM)}
        try:
            self.deploy(run_id, refresh=refresh, exact_key=exact_key)
        except OperationCancelled:
            for number in previous:
                signal.signal(number, signal.SIG_IGN)
            self.reap_workers()
            raise
        finally:
            for number, handler in previous.items():
                signal.signal(number, handler)

    def deploy(self, run_id=None, *, refresh=False, exact_key=""):
        self.reap_workers()
        self.recover_activation(refresh_requested=refresh)
        run = self.eligible_main(run_id)
        active_path = self.staging_root / "state.json"
        old = json.loads(active_path.read_text()) if active_path.exists() else None
        if not old and not refresh:
            raise StagingConfigurationError(
                "Explicit snapshot initialization is required before normal staging deployment. "
                "After provisioning private inputs, run staging.yml with operation=refresh."
            )
        if not (self.root / "infrastructure.env").is_file():
            raise ValueError("Operator must initialize shared infrastructure first")
        storage = self.storage_identity(self.storage())
        if old and old.get("storage") != storage:
            raise ValueError("Retained staging requires its original S3 bucket; migrate legacy storage explicitly")
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
            self.prepare(generation, values, directory, candidate, exact_key)
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
        except Exception:
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
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a") as stream:
                stream.write(f"Staging: [{url}]({url}) · `{run['head_sha']}`\n\n")
                for part, image in images.items():
                    stream.write(f"- {part}: `{image}`\n")
                if refresh:
                    provenance = generation["provenance"]
                    stream.write(f"\nBackup: `{provenance['bucket']}/{provenance['key']}` · `{provenance['backup_date']}`\n")


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=os.environ.get("PREVIEW_CONFIG", "/opt/people-gator-preview/config.json"))
    parser.add_argument("action", choices=["deploy", "refresh", "check-access"])
    parser.add_argument("--run-id", type=positive_int)
    parser.add_argument("--exact-key", default="")
    args = parser.parse_args()
    controller = Staging(json.loads(Path(args.config).read_text()))
    controller.staging_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if args.action == "check-access":
        controller.check_access()
        return
    if args.exact_key and args.action != "refresh":
        parser.error("--exact-key is only valid for explicit refresh")
    # Same inode as ALL preview lifecycle/manual operations across runner processes.
    with (controller.root / "controller.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        controller.operate(args.run_id, refresh=args.action == "refresh", exact_key=args.exact_key)


if __name__ == "__main__":
    try:
        main()
    except StagingConfigurationError as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
    except OperationCancelled:
        print("Staging operation cancelled; its preparation workers were removed. Retry explicitly.", file=sys.stderr)
        sys.exit(1)
    except Exception:
        print("Staging deployment failed; private candidate state/diagnostics retained. See staging operator guide.", file=sys.stderr)
        sys.exit(1)
