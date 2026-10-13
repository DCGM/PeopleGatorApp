"""Export the local API contract without starting services or accessing a database.

Run with the application's normal settings/environment:
    uv run python scripts/export_openapi.py /tmp/people-gator-openapi.json
"""

import argparse
import json
from pathlib import Path

# The schema package initializes the existing shared settings dependency first.
import people_gator_api.schemas  # noqa: F401
from people_gator_api.app import get_app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(get_app().openapi(), indent=2) + "\n")


if __name__ == "__main__":
    main()
