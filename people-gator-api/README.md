# People Gator API

FastAPI service for person identities, aliases, source provenance, faces, OCR
mentions and reviewed evidence links. It supports typed ingestion and batch
operations, text/face search, media retrieval and processing attribution through
backend-neutral persistence and filesystem contracts. PostgreSQL/pgvector is the
primary development, CI and preview workflow; Weaviate remains an optional adapter.

## Run and test

Use Python 3.14 and the committed uv lockfile:

```sh
uv sync --locked --python 3.14
```

Follow [Development](../docs/DEVELOPMENT.md) for the required PostgreSQL/local
storage `.env`, sample users, migrations, synthetic seed and startup. With those
settings configured, from this directory:

```sh
uv run --locked python -m people_gator_api.cli.database migrate
uv run --locked python -m people_gator_api.cli.seed
uv run --locked python -m people_gator_api.cli.database check
uv run --locked people-gator-api
```

Current settings require exactly one non-null `persistence.postgres` or
`persistence.weaviate` object and one non-null `storage.local` or `storage.s3`
object. Select by configuration presence, not `ENABLED` flags. Native settings
load `.env` relative to this working directory. Local storage needs no S3 keys.

`example.users.json` supplies the development-only `test` / `test` login. Copy it
to `peoplegator_api/users.json` inside the selected storage root without replacing
existing accounts. A missing users file creates an empty object, not a built-in
account. See [Architecture](../docs/ARCHITECTURE.md#access-rules) for JWT scopes,
refresh behavior and the browser's automatic demo login.

Run `uv run --locked pytest tests`. The
[test-store instructions](../docs/DEVELOPMENT.md#test-stores-and-validation) enable
PostgreSQL integration/schema coverage using separate disposable databases.
Never use a retained development or project store for destructive schema tests.

## Contracts and operator guides

- [Architecture](../docs/ARCHITECTURE.md), [Database](../docs/DATABASE.md) and
  [Search filters](../docs/SEARCH_FILTERS.md) describe current implementation.
- [Persistence contracts](src/people_gator_api/persistence/README.md) and
  [Filesystem](src/people_gator_api/filesystem/README.md) describe adapter boundaries.
- [Database migrations](docs/database-migrations.md) cover bootstrap adoption;
  [production startup](docs/production-startup.md) covers validation and roles.
- [Preview seeding](docs/preview-seeding.md) describes repeatable synthetic data
  and feature maintenance.
- [API-key authentication](docs/api-keys.md) and
  [processing filters](docs/entity-processing-filters.md) provide focused references.
- [Deployment](../docs/DEPLOYMENT.md), [Observability](../docs/OBSERVABILITY.md) and
  [Data maintenance](../docs/DATA_MAINTENANCE.md) cover operations.

The running API exposes `/docs`, `/redoc` and `/openapi.json`. Export the local
schema with `uv run --locked python scripts/export_openapi.py /tmp/people-gator-openapi.json`
before regenerating the frontend SDK. External embedding and OpenRouter services
are optional and are not needed for synthetic development. This checkout does
not contain the separately maintained authority-import or OCR/inference packages.
