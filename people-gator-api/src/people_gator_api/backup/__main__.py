"""Run with explicit private configuration; never initialize API settings."""
import argparse
import os
from pathlib import Path
import sys

from .core import BackupError, publish, read_config


def main(argv=None):
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["publish", "restore"])
    parser.add_argument("--config", type=Path, required=True, help="Private mode-600 JSON file, or - for stdin")
    parser.add_argument("--exact-key", default="", help="Restore an exact dated key inside the configured prefix")
    parser.add_argument("--report", type=Path, help="New private restore provenance file in a mode-700 directory")
    args = parser.parse_args(argv)
    if args.action == "restore":
        if args.report is None:
            parser.error("restore requires --report")
        from .restore import restore
        restore(read_config(args.config), args.report, exact_key=args.exact_key)
        print("Database restored and private provenance recorded")
    else:
        if args.report is not None or args.exact_key:
            parser.error("--report and --exact-key apply only to restore")
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
