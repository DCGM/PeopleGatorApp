"""The runner account's Docker context, temporary registry credentials and owned-worker cleanup."""
from contextlib import contextmanager
import os
from pathlib import Path
import re
import secrets
import tempfile

from .core import DeployError, run

ASSETS = Path(__file__).with_name("assets")
# Ambient variables must never override private env files during interpolation.
INTERPOLATION = {name for path in ASSETS.glob("*.yaml")
                 for name in re.findall(r"\$\{([A-Z][A-Z0-9_]*)", path.read_text())}
AMBIENT = {"DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"}


class Docker:
    """Every invocation names the account's current context; that context is never changed."""

    def __init__(self, context=None):
        if context is None:
            context = run(["docker", "context", "show"], timeout=30).strip() or "default"
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", context):
            raise DeployError("The current Docker context has an unusable name; run `docker context use <name>`")
        self.context = context
        self.registry_config = None

    def environment(self, extra=None):
        environment = {key: value for key, value in os.environ.items()
                       if key not in INTERPOLATION | AMBIENT
                       and not key.startswith(("COMPOSE_", "PEOPLE_GATOR_", "DEPLOY_", "AWS_", "PG"))}
        if self.registry_config:
            environment["DOCKER_CONFIG"] = self.registry_config
        return {**environment, **(extra or {})}

    @staticmethod
    def starts_container(args):
        """`docker run` and `docker compose ... run` start a server-side container."""
        if args[3] == "run":
            return True
        return args[3] == "compose" and "run" in args and "exec" not in args

    def run(self, args, *, input=None, stdin=None, timeout=600, diagnostic=None, echo=False, progress=None, extra_env=None):
        """``extra_env`` reaches only this subprocess, for ``docker run -e NAME`` pass-through of secrets."""
        args = [str(value) for value in args]
        owned = None
        if args[0] == "docker":
            args[1:1] = ["--context", self.context]
            # A killed docker client does not kill its server-side container.
            if self.starts_container(args):
                index = args.index("run")
                if "--name" in args:
                    owned = args[args.index("--name") + 1]
                else:
                    owned = "people-gator-operation-" + secrets.token_hex(12)
                    args[index + 1:index + 1] = ["--name", owned]
        try:
            return run(args, env=self.environment(extra_env), input=input, stdin=stdin, timeout=timeout,
                       diagnostic=diagnostic, echo=echo, progress=progress)
        except BaseException:
            if owned:
                try:
                    run(["docker", "--context", self.context, "rm", "-f", owned], env=self.environment(), timeout=30)
                except Exception:
                    pass  # label-based recovery still finds a daemon-unreachable worker
            raise

    @contextmanager
    def registry(self):
        """Disposable GHCR login. Existing host logins/contexts are not copied or changed."""
        token = os.environ.get("GH_TOKEN")
        actor = os.environ.get("GH_ACTOR") or os.environ.get("GITHUB_ACTOR")
        if not token or not actor:
            raise DeployError("Image deployment requires GH_TOKEN and GH_ACTOR/GITHUB_ACTOR for temporary GHCR login")
        with tempfile.TemporaryDirectory(prefix="people-gator-registry-") as temporary:
            path = Path(temporary)
            if self.context != "default":
                # Export reads the ambient configuration; import writes only the temporary one.
                self.run(["docker", "context", "export", self.context, str(path / "context")], timeout=60)
            self.registry_config = temporary
            try:
                if self.context != "default":
                    run(["docker", "context", "import", self.context, str(path / "context")],
                        env=self.environment(), timeout=60)
                    (path / "context").unlink()
                run(["docker", "--context", self.context, "login", "ghcr.io", "-u", actor, "--password-stdin"],
                    env=self.environment(), input=token, timeout=60)
                yield
            finally:
                self.registry_config = None
