"""Single terminal interface for the deployment utility."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from . import __version__, CONFIG_SCHEMA, STATE_SCHEMA
from .core import DeployError, cancellation
from . import config


def metadata():
    build = Path(__file__).with_name("build.json")
    return {"version": __version__, "revision": json.loads(build.read_text())["revision"] if build.exists() else "development",
            "config_schema": CONFIG_SCHEMA, "state_schema": STATE_SCHEMA}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="store_true")
    groups = parser.add_subparsers(dest="group")
    utility = groups.add_parser("self")
    actions = utility.add_subparsers(dest="action", required=True)
    for name in ("ensure", "update", "check"):
        sub = actions.add_parser(name)
        sub.add_argument("--json", action="store_true")
        if name != "check":
            sub.add_argument("--revision")
            sub.add_argument("--from-main", action="store_true")
            sub.add_argument("--source", type=Path)
            sub.add_argument("--prefix", type=Path)
    for environment in config.ENVIRONMENTS:
        group = groups.add_parser(environment)
        actions = group.add_subparsers(dest="action", required=True)
        for name in ("configure", "migrate-config", "install", "update", "uninstall", "check", "status",
                     "start", "stop", "logs", "cleanup", "reconcile", "refresh", "snapshot-init", "database-check",
                     "database-migrate", "infra-install", "infra-upgrade", "migration-inspect", "adopt", "recover"):
            if name in {"cleanup", "reconcile"} and environment != "pr":
                continue
            if name in {"refresh", "snapshot-init"} and environment != "staging":
                continue
            if name == "recover" and environment != "release":
                continue
            sub = actions.add_parser(name)
            sub.add_argument("--config", type=Path)
            sub.add_argument("--json", action="store_true")
            sub.add_argument("--pr", type=int)
            sub.add_argument("--run-id", type=int)
            sub.add_argument("--tag")
            sub.add_argument("--commit")
            sub.add_argument("--exact-key", default="")
            sub.add_argument("--legacy-config", type=Path)
            sub.add_argument("--dry-run", action="store_true")
            sub.add_argument("--input", type=Path)
            sub.add_argument("--interactive", action="store_true")
            sub.add_argument("--expected-digest")
            sub.add_argument("--backup-record", type=Path)
            sub.add_argument("--compatibility-reviewed", action="store_true")
    args = parser.parse_args(argv)
    try:
        with cancellation():
            if args.version:
                result = metadata()
            elif args.group == "self":
                from .installer import ensure, verify
                current = config.installation()
                if args.action == "check":
                    if not (Path(sys.prefix) / "installation.json").exists():
                        raise DeployError("Integrity requires a canonical versioned installation; run deploy/install.py")
                    verified = verify(Path(sys.prefix))
                    result = {k: v for k, v in verified.items() if k != "files"}
                else:
                    if not args.from_main and not args.revision:
                        parser.error("self ensure/update requires --revision or --from-main")
                    result = ensure(args.revision, from_main=args.from_main, source=args.source,
                                    scope=current["scope"], prefix=args.prefix or current["prefix"])
            elif args.group:
                path = config.selected(args.group, args.config)
                if args.action == "configure":
                    original = path.read_bytes() if path.exists() else b""
                    changes = json.loads(args.input.read_text()) if args.input else {}
                    if args.interactive:
                        if not sys.stdin.isatty():
                            raise DeployError("--interactive requires a terminal; use --input for CI")
                        previous = json.loads(original) if original else {}
                        for field in ("repository", "state_dir", "docker_context", "domain" if args.group == "pr" else "host", "web_network"):
                            supplied = input(f"{field} [{previous.get(field, changes.get(field, ''))}]: ").strip()
                            if supplied:
                                changes[field] = supplied
                        print("Additional nested/private settings can be supplied with --input.", file=sys.stderr)
                    elif not args.input:
                        parser.error("configure requires --input <private-json> or --interactive")
                    result = config.configure(args.group, path, changes, dry_run=args.dry_run,
                                              expected=args.expected_digest or hashlib.sha256(original).hexdigest())
                elif args.action == "migrate-config":
                    result = config.migrate(args.group, path, dry_run=args.dry_run)
                else:
                    from .environments import Environment
                    result = Environment(args.group, path).execute(args.action, **{
                        key: value for key, value in vars(args).items()
                        if key not in {"group", "action", "config", "version", "json"}})
            else:
                parser.print_help()
                return
            if result is not None:
                print(json.dumps(result, sort_keys=True))
                if os.environ.get("GITHUB_OUTPUT") and isinstance(result, dict) and "executable" in result:
                    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
                        output.write(f"executable={result['executable']}\n")
    except DeployError as error:
        parser.exit(1, f"{error}\n")
    except KeyboardInterrupt:
        parser.exit(130, "Operation cancelled; owned workers terminated; inspect the private operation journal before retrying.\n")
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError):
        parser.exit(1, "Operation failed; inspect private state and verify selected configuration, service access and prerequisites. No private input values are printed.\n")
