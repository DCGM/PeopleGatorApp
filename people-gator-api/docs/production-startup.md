# Production PostgreSQL startup

The production `Dockerfile` uses `scripts/container-entrypoint.sh`. It supports
`api` (default), `migrate`, and `check`. This flow requires PostgreSQL. Development
Compose continues to use `Dockerfile.dev` and its automatic schema bootstrap.

The API entrypoint forces debug/reload off and PostgreSQL `schema_mode=validate`.
The API lifespan waits for database connectivity, then checks the exact Alembic
head revision, required extensions, `demo_unaccent(text)`, and structural drift
against SQLAlchemy metadata. A failed check exits startup before serving requests.
The schema check runs in a read-only transaction and never creates or updates
tables, extensions, indexes, or functions. Every API worker performs its own check.

Alembic comparison covers tables, columns, types, nullability, foreign keys,
unique constraints, and static indexes. Generated-expression comparison warnings
also fail validation. Model-specific HNSW indexes are managed by model registration
and excluded, as in migration autogeneration. Other applications' tables are
ignored. This is not a comprehensive comparison of CHECK/primary-key constraints,
function bodies, extension versions, runtime privileges, or model-specific indexes;
exercise those in migration and application integration tests.

## Deployment order

Provision PostgreSQL with pgvector available, then build the application image:

```sh
docker build -t people-gator-api:release .
```

Supply connection settings through environment variables or your deployment's
secret injection. `runtime.env` should contain only a PostgreSQL persistence
configuration plus the other application settings. Use the separate migration
role in `migration.env`. Do not configure Weaviate in this production flow.

```dotenv
PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__HOST=postgres
PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__PORT=5432
PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__USER=people_gator_runtime
PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__PASSWORD=...
PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__DATABASE=people_gator
PEOPLE_GATOR_API__STORAGE__LOCAL__ROOT=/data
```

Run exactly one migration job per deployment, and start or roll out the API only
after that job succeeds. Both containers must reach the provisioned database;
replace `production` with your container network.

```sh
docker run --rm --network production --env-file migration.env people-gator-api:release migrate
docker run -d --name people-gator-api --network production --env-file runtime.env \
  -p 8000:8000 people-gator-api:release api
```

`migrate` waits for connectivity, runs `alembic upgrade head`, then validates the
result. It does not start the API. Never run this command in every API replica or
put concurrent migration jobs in the rollout. Review and test migrations before
deployment; for rolling updates they must remain compatible with the old API
until all replicas have been replaced.

Grant the runtime role schema USAGE, table CRUD, SELECT on `alembic_version`, and
EXECUTE on the helper function. Keep schema/extension changes with the deployment
role. Account separately for face-model registration: it creates per-model HNSW
indexes and therefore requires table ownership/DDL privileges. Provision models
with an administrative process before serving traffic with a restricted role.
Local storage volumes must be writable by container UID/GID `10001:10001`.

Connectivity waits default to 60 seconds, with 2-second retries. Override with
`PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__STARTUP_TIMEOUT_SECONDS` and
`PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__STARTUP_RETRY_INTERVAL_SECONDS`.
Authentication, permission, and schema errors fail rather than retrying schema
checks. Migrations are never generated inside a running container.

## Adopting an existing bootstrapped database

The two earlier revisions only installed extensions and the helper function.
Revision `c82e7f4a901d` adds the frozen table/index definitions for a fresh database.
An existing `create_all()` database already has those tables, so do not apply this
creation revision over it. Back it up and verify its structure first:

```sh
docker run --rm --network production --env-file runtime.env people-gator-api:release check --schema-only
```

Only if that check passes and the constraints/functions have been reviewed, an
operator can record the matching baseline with the deployment role:

```sh
docker run --rm --network production --env-file migration.env \
  --entrypoint alembic people-gator-api:release stamp c82e7f4a901d
docker run --rm --network production --env-file runtime.env people-gator-api:release check
```

Stamping changes only migration history, not structure. Resolve reported drift
with a reviewed migration before stamping. Never stamp an empty database.

## Verification

The opt-in schema integration test requires an empty, disposable database:

```sh
PEOPLE_GATOR_SCHEMA_TEST_URL=postgresql+asyncpg://test:test@localhost:5432/test \
  uv run pytest tests/services/persistence/test_postgres_schema_validation.py
```

It applies the full migration chain, checks repeated upgrades, rejects revision,
column, index, and function drift, and validates with a restricted runtime role.
