"""Single terminal interface for the PeopleGator deployment utility.

Operations run from the repository checkout of the commit being deployed and
read their settings from DEPLOY_* variables (a GitHub Environment's variables
and secrets in CI). Exit codes: 0 success; 1 actionable failure (nothing secret
is printed); 2 invalid usage; 130 cancelled (owned workers are terminated).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

from . import __version__, STATE_SCHEMA
from .core import DeployError, cancellation
from . import config

# Operation-specific options; anything else is rejected by argparse.
OPTIONS = {
    "pr": {"status": ["pr"], "check": ["pr"], "logs": ["pr", "tail"], "start": ["pr"], "stop": ["pr"],
           "update": ["pr", "sha"], "cleanup": ["pr"]},
    "staging": {"logs": ["tail"], "update": ["sha"], "snapshot-init": ["sha"],
                "refresh": ["sha", "backup_record"]},
    "release": {"logs": ["tail"], "update": ["tag", "sha", "backup_record"],
                "database-migrate": ["backup_record"], "recover": ["backup_record", "compatibility_reviewed"]},
}
ARGUMENTS = {
    "pr": (("--pr",), {"type": int, "help": "Pull request number of one preview instance"}),
    "tail": (("--tail",), {"type": int, "default": 200}),
    "sha": (("--sha",), {"help": "Tested commit whose sha-<commit> images this workflow run published"}),
    "backup_record": (("--backup-record",), {"type": Path, "help": "Private file recording a completed backup"}),
    "tag": (("--tag",), {"help": "Release tag, for example v1.2.3"}),
    "compatibility_reviewed": (("--compatibility-reviewed",), {"action": "store_true"}),
}
DEPLOYMENT_ENVIRONMENTS = ("preview", "staging", "production")


def parser():
    from .environments import OPERATIONS
    result = argparse.ArgumentParser(prog="people-gator-deploy", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    result.add_argument("--version", action="store_true", help="Print the utility and state schema versions")
    groups = result.add_subparsers(dest="group")
    for environment in config.ENVIRONMENTS:
        group = groups.add_parser(environment, help=f"{environment} environment lifecycle")
        actions = group.add_subparsers(dest="action", required=True)
        for name in OPERATIONS[environment]:
            sub = actions.add_parser(name)
            sub.add_argument("--json", action="store_true")
            for option in OPTIONS[environment].get(name, []):
                flags, settings = ARGUMENTS[option]
                sub.add_argument(*flags, **settings)
    deployments = groups.add_parser("deployments", help="Keep only current GitHub Deployments active")
    actions = deployments.add_subparsers(dest="action", required=True)
    supersede = actions.add_parser("supersede", help="Set older deployments of an environment inactive")
    supersede.add_argument("environment", choices=DEPLOYMENT_ENVIRONMENTS)
    supersede.add_argument("--ref", help="Only deployments of this ref (PR head branch for previews)")
    retire = actions.add_parser("retire", help="Set every preview deployment of a closed PR's branch inactive")
    retire.add_argument("--ref", required=True)
    actions.add_parser("prune", help="Retire closed PRs' previews and older staging/production deployments")
    return result


def main(argv=None):
    interface = parser()
    args = interface.parse_args(argv)
    try:
        with cancellation():
            if args.version:
                result = {"version": __version__, "state_schema": STATE_SCHEMA}
            elif args.group == "deployments":
                from .deployments import Deployments
                result = Deployments().execute(args.action, environment=getattr(args, "environment", None),
                                               ref=getattr(args, "ref", None))
            elif args.group:
                from .environments import Environment
                options = {key: value for key, value in vars(args).items()
                           if key not in {"group", "action", "version", "json"}}
                result = Environment(args.group).execute(args.action, **options)
                if args.action == "logs":
                    print(result, end="")
                    return
            else:
                interface.print_help()
                return
            if result is not None:
                print(json.dumps(result, sort_keys=True))
    except DeployError as error:
        interface.exit(1, f"{error}\n")
    except KeyboardInterrupt:
        interface.exit(130, "Operation cancelled; owned workers terminated; inspect the private operation journal before retrying.\n")
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError) as error:
        interface.exit(1, f"Operation failed ({type(error).__name__}); inspect private state and verify the selected "
                          "configuration, service access and prerequisites. No private input values are printed.\n")
