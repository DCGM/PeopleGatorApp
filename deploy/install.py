#!/usr/bin/env python3
"""Canonical bootstrap. Execute only from an explicitly reviewed checkout."""
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent / "people-gator-deploy" / "src"))
from people_gator_deploy.installer import main

if __name__ == "__main__":
    main(source=Path(__file__).resolve().parents[1])
