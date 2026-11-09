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
import socket
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
        self.docker = Docker(config.get("docker_context", "default"))
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

    def command(self, args: list[str], *, sql: str | None = None) -> str:
        # psql error messages can echo a statement containing a password.
        return self.docker.run(args, input=sql, diagnostic=self.diagnostic_path(),
                               echo=self.echo_output and sql is None)

    def postgres(self, tool: str, *args: str) -> list[str]:
        """Run a PostgreSQL client tool inside the operator-run shared PostgreSQL container."""
        return ["docker", "exec", "-i", self.config["postgres_container"], tool, *args]

    def sql(self, statements: str, database: str = "postgres") -> str:
        return self.command(self.postgres("psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1",
                                          "-U", self.config["postgres_admin_user"], "-d", database), sql=statements)

    @staticmethod
    def dotenv(values: dict[str, str]) -> str:
        # Single-quoted dotenv values are literal, including dollar signs.
        if any(any(c in value for c in "\n\r'") for value in values.values()):
            raise DeployError("Invalid character in Compose configuration")
        return "".join(f"{key}='{value}'\n" for key, value in values.items())

    def check_infrastructure(self) -> dict:
        """The shared PostgreSQL and log collector must already be up; nothing is created here.

        Previews and staging connect to ``preview-postgres`` on the database network
        and send Docker logs to the collector on the loopback port.
        """
        container = self.config["postgres_container"]
        network = self.config["database_network"]
        remedy = ("start it with docker compose -f deploy/infrastructure/compose.yaml --env-file <private env> up -d "
                  "or set DEPLOY_POSTGRES_CONTAINER")
        try:
            inspected = json.loads(self.command(["docker", "container", "inspect", container]))[0]
        except DeployError:
            raise DeployError(f"Shared PostgreSQL container {container!r} does not exist; {remedy}") from None
        if not inspected.get("State", {}).get("Running"):
            raise DeployError(f"Shared PostgreSQL container {container!r} is not running; {remedy}")
        attached = inspected.get("NetworkSettings", {}).get("Networks", {}).get(network) or {}
        # Engine 25+ reports user aliases in DNSNames and deprecates Aliases.
        names = {*(attached.get("Aliases") or []), *(attached.get("DNSNames") or [])}
        if not attached or "preview-postgres" not in names:
            raise DeployError(f"Shared PostgreSQL container {container!r} must join network {network!r} with the alias "
                              "preview-postgres (DEPLOY_DATABASE_NETWORK / deploy/infrastructure/compose.yaml)")
        try:
            self.sql("SELECT 1;")
        except DeployError:
            raise DeployError(f"psql as {self.config['postgres_admin_user']!r} failed inside {container!r}; check the "
                              "container's PostgreSQL and DEPLOY_POSTGRES_ADMIN_USER") from None
        port = int(self.config.get("preview_log_port", 24224))
        collector = True
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=3):
                pass
        except OSError:
            collector = False
            # fluentd-async logging drops logs silently rather than failing containers.
            print(f"::warning::No log collector listens on 127.0.0.1:{port}; container logs will be dropped "
                  "until deploy/infrastructure is running", file=sys.stderr, flush=True)
        return {"postgres_container": container, "database_network": network, "log_collector": collector}

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
