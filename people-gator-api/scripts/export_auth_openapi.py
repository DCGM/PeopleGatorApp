"""Export the independent issuer contract without resource configuration."""
import argparse
import json
from pathlib import Path
from people_gator_api.auth.app import get_app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(get_app().openapi(), indent=2) + "\n")


if __name__ == "__main__":
    main()
