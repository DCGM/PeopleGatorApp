---
description: "Use when creating or modifying Python code in this repository. Enforces uv-based dependency management and lockfile reproducibility rules."
name: "Python Uv Requirements"
applyTo: "**/*.py"
---
# Python Uv Requirements

- Use uv as the project and dependency manager for Python work.
- Keep dependency changes compatible with uv workflows.
- Treat lockfile reproducibility as mandatory.
- Commit uv.lock when Python dependencies are changed.
