"""Host primitives shared by every environment: GitHub API, Docker, PostgreSQL and images.

Nothing here is specific to PR previews, staging or releases. Deploy jobs run
in the workflow run that published the ``sha-<commit>`` images, so the build
identity is the tested commit plus this run's id/attempt; images are verified
by repository, revision label and digest before use.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.request

from .core import DeployError, atomic
from .docker import Docker

INSTALL_DIR = Path(__file__).resolve().parent / "assets"
SHA = re.compile(r"[a-f0-9]{40}")


class IneligibleRun(DeployError):
    """The requested commit is not deployable to this environment."""


def positive_int(value: str | int) -> int:
    if not re.fullmatch(r"[1-9][0-9]{0,15}", str(value)):
        raise DeployError("Expected a positive numeric identifier")
    return int(value)


def write_private(path: Path, content: str) -> None:
    atomic(path, content)


def run_number(name: str) -> int:
    """Actions run id/attempt from the environment; 0 outside a workflow run."""
    value = os.environ.get(name, "")
    return int(value) if re.fullmatch(r"[1-9][0-9]{0,15}", value) else 0


def github_api(repository: str, endpoint: str, *, method: str = "GET", data=None):
    """One authenticated GitHub API request; only idempotent reads are retried."""
    token = os.environ.get("GH_TOKEN")
    if not token:
        raise DeployError("GH_TOKEN is required for GitHub lifecycle commands")
    if not re.fullmatch(r"[!-~]+", token):
        raise DeployError("GH_TOKEN must contain a token without whitespace or control characters")
    url = f"https://api.github.com/repos/{repository}"
    if endpoint:
        url += f"/{endpoint}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "people-gator-deploy",
    }
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    # Never retry permission/not-found responses or interpret them as a
    # closed PR, including during cleanup.
    attempts = 3 if method == "GET" else 1
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                content = response.read()
                return json.loads(content) if content else None
        except urllib.error.HTTPError as error:
            request_id = error.headers.get("X-GitHub-Request-Id", "")
            if not re.fullmatch(r"[A-Za-z0-9:-]{1,200}", request_id):
                request_id = "unavailable"
            message = f"GitHub API {method} {url} failed: HTTP {error.code}; GitHub request ID: {request_id}."
            if error.code in {401, 403, 404}:
                message += (
                    " Check GITHUB_REPOSITORY, then the job token's repository access and its "
                    "contents/pull-requests/deployments permissions. A 404 may mean missing access "
                    "or a missing resource; it does not establish PR closure."
                )
            transient = error.code in {500, 502, 503, 504}
            error.close()
        except (urllib.error.URLError, TimeoutError):
            # Exception reasons and response bodies may contain credentials
            # or proxy details. Log only our own endpoint and fixed text.
            message = f"GitHub API {method} {url} failed: network error or timeout."
            transient = True
        except ValueError:
            raise DeployError(f"GitHub API {method} {url} returned invalid JSON") from None
        message = message.replace(token, "[REDACTED]")
        if not transient or attempt == attempts - 1:
            raise DeployError(message) from None
        delay = 2 ** attempt
        print(f"{message} Retrying in {delay}s ({attempt + 2}/{attempts}).", file=sys.stderr, flush=True)
        time.sleep(delay)
    raise DeployError(f"GitHub API {method} {url} failed")


def summary(text: str) -> None:
    """Append public, non-secret Markdown to the job summary when running in Actions."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a") as stream:
            stream.write(text)


def routed_readiness(host: str, *, extra: dict[str, bytes] | None = None, attempts=30, delay=2) -> None:
    """Success means the proxy routes HTTPS to a healthy API and frontend, not just running containers."""
    checks = {"/api/v1/health": None, "/healthz": None, **(extra or {}), "/": b"<html"}
    for path, marker in checks.items():
        for attempt in range(attempts):
            try:
                with urllib.request.urlopen(f"https://{host}{path}", timeout=5) as response:
                    body = response.read(1024 * 1024)
                    if path == "/api/v1/health" and json.loads(body).get("status") != "ok":
                        raise ValueError("API readiness returned an unexpected body")
                    if marker is not None and marker not in body.lower():
                        raise ValueError("Unexpected routed response")
                break
            except Exception:
                if attempt == attempts - 1:
                    raise DeployError(f"Routed readiness failed for https://{host}{path}; "
                                      "verify proxy/DNS/TLS and private service logs") from None
                time.sleep(delay)


