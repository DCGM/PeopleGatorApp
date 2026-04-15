---
description: "Use when creating new files, packages, or directories in this repository. Enforces monorepo layout and package placement rules."
name: "Monorepo Structure"
---
# Monorepo Structure

## Package Placement Rules

- New Python packages go under `<package-name>/` and must have their own `pyproject.toml` managed by `uv`.
- Shared utilities — Qdrant client, embedding helpers, authority API clients, and shared data models — belong in `people-gator-common/`.
- Face and text embedding inference code belongs in `people-gator-<task>-inference/`.
- Data ingestion pipelines (Kramerius, WikiData, Obaly Knih) belong in `people-gator-ingest/`.
- Model training and fine-tuning code belongs in `people-gator-<task>-training/`.
- The FastAPI service belongs in `people-gator-<task>-api/`.
- One-off research notebooks go in `<package-name>/notebooks/<incrementing-id>_<notebook-name>.ipynb`.
- A Vue frontend, when added, belongs in `people-gator-<app-name>-frontend/`.

## File Placement Rules

- Data models and shared types: `people-gator-common/src/models.py`
- Qdrant collection definitions and client setup: `people-gator-common/src/qdrant.py`
- Authority API client code: `people-gator-common/src/authority/`
- FastAPI route handlers: `people-gator-<task>-api/src/routes/`
- Pydantic request/response schemas: `people-gator-<task>-api/src/schemas/`
- Lightning Modules: `people-gator-<task>-training/src/modules/`
- Lightning Data Modules: `people-gator-<task>-training/src/data_modules/`
- Structured Hydra Configs: `people-gator-<task>-training/src/configs/`
- Training configs: `people-gator-<task>-training/configs/`

## New package initialization

- When adding a new package, create a new directory with a `src/` subdirectory.
- Add a `pyproject.toml` in the root of the package directory with appropriate metadata and dependencies.
- Add the new package to the monorepo's `uv.lock` file by running `uv sync` from the monorepo root after adding the new package's `pyproject.toml`.

## Do Not

- Do not place reusable code directly in the repo root.
- Do not add `__init__.py` files to `notebooks/` subdirectories — keep them as scripts, not importable packages.
- Do not add new packages without a `pyproject.toml` and a `uv.lock` entry.
