"""Run with explicit private configuration; never initialize API settings."""
import argparse
import os
from pathlib import Path
import sys

from .core import BackupError, publish, read_config


def main(argv=None):
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["publish"])
    parser.add_argument("--config", type=Path, required=True, help="Private mode-600 JSON file, or - for stdin")
    args = parser.parse_args(argv)
    publish(read_config(args.config))
    print("Database backup published and verified")


if __name__ == "__main__":
    try:
        main()
    except BackupError as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
    except Exception:
        print("Backup operation failed; check private configuration, storage permissions and connectivity", file=sys.stderr)
        sys.exit(1)
