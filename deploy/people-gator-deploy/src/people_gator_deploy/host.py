"""Host primitives shared by every environment: GitHub reads, Docker, PostgreSQL and images.

Nothing here is specific to PR previews, staging or releases. Pull-request
content never supplies Compose files or host commands; GitHub API metadata
selects images, which are verified by repository, revision label and digest.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import secrets
import sys
import time
import urllib.error
import urllib.request

from .core import DeployError, atomic
from .docker import Docker

INSTALL_DIR = Path(__file__).resolve().parent / "assets"
SHA = re.compile(r"[a-f0-9]{40}")


class IneligibleRun(DeployError):
    """The selected CI run cannot supply deployable images."""


def positive_int(value: str | int) -> int:
    if not re.fullmatch(r"[1-9][0-9]{0,15}", str(value)):
        raise DeployError("Expected a positive numeric identifier")
    return int(value)


def write_private(path: Path, content: str) -> None:
    atomic(path, content)


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
    """``root`` is the shared infrastructure state directory (infrastructure.env, controller.lock)."""

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
                f"{workflow_repository!r}. An operator must update only the repository field "
                "with `people-gator-deploy <environment> configure`, preserving all other "
                "settings, state and passwords."
            )
        self._access_checked = False
        self.root = Path(config["state_dir"])
        if not self.root.is_absolute():
            raise DeployError("state_dir must be absolute")

    # GitHub ---------------------------------------------------------------

    def api(self, endpoint: str):
        token = os.environ.get("GH_TOKEN")
        if not token:
            raise DeployError("GH_TOKEN is required for GitHub lifecycle commands")
        if not re.fullmatch(r"[!-~]+", token):
            raise DeployError("GH_TOKEN must contain a token without whitespace or control characters")
        url = f"https://api.github.com/repos/{self.repository}"
        if endpoint:
            url += f"/{endpoint}"
        request = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "people-gator-deploy",
        })
        # Only idempotent reads are retried. Never retry permission/not-found
        # responses or interpret them as a closed PR, including during cleanup.
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    return json.load(response)
            except urllib.error.HTTPError as error:
                request_id = error.headers.get("X-GitHub-Request-Id", "")
                if not re.fullmatch(r"[A-Za-z0-9:-]{1,200}", request_id):
                    request_id = "unavailable"
                message = f"GitHub API GET {url} failed: HTTP {error.code}; GitHub request ID: {request_id}."
                if error.code in {401, 403, 404}:
                    message += (
                        " Check the descriptor repository against GITHUB_REPOSITORY, then "
                        "the job token's repository access and contents/actions/pull-requests "
                        "read permissions. A 404 may mean missing access or a missing resource; "
                        "it does not establish PR closure."
                    )
                transient = error.code in {500, 502, 503, 504}
                error.close()
            except (urllib.error.URLError, TimeoutError):
                # Exception reasons and response bodies may contain credentials
                # or proxy details. Log only our own endpoint and fixed text.
                message = f"GitHub API GET {url} failed: network error or timeout."
                transient = True
            except ValueError:
                raise DeployError(f"GitHub API GET {url} returned invalid JSON") from None
            message = message.replace(token, "[REDACTED]")
            if not transient or attempt == 2:
                raise DeployError(message) from None
            delay = 2 ** attempt
            print(f"{message} Retrying in {delay}s ({attempt + 2}/3).", file=sys.stderr, flush=True)
            time.sleep(delay)
        raise DeployError(f"GitHub API GET {url} failed")

    def check_access(self) -> None:
        if self._access_checked:
            return
        repository = self.api("")
        if not isinstance(repository, dict) or repository.get("full_name", "").lower() != self.repository.lower():
            raise DeployError(
                "GitHub returned a different repository identity. Update the descriptor "
                "repository field to its current full name before retrying."
            )
        self._access_checked = True
        print(f"GitHub repository access verified: {self.repository}", flush=True)

    def ci_run(self, run_id: int, *, event: str, branch: str | None = None) -> dict:
        """A successful same-repository PR CI run of the requested event; nothing else builds images."""
        run = self.api(f"actions/runs/{positive_int(run_id)}")
        workflow = self.api(f"actions/workflows/{positive_int(run['workflow_id'])}")
        if (run.get("conclusion") != "success" or run.get("event") != event
                or (branch is not None and run.get("head_branch") != branch)
                or workflow.get("path") != ".github/workflows/pr-ci.yml"
                or (run.get("head_repository") or {}).get("full_name", "").lower() != self.repository.lower()
                or not SHA.fullmatch(run.get("head_sha", ""))):
            raise IneligibleRun(f"Run {run_id} is not an eligible successful same-repository {event} PR CI run")
        return run

    # Docker / PostgreSQL --------------------------------------------------

    def diagnostic_path(self) -> Path | None:
        return None

    def command(self, args: list[str], *, sql: str | None = None) -> str:
        # psql error messages can echo a statement containing a password.
        return self.docker.run(args, input=sql, diagnostic=self.diagnostic_path(),
                               echo=self.echo_output and sql is None)

    def infra(self, *args: str) -> list[str]:
        return [
            "docker", "compose", "--project-name", self.config.get("infrastructure_project", "people-gator-preview-infra"),
            "--env-file", str(self.root / "infrastructure.env"),
            "-f", str(INSTALL_DIR / "compose.infrastructure.yaml"), *args,
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
            raise DeployError("Invalid character in Compose configuration")
        return "".join(f"{key}='{value}'\n" for key, value in values.items())

    def init(self) -> None:
        """Create or explicitly upgrade shared PostgreSQL/collector/pgAdmin, preserving passwords."""
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
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
            "INFRA_ID": self.config.get("infrastructure_id", "preview"),
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
        # Environment roles must not connect to administrative/template databases.
        self.sql("REVOKE ALL ON DATABASE postgres, template1 FROM PUBLIC;\n")
        print("Shared PostgreSQL, log collector and pgAdmin are ready")
        print(f"pgAdmin: https://{values['PGADMIN_HOST']} (login: {values['PGADMIN_DEFAULT_EMAIL']})")
        print(f"Generated credentials are in {env_file}; passwords are never printed")

    def image(self, component: str, run: dict) -> str:
        """Pull the run/attempt tag and return its digest after verifying the tested revision."""
        repository = f"ghcr.io/{self.repository.lower()}-{component}"
        tag = f"{repository}:run-{positive_int(run['id'])}-{positive_int(run['run_attempt'])}"
        self.command(["docker", "pull", tag])
        inspected = json.loads(self.command(["docker", "image", "inspect", tag]))[0]
        labels = inspected.get("Config", {}).get("Labels") or {}
        if labels.get("org.opencontainers.image.revision") != run["head_sha"]:
            raise DeployError("Image revision does not match the tested commit")
        for digest in inspected.get("RepoDigests", []):
            if re.fullmatch(re.escape(repository) + r"@sha256:[a-f0-9]{64}", digest):
                return digest
        raise DeployError("Image has no digest in the expected repository")
