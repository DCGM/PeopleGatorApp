# PostgreSQL migrations

Run migrations from the API project directory before starting the API in schema
validation mode:

```sh
uv run python -m people_gator_api.cli.database migrate
uv run python -m people_gator_api.cli.database check
```

The migration command waits for PostgreSQL, serializes concurrent runs with an
advisory transaction lock, applies migrations and validates the resulting schema
before committing. Fresh databases and existing Alembic-managed databases use
the same command. `uv run alembic upgrade head` also applies ordinary migrations.

## Adopting a database created in bootstrap mode

Older installations used `Base.metadata.create_all` to create application tables
while Alembic recorded only an extension revision such as `65c4e6cdfa7f`. Running
`alembic upgrade head` on such a database can fail with `DuplicateTableError` for
`pg_demo_face_models`: the baseline migration is trying to create tables that
already exist. Bootstrap can also create new tables on startup while leaving
new columns absent from existing tables.

Use the explicit adoption option for these databases:

```sh
uv run python -m people_gator_api.cli.database migrate --adopt-bootstrap
```

For live-preview, run it inside the backend container:

```sh
docker compose -f compose.live-preview.yaml exec backend uv run python -m people_gator_api.cli.database migrate --adopt-bootstrap
docker compose -f compose.live-preview.yaml exec backend uv run python -m people_gator_api.cli.database check
```

Adoption compares the existing schema against frozen migration definitions,
including columns, types, nullability, indexes, foreign keys, unique constraints,
primary keys and checks. It recognizes the core baseline (`c82e7f4a901d`), the
baseline plus API-key registry (`d34a021b0001`), the schema including entity
touch fields (`d34a021b0002`), and optional document names (`d34a021b0003`).
The document-name migration adds a nullable text column without changing source
identities; existing names remain NULL until explicitly supplied on a new registration.
Per-model HNSW indexes remain owned by model
registration and are excluded from comparison.

Only a complete matching snapshot can advance the Alembic marker. Missing
migrations then run normally. For example, a database with the API-key table but
without entity touch columns is adopted at `d34a021b0001`, and the touch migration
is applied. Existing identities and API-key IDs are preserved; historical touch
fields remain NULL. Adoption, missing migrations and final validation share a
transaction, so a failure rolls them back together. Re-running the command is
safe once migration history is current.

A partial or structurally different schema is rejected without advancing its
revision. Review and repair the reported differences before retrying. Avoid
manually stamping `head`: doing so would mark missing columns as already applied.
`check --schema-only` compares against the current application schema, so it is
not a historical baseline adoption check.

For deployments managed by migrations, configure PostgreSQL `schema_mode` as
`validate` and run the migration command before starting the backend. This makes
schema changes explicit instead of relying on bootstrap to create missing tables.
