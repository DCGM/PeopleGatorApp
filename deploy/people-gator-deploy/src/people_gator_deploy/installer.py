"""One installation implementation for bootstrap, reinstall, ensure and self-update."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import venv

from . import __version__, CONFIG_SCHEMA, STATE_SCHEMA
from .core import DeployError, atomic, lock, run, write_json

PACKAGE = "deploy/people-gator-deploy"
REPOSITORY = "https://github.com/DCGM/PeopleGatorApp.git"


def layout(scope="user", prefix=None):
    base = Path(prefix).expanduser() if prefix else (Path.home() / ".local" if scope == "user" else Path("/"))
    if not base.is_absolute():
        raise DeployError("Installation prefix must be absolute")
    if scope == "system":
        return {"scope": scope, "prefix": str(base), "bin": str(base / "usr/local/bin"),
                "versions": str(base / "opt/people-gator-deploy/versions"),
                "config": str(base / "etc/people-gator-deploy/environments"),
                "state": str(base / "var/lib/people-gator-deploy")}
    return {"scope": scope, "prefix": str(base), "bin": str(base / "bin"),
            "versions": str(base / "lib/people-gator-deploy/versions"),
            "config": str(base / "opt/people-gator-deploy/environments"),
            "state": str(base / "opt/people-gator-deploy/state")}


def git(source, *args):
    return run(["git", "-C", source, *args], timeout=120).strip()


def integrity(directory):
    result = {}
    for path in sorted(directory.rglob("*")):
        if path.is_file() and not path.is_symlink() and path.name != "installation.json":
            result[str(path.relative_to(directory))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def verify(directory):
    try:
        manifest = json.loads((directory / "installation.json").read_text())
        if (manifest["config_schema"] != CONFIG_SCHEMA or manifest["state_schema"] != STATE_SCHEMA
                or manifest["files"] != integrity(directory)):
            raise ValueError()
        return manifest
    except (OSError, ValueError, KeyError):
        raise DeployError(f"Incomplete/corrupt utility installation: {directory}; reinstall the exact reviewed revision") from None


def install(source: Path, revision: str, *, scope="user", prefix=None, run_as=None):
    if not re.fullmatch(r"[a-f0-9]{40}", revision):
        raise DeployError("--revision requires an exact 40-character reviewed commit SHA")
    if scope == "system" and (os.geteuid() != 0 or not run_as):
        raise DeployError("System installation requires an operator running as root and --run-as <deployment-user>")
    if scope == "user" and os.geteuid() == 0 and prefix is None:
        raise DeployError("Select --system --run-as or an explicit disposable --prefix when running as root")
    account = pwd.getpwnam(run_as) if run_as else None
    if account and account.pw_uid == 0:
        raise DeployError("The routine deployment account must be unprivileged")
    # CI may execute only its exact reviewed default-branch workflow revision.
    # Release tags run the tagged workflow, so that commit must already be on main.
    tagged = False
    if os.environ.get("GITHUB_ACTIONS") == "true":
        repository = os.environ.get("GITHUB_REPOSITORY", "")
        workflow = os.environ.get("GITHUB_WORKFLOW_REF", "")
        allowed = {f"{repository}/.github/workflows/{name}@refs/heads/main"
                   for name in ("pr-preview.yml", "staging.yml", "release.yml")}
        tagged = bool(re.fullmatch(re.escape(f"{repository}/.github/workflows/release.yml@refs/tags/")
                                   + r"v[0-9A-Za-z.+-]+", workflow))
        if (workflow not in allowed and not tagged) or os.environ.get("GITHUB_WORKFLOW_SHA") != revision:
            raise DeployError("CI installation requires the exact reviewed main deployment workflow commit")
        if scope != "user":
            raise DeployError("CI cannot upgrade a system installation; ask its operator or select a user prefix")
    git(source, "cat-file", "-e", revision + "^{commit}")
    if tagged and subprocess.run(["git", "-C", str(source), "merge-base", "--is-ancestor", revision,
                                  "refs/remotes/origin/main"], capture_output=True).returncode != 0:
        raise DeployError("Tag-triggered controllers must be commits already reviewed on main")
    paths = layout(scope, prefix)
    versions = Path(paths["versions"])
    versions.mkdir(mode=0o755, parents=True, exist_ok=True)
    destination = versions / revision
    with lock(versions.parent / "install.lock"):
        if destination.exists():
            metadata = verify(destination)
            if metadata["scope"] != scope or metadata["prefix"] != paths["prefix"]:
                raise DeployError("Existing installation scope/prefix conflicts with the selected installation")
        else:
            temporary = Path(tempfile.mkdtemp(prefix=".pending-", dir=versions))
            try:
                with tempfile.TemporaryDirectory(prefix="people-gator-build-") as build:
                    build = Path(build)
                    archive = build / "source.tar"
                    # Only committed blobs become host code. No developer checkout is modified.
                    run(["git", "-C", source, "archive", "--format=tar", "-o", archive, revision, PACKAGE])
                    with tarfile.open(archive) as stream:
                        # git archive contains only the selected trusted package tree.
                        for member in stream.getmembers():
                            if member.issym() or member.islnk() or not (build / member.name).resolve().is_relative_to(build):
                                raise DeployError("Unsupported package archive member")
                        stream.extractall(build, filter="data")
                    package = build / PACKAGE
                    write_json(package / "src/people_gator_deploy/build.json", {"revision": revision})
                    venv.EnvBuilder(with_pip=True).create(temporary)
                    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PIP_DISABLE_PIP_VERSION_CHECK="1")
                    run([temporary / "bin/python", "-m", "pip", "install", "--no-deps", "--no-compile", str(package)], env=environment, timeout=300)
                for cache in temporary.rglob("__pycache__"):
                    shutil.rmtree(cache)
                # A relative launcher survives atomic directory publication and spaces in paths.
                atomic(temporary / "bin/people-gator-deploy", '#!/bin/sh\nexec "$(dirname -- "$0")/python" -I -B -m people_gator_deploy "$@"\n')
                (temporary / "bin/people-gator-deploy").chmod(0o755)
                metadata = {**paths, "version": __version__, "revision": revision,
                            "config_schema": CONFIG_SCHEMA, "state_schema": STATE_SCHEMA,
                            "run_as": run_as, "files": integrity(temporary)}
                write_json(temporary / "installation.json", metadata)
                if scope == "system":
                    temporary.chmod(0o755)
                    (temporary / "installation.json").chmod(0o644)
                verify(temporary)
                run([temporary / "bin/people-gator-deploy", "--version"], timeout=30)
                temporary.rename(destination)
            finally:
                if temporary.exists():
                    shutil.rmtree(temporary)
        for field in ("config", "state", "bin"):
            path = Path(paths[field])
            path.mkdir(mode=0o700 if field != "bin" else 0o755, parents=True, exist_ok=True)
            if account and field in {"config", "state"}:
                os.chown(path, account.pw_uid, account.pw_gid)
        entry = Path(paths["bin"]) / "people-gator-deploy"
        activate = not entry.exists()
        if entry.is_symlink():
            old = entry.resolve().parent.parent
            previous = verify(old)
            if previous["revision"] == revision:
                activate = True
            else:
                # Retries install a pinned old version but cannot downgrade the default.
                activate = subprocess.run(["git", "-C", str(source), "merge-base", "--is-ancestor",
                                           previous["revision"], revision], capture_output=True).returncode == 0
        elif entry.exists():
            raise DeployError(f"Conflicting executable: {entry}; select another --prefix or resolve it explicitly")
        if activate:
            link = entry.with_name(".people-gator-deploy-" + revision)
            link.unlink(missing_ok=True)
            link.symlink_to(destination / "bin/people-gator-deploy")
            os.replace(link, entry)
    return {**{k: v for k, v in metadata.items() if k != "files"},
            "executable": str(destination / "bin/people-gator-deploy"), "default_activated": activate,
            "path_ready": str(entry.parent) in os.environ.get("PATH", "").split(os.pathsep)}


def ensure(revision=None, *, from_main=False, source=None, scope="user", prefix=None, run_as=None):
    if scope == "system":
        raise DeployError("System upgrades require the operator's canonical deploy/install.py --system --run-as invocation")
    if source:
        return install(Path(source), revision, scope=scope, prefix=prefix, run_as=run_as)
    if not from_main and revision:
        target = Path(layout(scope, prefix)["versions"]) / revision
        if target.exists():
            metadata = verify(target)
            return {**{k: v for k, v in metadata.items() if k != "files"},
                    "executable": str(target / "bin/people-gator-deploy")}
    with tempfile.TemporaryDirectory(prefix="people-gator-update-") as temporary:
        checkout = Path(temporary) / "source"
        run(["git", "clone", "--no-checkout", "--filter=blob:none", REPOSITORY, checkout], timeout=300)
        if from_main:
            revision = git(checkout, "rev-parse", "origin/main")
        else:
            git(checkout, "fetch", "origin", revision)
        return install(checkout, revision, scope=scope, prefix=prefix, run_as=run_as)


def main(source=None):
    parser = argparse.ArgumentParser(description=__doc__)
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--user", action="store_true")
    scope.add_argument("--system", action="store_true")
    parser.add_argument("--revision", required=True)
    parser.add_argument("--prefix", type=Path)
    parser.add_argument("--run-as")
    args = parser.parse_args()
    try:
        result = install(source, args.revision, scope="system" if args.system else "user", prefix=args.prefix, run_as=args.run_as)
        print(json.dumps(result))
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a") as output:
                output.write(f"executable={result['executable']}\n")
    except (DeployError, OSError, subprocess.SubprocessError):
        parser.exit(1, "Installation failed; verify revision, selected scope/prefix, ownership, Python venv and package-index access. Prior installation is preserved.\n")
