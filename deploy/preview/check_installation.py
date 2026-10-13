"""Reject a stale preview host before deploying a candidate image.

Run this from the exact reviewed workflow revision, never a PR checkout. The
host's controller and Compose template remain installed by an operator.
"""

import argparse
from pathlib import Path
import shlex


DEPLOYMENT_FILES = ("preview.py", "compose.pr.yaml")


def check_installation(expected: Path, installed: Path) -> None:
    stale = [
        name for name in DEPLOYMENT_FILES
        if not (installed / name).is_file()
        or (installed / name).read_bytes() != (expected / name).read_bytes()
    ]
    if stale:
        command = shlex.join([
            "sudo", "install", "-m", "644",
            *(str(expected / name) for name in DEPLOYMENT_FILES), str(installed) + "/",
        ])
        raise RuntimeError(
            "Preview host installation is out of date: " + ", ".join(stale)
            + ". Refusing deployment because the installed lifecycle may skip seeding. "
            + "Install the controller and Compose template from this reviewed workflow "
            + "revision, preserving config.json and state, then rerun the lifecycle job:\n"
            + command
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installed", type=Path, default=Path("/opt/people-gator-preview"))
    args = parser.parse_args()
    try:
        check_installation(Path(__file__).resolve().parent, args.installed)
    except (OSError, RuntimeError) as error:
        parser.exit(1, str(error) + "\n")
    print("Installed preview lifecycle matches the trusted workflow revision; seeding is required.")


if __name__ == "__main__":
    main()
