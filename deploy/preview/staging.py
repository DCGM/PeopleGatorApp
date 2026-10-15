#!/usr/bin/env python3
"""Reviewed-main staging lifecycle. Shares the preview controller host lock.

Normal deploys retain the active database/media. Only explicit refresh retrieves
production backups. No infrastructure initialization or garbage collection here.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

from preview import Controller, INSTALL_DIR, positive_int, write_private


class Staging(Controller):
    def __init__(self, config: dict):
        super().__init__(config)
        staging = config["staging"]
        self.staging_root = Path(staging["state_dir"])
        if not self.staging_root.is_absolute() or self.staging_root.is_relative_to(self.root):
            raise ValueError("Staging state must be absolute and outside preview state")
        self.host = staging.get("host", "staging.peoplegator.dev")
        if not re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)*", self.host) or self.host.endswith("." + self.domain):
            raise ValueError("Staging needs its independent hostname")
        self.settings = staging
        private = Path(staging["private_dir"])
        if not private.is_absolute() or private.is_relative_to(self.root) or private.is_relative_to(self.staging_root):
            raise ValueError("Private staging inputs must live outside release/preview/state directories")
        self.auth_volume = staging.get("auth_volume", "people-gator-staging-auth")
        if not re.fullmatch(r"people-gator-staging-[a-z0-9-]+", self.auth_volume):
            raise ValueError("Invalid staging-owned auth volume")

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
        for key in ("STAGING_HOST", "MEDIA_VOLUME", "DB_NAME", "DB_USER", "DB_PASSWORD", "BACKEND_IMAGE",
                    "FRONTEND_IMAGE", "CORS_ORIGIN_REGEX", "COMMIT_SHA", "DATABASE_NETWORK", "WEB_NETWORK",
                    "CERTIFICATE_RESOLVER", "PREVIEW_LOG_ADDRESS", "AUTH_VOLUME"):
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
        return {"COMMIT_SHA": sha, "STAGING_HOST": self.host,
                "PREVIEW_LOG_ADDRESS": f"127.0.0.1:{self.config.get('preview_log_port', 24224)}",
                "DB_NAME": f"staging_{identity}", "DB_USER": f"staging_{identity}",
                "AUTH_VOLUME": self.auth_volume, "DB_PASSWORD": generation["password"], "MEDIA_VOLUME": f"people-gator-staging-{identity}-media",
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
        for volume in (values["MEDIA_VOLUME"], values["AUTH_VOLUME"]):
            self.command(["docker", "volume", "create", volume])

    def worker(self, action, values, directory, *, work=None, exact_key=""):
        # Credentials are separate, explicit, operation-scoped read-only mounts.
        files = {"download": ["backup-source.json"], "auth": ["credential-input.json"],
                 "sanitize": ["media-policy.json", "media-source.json"], "validate": []}[action]
        args = ["docker", "run", "--rm", "--log-driver", "none", "--read-only", "--cap-drop", "ALL",
                "--label", "people-gator.staging.worker=true", "--cap-add", "CHOWN", "--cap-add", "DAC_OVERRIDE", "--cap-add", "FOWNER", "--security-opt", "no-new-privileges:true", "--user", "0:0",
                "--tmpfs", "/tmp:size=256m,mode=1777", "--entrypoint", "python",
                "--mount", f"type=bind,src={INSTALL_DIR / 'snapshot.py'},dst=/snapshot.py,readonly"]
        if action in {"auth", "sanitize", "validate"}:
            if action != "auth":
                args += ["--network", values["DATABASE_NETWORK"]]
            environment = directory / "worker.env"
            config = {"PEOPLE_GATOR_API__PERSISTENCE": json.dumps({"postgres": {
                "host": "preview-postgres", "port": 5432, "user": values["DB_USER"],
                "password": values["DB_PASSWORD"], "database": values["DB_NAME"], "schema_mode": "validate"}, "weaviate": None}),
                "PEOPLE_GATOR_API__STORAGE": '{"local":{"root":"/data"},"s3":null}',
                "PEOPLE_GATOR_API__OTEL__ENABLED": "false"}
            write_private(environment, "".join(f"{k}={v}\n" for k, v in config.items()))
            args += ["--env-file", str(environment)]
        if action in {"auth", "sanitize", "validate"}:
            args += ["--mount", f"type=volume,src={values['MEDIA_VOLUME']},dst=/data"]
        if action == "auth":
            args += ["--network", "none", "--mount", f"type=volume,src={values['AUTH_VOLUME']},dst=/data/peoplegator_api"]
        for name in files:
            path = Path(self.settings["private_dir"]) / name
            if name == "media-source.json" and not path.exists():
                continue  # allowed only when the policy permits no source images
            if not path.is_file():
                raise ValueError(f"Provision private staging input {name} first")
            args += ["--mount", f"type=bind,src={path},dst=/private/{name},readonly"]
        if work:
            args += ["--mount", f"type=bind,src={work},dst=/work"]
        args += [values["BACKEND_IMAGE"], "/snapshot.py", action]
        if exact_key:
            args += ["--exact-key", exact_key]
        return self.command(args)

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
            report = json.loads(self.worker("sanitize", values, directory))
            generation["provenance"] = {**provenance, **report}
            write_private(directory / "provenance.json", json.dumps(generation["provenance"]))
            self.command(self.compose_staging(env_file, "run", "--rm", "--no-deps", "storage-init"))
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
        ids = self.command(["docker", "ps", "-aq", "--filter", "label=people-gator.staging.worker=true"]).split()
        if ids:
            if any(not re.fullmatch(r"[a-f0-9]{12,64}", value) for value in ids):
                raise ValueError("Invalid abandoned-worker identity")
            self.command(["docker", "rm", "-f", *ids])

    def deploy(self, run_id=None, *, refresh=False, exact_key=""):
        self.reap_workers()
        self.recover_activation(refresh_requested=refresh)
        run = self.eligible_main(run_id)
        active_path = self.staging_root / "state.json"
        old = json.loads(active_path.read_text()) if active_path.exists() else None
        if not old and not refresh:
            raise ValueError("Explicit snapshot initialization is required before normal staging deployment")
        if not (self.root / "infrastructure.env").is_file():
            raise ValueError("Operator must initialize shared infrastructure first")
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
        controller.deploy(args.run_id, refresh=args.action == "refresh", exact_key=args.exact_key)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("Staging deployment failed; private candidate state/diagnostics retained. See staging operator guide.", file=sys.stderr)
        sys.exit(1)
