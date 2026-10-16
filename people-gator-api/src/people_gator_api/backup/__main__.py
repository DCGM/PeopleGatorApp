"""Run with explicit private configuration; never initialize API settings."""
import argparse
import os
from pathlib import Path
import sys

from .core import BackupError, publish, read_config


def main(argv=None):
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["publish", "restore", "schedule"])
    parser.add_argument("--config", type=Path, required=True, help="Private mode-600 JSON file, or - for stdin")
    parser.add_argument("--exact-key", default="", help="Restore an exact dated key inside the configured prefix")
    parser.add_argument("--report", type=Path, help="New private restore provenance file in a mode-700 directory")
    parser.add_argument("--lock-file", type=Path, help="Shared private agent lock for scheduled/manual publication")
    parser.add_argument("--at", default="02:00", help="Daily scheduled backup time in UTC (HH:MM)")
    parser.add_argument("--retry-seconds", type=int, default=300, help="Scheduled failure retry delay")
    args = parser.parse_args(argv)
    if args.action == "schedule":
        if args.lock_file is None or args.report is not None or args.exact_key:
            parser.error("schedule requires --lock-file and cannot use restore options")
        from .scheduler import serve
        serve(args.config, args.at, args.retry_seconds, args.lock_file)
    elif args.action == "restore":
        if args.report is None:
            parser.error("restore requires --report")
        if args.lock_file is not None:
            parser.error("restore does not use the publisher agent lock")
        from .restore import restore
        restore(read_config(args.config), args.report, exact_key=args.exact_key)
        print("Database restored and private provenance recorded")
    else:
        if args.report is not None or args.exact_key:
            parser.error("--report and --exact-key apply only to restore")
        if args.lock_file is not None:
            from .scheduler import agent_lock
            with agent_lock(args.lock_file):
                publish(read_config(args.config))
        else:
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
