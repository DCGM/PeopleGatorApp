"""PR preview lifecycle: per-PR isolated database/role/storage with the synthetic preview seed.

Deploys only successful same-repository PR CI builds whose head is still the
open PR head. Redeployment preserves credentials, seeded identities, reviewed
edits and media. Removing one closed preview never touches another preview,
staging, releases or shared infrastructure.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import secrets
import shutil
from typing import TypedDict

from .core import DeployError
from .host import INSTALL_DIR, Host, positive_int, routed_readiness, summary, write_private


class PreviewCredentials(TypedDict):
    password: str


class PreviewState(PreviewCredentials, total=False):
    version: list[int]
    seeded_version: list[int]
    sha: str
    images: dict[str, str]


class Preview(Host):
    echo_output = True  # previews contain only synthetic seed data

    def __init__(self, config: dict):
        super().__init__(config)
        # Per-PR state; the shared infrastructure root is kept separately.
        self.previews = Path(config.get("previews_dir", config["state_dir"]))
        self.domain = config.get("domain", "preview.peoplegator.dev")
        if not re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)*", self.domain):
            raise DeployError("Invalid preview domain")

    def compose(self, number: int, env_file: Path, *args: str) -> list[str]:
        return [
            "docker", "compose", "--project-name", f"people-gator-pr-{positive_int(number)}",
            "--env-file", str(env_file), "-f", str(INSTALL_DIR / "compose.pr.yaml"), *args,
        ]

    def provision_database(self, number: int, password: str) -> None:
        number = positive_int(number)
        if not re.fullmatch(r"[a-f0-9]{64}", password):
            raise DeployError("Invalid database password in preview state")
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
        run = self.ci_run(run_id, event="pull_request")
        candidates = run.get("pull_requests", [])
        if not candidates:
            candidates = self.api(f"commits/{run['head_sha']}/pulls?per_page=100")
        numbers = sorted({positive_int(pr["number"]) for pr in candidates})
        return run, numbers

    def env(self, number: int, state: PreviewState, images: dict[str, str], *, sha: str = "unknown") -> str:
        values = {
            "COMMIT_SHA": sha,
            "TELEMETRY_FILE": self.config.get("telemetry_file", "/dev/null"),
            "APPLICATION_OTEL_NETWORK": self.config.get("otel_network", self.config.get("web_network", "web")),
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

    def deploy(self, run_id: int) -> list[int]:
        self.check_access()
        run, candidates = self.eligible_run(run_id)
        current = [number for number in candidates if self.current_pr(number, run["head_sha"])]
        if not current:
            print("No open PR still matches this run; skipping stale deployment")
            return []
        if not (self.root / "infrastructure.env").exists():
            raise DeployError("Initialize preview infrastructure first: people-gator-deploy pr install")
        users = Path(self.config["users_file"])
        if not users.is_absolute() or not users.is_file():
            raise DeployError("users_file must name an existing absolute file")
        images = {component: self.image(component, run) for component in ("frontend", "backend")}
        return [number for number in current if self.deploy_pr(number, run, images)]

    def deploy_pr(self, number: int, run: dict, images: dict[str, str]) -> bool:
        directory = self.previews / f"pr-{positive_int(number)}"
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        state_file = directory / "state.json"
        state: PreviewState = json.loads(state_file.read_text()) if state_file.exists() else {
            "password": secrets.token_hex(32),
        }
        version = (positive_int(run["id"]), positive_int(run["run_attempt"]))
        deployed_version = tuple(state.get("version", [0, 0]))
        if deployed_version > version or (
            deployed_version == version and tuple(state.get("seeded_version", [])) == version
        ):
            print(f"PR #{number} already has this run or a newer deployment")
            return False
        if not self.current_pr(number, run["head_sha"]):
            return False
        # Persist credentials before provisioning so failures can be retried/cleaned.
        write_private(state_file, json.dumps(state))
        candidate = directory / "candidate.env"
        write_private(candidate, self.env(number, state, images, sha=run["head_sha"]))
        # Replace this PR's containers explicitly, including an earlier stack
        # whose local controller state is unavailable. Keep its media volume,
        # database and retained credentials so review edits survive redeployment.
        self.command(self.compose(number, candidate, "--profile", "tools",
                                  "down", "--remove-orphans", "--timeout", "30"))
        self.provision_database(number, state["password"])
        self.command(self.compose(number, candidate, "run", "--rm", "--no-deps", "storage-init"))
        self.command(self.compose(number, candidate, "run", "--rm", "--no-deps", "migrate"))
        print(f"PR #{number}: seeding candidate data before application startup", flush=True)
        self.command(self.compose(number, candidate, "run", "--rm", "--no-deps", "seed"))
        print(f"PR #{number}: candidate seeding completed", flush=True)
        # A PR can close or receive a new commit while migrations/seeding are running.
        if not self.current_pr(number, run["head_sha"]):
            if self.api(f"pulls/{number}")["state"] == "closed":
                self.remove(number)
            print(f"PR #{number} changed during deployment; skipping startup")
            return False
        self.command(self.compose(number, candidate,
                                  "up", "-d", "--wait", "--wait-timeout", "180", "--remove-orphans",
                                  "backend", "frontend"))
        candidate.replace(directory / "compose.env")
        # Success is recorded only once the routed preview responds.
        self.readiness(number)
        state.update(version=list(version), seeded_version=list(version), sha=run["head_sha"], images=images)
        write_private(state_file, json.dumps(state))
        url = f"https://pr-{number}.{self.domain}"
        print(f"Deployed PR #{number}: {url}")
        summary(f"PR #{number}: [{url}]({url}) · `{run['head_sha']}`\n\n"
                + "".join(f"- {part}: `{image}`\n" for part, image in images.items()) + "\n")
        return True

    def host(self, number: int) -> str:
        return f"pr-{positive_int(number)}.{self.domain}"

    def readiness(self, number: int) -> None:
        routed_readiness(self.host(number))

    def remove(self, number: int) -> None:
        number = positive_int(number)
        directory = self.previews / f"pr-{number}"
        if not directory.exists():
            print(f"PR #{number} has no preview state")
            return
        env_file = directory / "compose.env"
        if not env_file.exists():
            env_file = directory / "candidate.env"
        if env_file.exists():
            self.command(self.compose(number, env_file, "--profile", "tools",
                                      "down", "--volumes", "--remove-orphans", "--timeout", "30"))
        # PostgreSQL 16 FORCE disconnects the stopped preview's remaining sessions.
        self.sql(f"DROP DATABASE IF EXISTS preview_pr_{number} WITH (FORCE);\n"
                 f"DROP ROLE IF EXISTS preview_pr_{number};\n")
        # Retain state until both Compose and DB cleanup succeed, allowing retries.
        shutil.rmtree(directory)
        print(f"Removed preview, storage, database and role for PR #{number}")

    def cleanup(self, number: int) -> bool:
        self.check_access()
        pr = self.api(f"pulls/{positive_int(number)}")
        if pr["state"] != "closed":
            print(f"PR #{number} is open; ignoring stale close event")
            return False
        self.remove(number)
        return True

    def instances(self) -> list[int]:
        numbers = []
        for directory in sorted(self.previews.glob("pr-*")):
            match = re.fullmatch(r"pr-([1-9][0-9]*)", directory.name)
            if match and directory.is_dir():
                numbers.append(positive_int(match[1]))
        return sorted(numbers)

    def reconcile(self) -> list[int]:
        self.check_access()
        # Individual API reads avoid accidentally deleting open PRs on pagination
        # or partial-list failures. API errors fail closed: no inferred closures.
        return [number for number in self.instances() if self.cleanup(number)]