class Host:
    """``root`` is the environment's private state directory."""

    # Synthetic-data environments may relay failed command output to CI logs.
    echo_output = False

    def __init__(self, config: dict):
        self.config = config
        self.docker = Docker(config.get("docker_context"))
        self.repository = config["repository"]
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", self.repository):
            raise DeployError("Invalid GitHub repository")
        workflow_repository = os.environ.get("GITHUB_REPOSITORY")
        if workflow_repository and self.repository.lower() != workflow_repository.lower():
            raise DeployError(
                f"Configured repository {self.repository} does not match GITHUB_REPOSITORY "
                f"{workflow_repository!r}. Unset DEPLOY_REPOSITORY or make it match the workflow repository."
            )
        self._access_checked = False
        self.root = Path(config["state_dir"])
        if not self.root.is_absolute():
            raise DeployError("state_dir must be absolute")

    # GitHub ---------------------------------------------------------------

    def api(self, endpoint: str, *, method: str = "GET", data=None):
        return github_api(self.repository, endpoint, method=method, data=data)

    def check_access(self) -> None:
        if self._access_checked:
            return
        repository = self.api("")
        if not isinstance(repository, dict) or repository.get("full_name", "").lower() != self.repository.lower():
            raise DeployError(
                "GitHub returned a different repository identity. Set DEPLOY_REPOSITORY to its current "
                "full name before retrying."
            )
        self._access_checked = True
        print(f"GitHub repository access verified: {self.repository}", flush=True)

    def build(self, sha: str) -> dict:
        """The tested commit and this workflow run's identity; images are tagged sha-<commit>."""
        if not SHA.fullmatch(sha or ""):
            raise DeployError("--sha requires the tested 40-character lowercase commit")
        return {"head_sha": sha, "id": run_number("GITHUB_RUN_ID"), "run_attempt": run_number("GITHUB_RUN_ATTEMPT")}

    # Docker / PostgreSQL --------------------------------------------------

    def diagnostic_path(self) -> Path | None:
        return None

    def command(self, args: list[str], *, sql: str | None = None, env: dict | None = None) -> str:
        # psql error messages can echo a statement containing a password.
        return self.docker.run(args, input=sql, diagnostic=self.diagnostic_path(),
                               echo=self.echo_output and sql is None, extra_env=env)

    def postgres(self, tool: str, *args: str, role: str = "postgres") -> list[str]:
        """A PostgreSQL client tool in a throwaway container on the database network.

        ``role`` selects the ``postgres`` (admin) or ``migration`` connection. The
        password travels through the environment (``-e PGPASSWORD``), never argv.
        """
        connection = self.config[role]
        return ["docker", "run", "--rm", "-i", "--network", self.config.get("database_network", "db"),
                "-e", "PGPASSWORD", self.config.get("postgres_image", "pgvector/pgvector:pg16"), tool,
                "-h", connection["host"], "-p", str(connection["port"]), "-U", connection["user"], *args]

    def postgres_env(self, role: str = "postgres") -> dict[str, str]:
        return {"PGPASSWORD": self.config[role]["password"]}

    def sql(self, statements: str, database: str | None = None) -> str:
        return self.command(self.postgres("psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1",
                                          "-d", database or self.config["postgres"]["database"]),
                            sql=statements, env=self.postgres_env())

    @staticmethod
    def dotenv(values: dict[str, str]) -> str:
        # Single-quoted dotenv values are literal, including dollar signs.
        if any(any(c in value for c in "\n\r'") for value in values.values()):
            raise DeployError("Invalid character in Compose configuration")
        return "".join(f"{key}='{value}'\n" for key, value in values.items())

    def harden_shared_server(self) -> None:
        """Per-environment roles may connect only to their own database (idempotent).

        PostgreSQL grants CONNECT on every database to PUBLIC by default; revoke it on
        the admin and template databases of the shared server before creating roles.
        """
        admin = self.config["postgres"]["database"]
        quoted = '"' + admin.replace('"', '""') + '"'
        self.sql(f"REVOKE ALL ON DATABASE {quoted}, template1 FROM PUBLIC;\n")

    def check_database(self, role: str = "postgres") -> dict:
        """The configured database must answer from the database network; nothing is created here."""
        connection = self.config[role]
        where = f"{connection['host']}:{connection['port']}/{connection['database']} as {connection['user']}"
        try:
            # The password travels only in the environment and the statement is fixed,
            # so psql's own error (wrong password, unknown host, ...) is safe to show.
            self.docker.run(self.postgres("psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1", "-d", connection["database"],
                                          "-c", "SELECT 1", role=role),
                            extra_env=self.postgres_env(role), echo=True, timeout=120)
        except DeployError:
            raise DeployError(f"Cannot connect to {where} from the {self.config.get('database_network', 'db')} "
                              f"network; check the database URL and that the server joins that network "
                              "(deploy/GITHUB-SETUP.md)") from None
        return {"database": where, "network": self.config.get("database_network", "db")}

    def image(self, component: str, run: dict) -> str:
        """Pull the tested commit's tag and return its digest after verifying the revision label."""
        repository = f"ghcr.io/{self.repository.lower()}-{component}"
        if not SHA.fullmatch(run.get("head_sha", "")):
            raise DeployError("Build identity needs the tested commit")
        tag = f"{repository}:sha-{run['head_sha']}"
        self.command(["docker", "pull", tag])
        inspected = json.loads(self.command(["docker", "image", "inspect", tag]))[0]
        labels = inspected.get("Config", {}).get("Labels") or {}
        if labels.get("org.opencontainers.image.revision") != run["head_sha"]:
            raise DeployError("Image revision does not match the tested commit")
        for digest in inspected.get("RepoDigests", []):
            if re.fullmatch(re.escape(repository) + r"@sha256:[a-f0-9]{64}", digest):
                return digest
        raise DeployError("Image has no digest in the expected repository")
