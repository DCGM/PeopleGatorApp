"""Single terminal interface for the PeopleGator deployment utility.

Exit codes: 0 success; 1 actionable failure (nothing secret is printed);
2 invalid usage; 130 cancelled (owned workers are terminated).
"""
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

# Operation-specific options; anything else is rejected by argparse.
OPTIONS = {
    "pr": {"status": ["pr"], "check": ["pr"], "logs": ["pr", "tail"], "start": ["pr"], "stop": ["pr"],
           "update": ["run_id"], "cleanup": ["pr"]},
    "staging": {"logs": ["tail"], "update": ["run_id"], "snapshot-init": ["run_id", "exact_key"],
                "refresh": ["run_id", "exact_key", "backup_record"]},
    "release": {"logs": ["tail"], "update": ["tag", "commit", "run_id", "backup_record"],
                "database-migrate": ["backup_record"], "recover": ["backup_record", "compatibility_reviewed"]},
}
ARGUMENTS = {
    "pr": (("--pr",), {"type": int, "help": "Pull request number of one preview instance"}),
    "tail": (("--tail",), {"type": int, "default": 200}),
    "run_id": (("--run-id",), {"type": int, "help": "Successful PR CI run ID"}),
    "exact_key": (("--exact-key",), {"default": "", "help": "Exact dated backup key (snapshot operations)"}),
    "backup_record": (("--backup-record",), {"type": Path, "help": "Private file recording a completed backup"}),
    "tag": (("--tag",), {"help": "Release tag, for example v1.2.3"}),
    "commit": (("--commit",), {"help": "Commit delivered by the tag event; a moved tag is rejected"}),
    "compatibility_reviewed": (("--compatibility-reviewed",), {"action": "store_true"}),
}


def metadata():
    build = Path(__file__).with_name("build.json")
    return {"version": __version__, "revision": json.loads(build.read_text())["revision"] if build.exists() else "development",
            "config_schema": CONFIG_SCHEMA, "state_schema": STATE_SCHEMA}


def parser():
    from .environments import OPERATIONS
    result = argparse.ArgumentParser(prog="people-gator-deploy", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    result.add_argument("--version", action="store_true", help="Print version, source commit and schema versions")
    groups = result.add_subparsers(dest="group")
    utility = groups.add_parser("self", help="Install, verify or update this utility")
    actions = utility.add_subparsers(dest="action", required=True)
    for name in ("ensure", "update", "check"):
        sub = actions.add_parser(name)
        sub.add_argument("--json", action="store_true")
        if name != "check":
            sub.add_argument("--revision")
            sub.add_argument("--from-main", action="store_true")
            sub.add_argument("--source", type=Path, help="Reviewed local repository (never modified)")
            sub.add_argument("--prefix", type=Path)
    for environment in config.ENVIRONMENTS:
        group = groups.add_parser(environment, help=f"{environment} environment lifecycle")
        actions = group.add_subparsers(dest="action", required=True)
        for name in OPERATIONS[environment]:
            sub = actions.add_parser(name)
            sub.add_argument("--config", type=Path, help="Descriptor (else PEOPLE_GATOR_DEPLOY_CONFIG, else scope default)")
            sub.add_argument("--json", action="store_true")
            if name == "configure":
                sub.add_argument("--input", type=Path, help="Private JSON object merged into the descriptor")
                sub.add_argument("--interactive", action="store_true")
                sub.add_argument("--dry-run", action="store_true")
                sub.add_argument("--expected-digest", help="SHA-256 of the descriptor you edited from")
            elif name == "migrate-config":
                sub.add_argument("--dry-run", action="store_true")
            for option in OPTIONS[environment].get(name, []):
                flags, settings = ARGUMENTS[option]
                sub.add_argument(*flags, **settings)
    return result


def configure(args, path, interface):
    original = path.read_bytes() if path.exists() else b""
    changes = json.loads(args.input.read_text()) if args.input else {}
    if args.interactive:
        if not sys.stdin.isatty():
            raise DeployError("--interactive requires a terminal; use --input for CI")
        previous = json.loads(original) if original else {}
        fields = ["repository", "state_dir", "docker_context", "domain" if args.group == "pr" else "host", "web_network"]
        for field in fields:
            supplied = input(f"{field} [{previous.get(field, changes.get(field, ''))}]: ").strip()
            if supplied:
                changes[field] = supplied
        print("Additional nested/private settings can be supplied with --input.", file=sys.stderr)
    elif not args.input:
        interface.error("configure requires --input <private-json> or --interactive")
    return config.configure(args.group, path, changes, dry_run=args.dry_run,
                            expected=args.expected_digest or hashlib.sha256(original).hexdigest())


def main(argv=None):
    interface = parser()
    args = interface.parse_args(argv)
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
                        interface.error("self ensure/update requires --revision or --from-main")
                    if args.action == "update" and not args.from_main and not args.source:
                        interface.error("self update requires --from-main or --source <reviewed checkout>")
                    result = ensure(args.revision, from_main=args.from_main, source=args.source,
                                    scope=current["scope"], prefix=args.prefix or current["prefix"])
            elif args.group:
                path = config.selected(args.group, args.config)
                print(f"{args.group}: descriptor {path} ({config.installation()['scope']} scope)", file=sys.stderr)
                if args.action == "configure":
                    result = configure(args, path, interface)
                elif args.action == "migrate-config":
                    result = config.migrate(args.group, path, dry_run=args.dry_run)
                else:
                    from .environments import Environment
                    options = {key: value for key, value in vars(args).items()
                               if key not in {"group", "action", "config", "version", "json"}}
                    result = Environment(args.group, path).execute(args.action, **options)
                    if args.action == "logs":
                        print(result, end="")
                        return
            else:
                interface.print_help()
                return
            if result is not None:
                print(json.dumps(result, sort_keys=True))
                if os.environ.get("GITHUB_OUTPUT") and isinstance(result, dict) and "executable" in result:
                    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
                        output.write(f"executable={result['executable']}\n")
    except DeployError as error:
        interface.exit(1, f"{error}\n")
    except KeyboardInterrupt:
        interface.exit(130, "Operation cancelled; owned workers terminated; inspect the private operation journal before retrying.\n")
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError) as error:
        interface.exit(1, f"Operation failed ({type(error).__name__}); inspect private state and verify the selected "
                          "configuration, service access and prerequisites. No private input values are printed.\n")
