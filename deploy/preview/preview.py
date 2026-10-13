#!/usr/bin/env python3
"""Installed preview-host controller. Uses only Python's standard library.

Run this trusted copy, never a copy checked out from a pull request. GitHub API
metadata selects images; PRs cannot supply Compose files or host commands.
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
from typing import TypedDict
import urllib.request


INSTALL_DIR = Path(__file__).resolve().parent


class PreviewCredentials(TypedDict):
    password: str


class PreviewState(PreviewCredentials, total=False):
    version: list[int]
    sha: str
    images: dict[str, str]


def positive_int(value: str | int) -> int:
    if not re.fullmatch(r"[1-9][0-9]{0,15}", str(value)):
        raise ValueError("Expected a positive numeric identifier")
    return int(value)


def write_private(path: Path, content: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    # umask is also set in main, but permissions matter for library callers too.
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(content)
    temporary.replace(path)


class Controller:
    def __init__(self, config: dict):
        self.config = config
        self.repository = config["repository"]
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", self.repository):
            raise ValueError("Invalid GitHub repository")
        self.root = Path(config["state_dir"])
        if not self.root.is_absolute():
            raise ValueError("state_dir must be absolute")
        self.domain = config.get("domain", "preview.peoplegator.dev")
        if not re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)*", self.domain):
            raise ValueError("Invalid preview domain")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def api(self, endpoint: str):
        token = os.environ.get("GH_TOKEN")
        if not token:
            raise ValueError("GH_TOKEN is required for GitHub lifecycle commands")
        request = urllib.request.Request(
            f"https://api.github.com/repos/{self.repository}/{endpoint}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)

    def command(self, args: list[str], *, sql: str | None = None) -> str:
        # Avoid ambient Compose interpolation variables overriding private files.
        environment = {
            key: value for key, value in os.environ.items()
            if not key.startswith("COMPOSE_") and key not in {
                "POSTGRES_ADMIN_PASSWORD", "PR_NUMBER", "PREVIEW_HOST",
                "FRONTEND_IMAGE", "BACKEND_IMAGE", "DB_USER", "DB_NAME",
                "DB_PASSWORD", "USERS_FILE", "DATABASE_NETWORK", "WEB_NETWORK",
                "CERTIFICATE_RESOLVER", "CORS_ORIGIN_REGEX", "COMMIT_SHA",
                "PREVIEW_LOG_ADDRESS", "PREVIEW_LOG_PORT", "OTEL_NETWORK",
                "OTEL_EXPORTER_OTLP_ENDPOINT", "PGADMIN_HOST",
                "PGADMIN_DEFAULT_EMAIL", "PGADMIN_DEFAULT_PASSWORD",
            }
        }
        result = subprocess.run(
            args, input=sql, text=True, capture_output=True, env=environment,
            timeout=600, check=False,
        )
        if result.returncode:
            # psql error messages can echo a statement containing a password.
            if sql is None:
                print(result.stdout, end="")
                print(result.stderr, end="", file=sys.stderr)
            raise RuntimeError(f"{args[0]} command failed (exit {result.returncode})")
        return result.stdout

    def infra(self, *args: str) -> list[str]:
        return [
            "docker", "compose", "--env-file", str(self.root / "infrastructure.env"),
            "-f", str(INSTALL_DIR / "compose.infrastructure.yaml"), *args,
        ]

    def compose(self, number: int, env_file: Path, *args: str) -> list[str]:
        return [
            "docker", "compose", "--project-name", f"people-gator-pr-{number}",
            "--env-file", str(env_file), "-f", str(INSTALL_DIR / "compose.pr.yaml"),
            *args,
        ]

    def sql(self, statements: str, database: str = "postgres") -> str:
        return self.command(self.infra(
            "exec", "-T", "postgres", "psql", "-X", "-qAt",
            "-v", "ON_ERROR_STOP=1", "-U", "preview_admin", "-d", database,
        ), sql=statements)

    @staticmethod
    def dotenv(values: dict[str, str]) -> str:
        # Single-quoted dotenv values are literal, including dollar signs.
        if any(any(c in value for c in "\n\r'") for value in values.values()):
            raise ValueError("Invalid character in Compose configuration")
        return "".join(f"{key}='{value}'\n" for key, value in values.items())

    def init(self) -> None:
        env_file = self.root / "infrastructure.env"
        # Upgrade old unquoted environment files without changing DB credentials.
        existing = {}
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                key, separator, value = line.partition("=")
                if separator:
                    existing[key] = value.strip("'")
        values = {
            "POSTGRES_ADMIN_PASSWORD": existing.get("POSTGRES_ADMIN_PASSWORD") or secrets.token_hex(32),
            "PGADMIN_DEFAULT_PASSWORD": existing.get("PGADMIN_DEFAULT_PASSWORD") or secrets.token_hex(32),
            "PGADMIN_DEFAULT_EMAIL": self.config.get("pgadmin_email", "admin@peoplegator.dev"),
            "PGADMIN_HOST": self.config.get("pgadmin_host", "pgadmin-preview.peoplegator.dev"),
            "DATABASE_NETWORK": self.config.get("database_network", "people-gator-preview-db"),
            "WEB_NETWORK": self.config.get("web_network", "web"),
            "CERTIFICATE_RESOLVER": self.config.get("certificate_resolver", "tlschallenge"),
            "OTEL_NETWORK": self.config.get("otel_network", "logging"),
            "OTEL_EXPORTER_OTLP_ENDPOINT": self.config.get("otel_http_endpoint", "http://lgtm:4318"),
            "PREVIEW_LOG_PORT": str(self.config.get("preview_log_port", 24224)),
        }
        write_private(env_file, self.dotenv(values))
        self.command(self.infra("run", "--rm", "--no-deps", "otel-collector", "validate", "--config=/etc/otelcol/preview.yaml"))
        self.command(self.infra("up", "-d", "--wait", "--wait-timeout", "180"))
        # Preview roles must not connect to administrative/template databases.
        self.sql("REVOKE ALL ON DATABASE postgres, template1 FROM PUBLIC;\n")
        print("Shared preview PostgreSQL, log collector and pgAdmin are ready")
        print(f"pgAdmin: https://{values['PGADMIN_HOST']} (login: {values['PGADMIN_DEFAULT_EMAIL']})")
        print(f"Generated credentials are in {env_file}; passwords are never printed")

    def provision_database(self, number: int, password: str) -> None:
        number = positive_int(number)
        if not re.fullmatch(r"[a-f0-9]{64}", password):
            raise ValueError("Invalid database password in preview state")
        name = f"preview_pr_{number}"
        # Names and passwords are strictly validated; SQL never comes from PR text.
        # Disable connections during creation, before revoking PUBLIC access.
        self.sql(rf"""
