"""PR preview lifecycle: per-PR isolated database/role/storage with the synthetic preview seed.

Deploys the images this workflow run published for a same-repository PR whose
head is still the tested commit. Redeployment preserves credentials, seeded
identities, reviewed edits and media. Removing one closed preview never touches
another preview, staging, releases or the operator-run shared infrastructure.
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
    standalone_auth: bool


class Preview(Host):
    echo_output = True  # previews contain only synthetic seed data

    def __init__(self, config: dict):
        super().__init__(config)
        self.previews = self.root
        self.domain = config["domain"]
        if not re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)*", self.domain):
            raise DeployError("Invalid preview domain")

    @staticmethod
    def uses_standalone_auth(env_file: Path) -> bool:
        if not env_file.exists():
            return False
        for line in env_file.read_text().splitlines():
            if line.startswith("STANDALONE_AUTH="):
                if line in ("STANDALONE_AUTH=1", "STANDALONE_AUTH='1'"):
                    return True
                if line in ("STANDALONE_AUTH=0", "STANDALONE_AUTH='0'"):
                    return False
                raise DeployError("Unsupported saved preview auth topology")
        return False

    def image_uses_standalone_auth(self, image: str) -> bool:
        inspected = json.loads(self.command(["docker", "image", "inspect", image]))[0]
        capability = (inspected.get("Config", {}).get("Labels") or {}).get("org.peoplegator.auth-service")
        if capability not in (None, "1"):
            raise DeployError("Unsupported image auth-service capability")
        return capability == "1"

    def compose(self, number: int, env_file: Path, *args: str) -> list[str]:
        # Select only recipes shipped in the reviewed installation, never PR files.
        recipe = "compose.pr-auth.yaml" if self.uses_standalone_auth(env_file) else "compose.pr.yaml"
        return [
            "docker", "compose", "--project-name", f"people-gator-pr-{positive_int(number)}",
            "--env-file", str(env_file), "-f", str(INSTALL_DIR / recipe), *args,
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

    def env(self, number: int, state: PreviewState, images: dict[str, str], *, sha: str = "unknown", standalone_auth: bool = False) -> str:
        values = {
            "STANDALONE_AUTH": "1" if standalone_auth else "0",
            "COMMIT_SHA": sha,
            "RUNTIME_FILE": self.config["runtime_file"],
            "TELEMETRY_FILE": self.config.get("telemetry_file", "/dev/null"),
            "APPLICATION_OTEL_NETWORK": self.config.get("otel_network", "logging"),
            "PR_NUMBER": str(number), "PREVIEW_HOST": f"pr-{number}.{self.domain}",
            "CORS_ORIGIN_REGEX": f"^https://{re.escape(f'pr-{number}.{self.domain}')}$",
            "DB_HOST": self.config["postgres"]["host"], "DB_PORT": str(self.config["postgres"]["port"]),
            "DB_NAME": f"preview_pr_{number}", "DB_USER": f"preview_pr_{number}",
            "DB_PASSWORD": state["password"],
            "DATABASE_NETWORK": self.config.get("database_network", "people-gator-db"),
            "WEB_NETWORK": self.config.get("web_network", "web"),
            "USERS_FILE": self.config["users_file"],
            "FRONTEND_IMAGE": images["frontend"], "BACKEND_IMAGE": images["backend"],
        }
        return self.dotenv(values)

    def deploy(self, sha: str, pr: int) -> list[int]:
        self.check_access()
        number = positive_int(pr)
        run = self.build(sha)
        if not self.current_pr(number, sha):
            print(f"PR #{number} is closed, from a fork or no longer at {sha}; skipping stale deployment")
            return []
        users = Path(self.config["users_file"])
        if not users.is_absolute() or not users.is_file():
            raise DeployError("users_file must name an existing absolute file")
        images = {component: self.image(component, run) for component in ("frontend", "backend")}
        standalone_auth = self.image_uses_standalone_auth(images["backend"])
        return [number] if self.deploy_pr(number, run, images, standalone_auth=standalone_auth) else []

    def deploy_pr(self, number: int, run: dict, images: dict[str, str], *, standalone_auth: bool = False) -> bool:
        directory = self.previews / f"pr-{positive_int(number)}"
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        state_file = directory / "state.json"
        state: PreviewState = json.loads(state_file.read_text()) if state_file.exists() else {
            "password": secrets.token_hex(32),
        }
        version = (int(run.get("id") or 0), int(run.get("run_attempt") or 0))
        deployed_version = tuple(state.get("version", [0, 0]))
        # Run ids order workflow runs; operator runs outside Actions carry (0, 0)
        # and are compared by commit only.
        if version != (0, 0) and deployed_version > version:
            print(f"PR #{number} already has a newer deployment")
            return False
        if (deployed_version == version and state.get("sha") == run["head_sha"]
                and tuple(state.get("seeded_version", [])) == version
                and state.get("standalone_auth", False) == standalone_auth):
            print(f"PR #{number} already runs this build")
            return False
        if not self.current_pr(number, run["head_sha"]):
            return False
        # Persist credentials before provisioning so failures can be retried/cleaned.
        write_private(state_file, json.dumps(state))
        candidate = directory / "candidate.env"
        write_private(candidate, self.env(number, state, images, sha=run["head_sha"], standalone_auth=standalone_auth))
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
        if standalone_auth:
            self.command(self.compose(number, candidate, "run", "--rm", "--no-deps", "auth-provision"))
        # A PR can close or receive a new commit while migrations/seeding are running.
        if not self.current_pr(number, run["head_sha"]):
            if self.api(f"pulls/{number}")["state"] == "closed":
                self.remove(number)
            print(f"PR #{number} changed during deployment; skipping startup")
            return False
        self.command(self.compose(number, candidate,
                                  "up", "-d", "--wait", "--wait-timeout", "180", "--remove-orphans",
                                  *(["auth"] if standalone_auth else []), "backend", "frontend"))
        candidate.replace(directory / "compose.env")
        # Success is recorded only once the routed preview responds.
        self.readiness(number)
        state.update(version=list(version), seeded_version=list(version), sha=run["head_sha"], images=images, standalone_auth=standalone_auth)
        write_private(state_file, json.dumps(state))
        url = f"https://pr-{number}.{self.domain}"
        print(f"Deployed PR #{number}: {url}")
        summary(f"PR #{number}: [{url}]({url}) · `{run['head_sha']}`\n\n"
                + "".join(f"- {part}: `{image}`\n" for part, image in images.items()) + "\n")
        return True

    def host(self, number: int) -> str:
        return f"pr-{positive_int(number)}.{self.domain}"

    def readiness(self, number: int) -> None:
        environment = self.previews / f"pr-{positive_int(number)}" / "compose.env"
        if self.uses_standalone_auth(environment):
            routed_readiness(self.host(number), extra={
                "/login.html": b"<html", "/auth/health": b'{"status":"ok"}',
                "/.well-known/jwks.json": b'"keys":[',
            })
        else:
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
            try:
                self.command(self.compose(number, env_file, "--profile", "tools",
                                          "down", "--volumes", "--remove-orphans", "--timeout", "30"))
            except DeployError:
                # A stack saved under earlier conventions (for example a database
                # network that no longer exists) cannot be torn down by Compose;
                # remove its containers and volumes by project label instead.
                project = f"label=com.docker.compose.project=people-gator-pr-{number}"
                containers = self.command(["docker", "ps", "-aq", "--filter", project]).split()
                if containers:
                    self.command(["docker", "rm", "-f", *containers])
                volumes = self.command(["docker", "volume", "ls", "-q", "--filter", project]).split()
                if volumes:
                    self.command(["docker", "volume", "rm", "-f", *volumes])
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
