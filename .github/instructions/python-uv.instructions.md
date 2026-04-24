---
description: "Use when creating or modifying Python code in this repository. Enforces uv-based dependency management and lockfile reproducibility rules."
name: "Python Uv Requirements"
applyTo: "**/*.py"
---
# Python Uv Requirements

- Use uv as the project and dependency manager for Python work.
- Always use `uv init --package --vcs none <project-name>` to create a new Python project.
- Always use `uv add <package1> <package2> ...` to add new dependencies.
- If you need to add a development dependency, use `uv add --dev <package-name>`.
- Modify `pyproject.toml` directly only for non-dependency related changes (e.g., project metadata).
- Allowed modification of `pyproject.toml` is also for adding runnable modules under the `[project.scripts]` section.
- All dependency changes must be made through `uv` commands to ensure proper lockfile updates.
- Always install `ipykernel` as a development dependency for Python projects to enable Jupyter notebook support.
- Keep dependency changes compatible with uv workflows.
- Use absolute package imports in Python modules; avoid relative imports.
- Treat lockfile reproducibility as mandatory.
- Commit uv.lock when Python dependencies are changed.