SELECT 'CREATE ROLE {name} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{name}')\gexec
ALTER ROLE {name} PASSWORD '{password}';
SELECT 'CREATE DATABASE {name} OWNER {name} ALLOW_CONNECTIONS false'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '{name}')\gexec
REVOKE ALL ON DATABASE {name} FROM PUBLIC;
GRANT CONNECT, TEMPORARY ON DATABASE {name} TO {name};
ALTER DATABASE {name} ALLOW_CONNECTIONS true;
""")
        # pgvector is not a trusted extension: provision it as admin, then run
        # application migrations with only the isolated PR owner's credentials.
        self.sql("""
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
""", database=name)

    def current_pr(self, number: int, sha: str | None = None) -> dict | None:
        pr = self.api(f"pulls/{positive_int(number)}")
        head_repo = (pr["head"].get("repo") or {}).get("full_name", "")
        if pr["state"] != "open" or head_repo.lower() != self.repository.lower():
            return None
        if sha is not None and pr["head"]["sha"] != sha:
            return None
        return pr

    def eligible_run(self, run_id: int) -> tuple[dict, list[int]]:
        run = self.api(f"actions/runs/{positive_int(run_id)}")
        workflow = self.api(f"actions/workflows/{positive_int(run['workflow_id'])}")
        if (
            run["conclusion"] != "success" or run["event"] != "pull_request"
            or workflow["path"] != ".github/workflows/pr-ci.yml"
            or (run.get("head_repository") or {}).get("full_name", "").lower()
                != self.repository.lower()
            or not re.fullmatch(r"[a-f0-9]{40}", run["head_sha"])
        ):
            raise ValueError("Run is not an eligible successful same-repository PR CI run")
        candidates = run.get("pull_requests", [])
        if not candidates:
            candidates = self.api(f"commits/{run['head_sha']}/pulls?per_page=100")
        numbers = sorted({positive_int(pr["number"]) for pr in candidates})
        return run, numbers

    def image(self, component: str, run: dict) -> str:
        repository = f"ghcr.io/{self.repository.lower()}-{component}"
        tag = f"{repository}:run-{positive_int(run['id'])}-{positive_int(run['run_attempt'])}"
        self.command(["docker", "pull", tag])
        inspected = json.loads(self.command(["docker", "image", "inspect", tag]))[0]
        labels = inspected.get("Config", {}).get("Labels") or {}
        if labels.get("org.opencontainers.image.revision") != run["head_sha"]:
            raise ValueError("Image revision does not match the tested PR commit")
        for digest in inspected.get("RepoDigests", []):
            if re.fullmatch(re.escape(repository) + r"@sha256:[a-f0-9]{64}", digest):
                return digest
        raise ValueError("Image has no digest in the expected repository")

    def env(self, number: int, state: PreviewState, images: dict[str, str], *, sha: str = "unknown") -> str:
        values = {
            "COMMIT_SHA": sha,
            "PREVIEW_LOG_ADDRESS": f"127.0.0.1:{self.config.get('preview_log_port', 24224)}",
            "PR_NUMBER": str(number), "PREVIEW_HOST": f"pr-{number}.{self.domain}",
            "CORS_ORIGIN_REGEX": f"^https://{re.escape(f'pr-{number}.{self.domain}')}$",
            "DB_NAME": f"preview_pr_{number}", "DB_USER": f"preview_pr_{number}",
            "DB_PASSWORD": state["password"],
            "DATABASE_NETWORK": self.config.get("database_network", "people-gator-preview-db"),
            "WEB_NETWORK": self.config.get("web_network", "web"),
            "CERTIFICATE_RESOLVER": self.config.get("certificate_resolver", "tlschallenge"),
            "USERS_FILE": self.config["users_file"],
            "FRONTEND_IMAGE": images["frontend"], "BACKEND_IMAGE": images["backend"],
        }
        return self.dotenv(values)

    def deploy(self, run_id: int) -> None:
        run, candidates = self.eligible_run(run_id)
        current = [number for number in candidates if self.current_pr(number, run["head_sha"])]
        if not current:
            print("No open PR still matches this run; skipping stale deployment")
            return
        if not (self.root / "infrastructure.env").exists():
            raise ValueError("Initialize preview infrastructure first")
        users = Path(self.config["users_file"])
        if not users.is_absolute() or not users.is_file():
            raise ValueError("users_file must name an existing absolute file")
        images = {component: self.image(component, run) for component in ("frontend", "backend")}
        for number in current:
            self.deploy_pr(number, run, images)

    def deploy_pr(self, number: int, run: dict, images: dict[str, str]) -> None:
        directory = self.root / f"pr-{positive_int(number)}"
        directory.mkdir(mode=0o700, exist_ok=True)
        state_file = directory / "state.json"
        state: PreviewState = json.loads(state_file.read_text()) if state_file.exists() else {
            "password": secrets.token_hex(32),
        }
        version = (positive_int(run["id"]), positive_int(run["run_attempt"]))
        if tuple(state.get("version", [0, 0])) >= version:
            print(f"PR #{number} already has this run or a newer deployment")
            return
        if not self.current_pr(number, run["head_sha"]):
            return
        # Persist credentials before provisioning so failures can be retried/cleaned.
        write_private(state_file, json.dumps(state))
        candidate = directory / "candidate.env"
        write_private(candidate, self.env(number, state, images, sha=run["head_sha"]))
        self.provision_database(number, state["password"])
        self.command(self.compose(number, candidate, "run", "--rm", "--no-deps", "storage-init"))
        self.command(self.compose(number, candidate, "run", "--rm", "--no-deps", "migrate"))
        self.command(self.compose(number, candidate, "run", "--rm", "--no-deps", "seed"))
        # A PR can close or receive a new commit while migrations/seeding are running.
        if not self.current_pr(number, run["head_sha"]):
            if self.api(f"pulls/{number}")["state"] == "closed":
                self.remove(number)
            print(f"PR #{number} changed during deployment; skipping startup")
            return
        self.command(self.compose(number, candidate,
            "up", "-d", "--wait", "--wait-timeout", "180", "--remove-orphans",
            "backend", "frontend",
        ))
        candidate.replace(directory / "compose.env")
        state.update(version=list(version), sha=run["head_sha"], images=images)
        write_private(state_file, json.dumps(state))
        url = f"https://pr-{number}.{self.domain}"
        print(f"Deployed PR #{number}: {url}")
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a") as stream:
                stream.write(f"PR #{number}: [{url}]({url}) · `{run['head_sha']}`\n\n")

    def remove(self, number: int) -> None:
        number = positive_int(number)
        directory = self.root / f"pr-{number}"
        if not directory.exists():
            print(f"PR #{number} has no preview state")
            return
        env_file = directory / "compose.env"
        if not env_file.exists():
            env_file = directory / "candidate.env"
        if env_file.exists():
            self.command(self.compose(number, env_file, "--profile", "tools",
                "down", "--volumes", "--remove-orphans", "--timeout", "30",
            ))
        # PostgreSQL 16 FORCE disconnects the stopped preview's remaining sessions.
        self.sql(f"DROP DATABASE IF EXISTS preview_pr_{number} WITH (FORCE);\n"
                 f"DROP ROLE IF EXISTS preview_pr_{number};\n")
        # Retain state until both Compose and DB cleanup succeed, allowing retries.
        shutil.rmtree(directory)
        print(f"Removed preview, storage, database and role for PR #{number}")

    def cleanup(self, number: int) -> None:
        pr = self.api(f"pulls/{positive_int(number)}")
        if pr["state"] != "closed":
            print(f"PR #{number} is open; ignoring stale close event")
            return
        self.remove(number)

    def reconcile(self) -> None:
        # Individual API reads avoid accidentally deleting open PRs on pagination
        # or partial-list failures. API errors fail closed: no inferred closures.
        for directory in sorted(self.root.glob("pr-*")):
            match = re.fullmatch(r"pr-([1-9][0-9]*)", directory.name)
            if match and directory.is_dir():
                self.cleanup(positive_int(match[1]))


def main() -> None:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=os.environ.get("PREVIEW_CONFIG", str(INSTALL_DIR / "config.json")))
    subparsers = parser.add_subparsers(dest="action", required=True)
    subparsers.add_parser("init")
    subparsers.add_parser("reconcile")
    deploy = subparsers.add_parser("deploy")
    deploy.add_argument("--run-id", type=positive_int, required=True)
    cleanup = subparsers.add_parser("cleanup")
    cleanup.add_argument("--pr", type=positive_int, required=True)
    args = parser.parse_args()
    controller = Controller(json.loads(Path(args.config).read_text()))
    # Also serialize manual/operator invocations against GitHub lifecycle jobs.
    with (controller.root / "controller.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if args.action == "deploy":
            controller.deploy(args.run_id)
        elif args.action == "cleanup":
            controller.cleanup(args.pr)
        else:
            getattr(controller, args.action)()


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as error:
        print(f"Preview controller failed: {error}", file=sys.stderr)
        sys.exit(1)
