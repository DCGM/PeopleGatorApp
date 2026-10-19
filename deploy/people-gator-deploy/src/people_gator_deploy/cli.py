"""Single terminal interface for the deployment utility."""
import argparse
import json
from pathlib import Path
import sys

from . import __version__, CONFIG_SCHEMA, STATE_SCHEMA
from .core import DeployError


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="store_true")
    args = parser.parse_args(argv)
    if args.version:
        build = Path(__file__).with_name("build.json")
        print(json.dumps({"version": __version__, "revision": json.loads(build.read_text())["revision"] if build.exists() else "development",
                          "config_schema": CONFIG_SCHEMA, "state_schema": STATE_SCHEMA}))
        return
    parser.print_help()
