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

Live-preview now runs `migrate --adopt-bootstrap` before starting the API and
uses `schema_mode: validate`. A failed migration prevents API startup. This
preserves the database and applies missing columns and backfills on each backend
start; bootstrap alone only creates missing tables. For an already running
preview after updating the Compose configuration, recreate its backend:

```sh
docker compose -f compose.live-preview.yaml up -d --wait backend
```

If the backend is stopped or unable to start, run a one-off migration using the
same image and configuration, then start it again:

```sh
docker compose -f compose.live-preview.yaml run --rm --no-deps backend uv run python -m people_gator_api.cli.database migrate --adopt-bootstrap
docker compose -f compose.live-preview.yaml up -d --wait backend
```

Restart the backend after syncing migration changes with Compose Watch; Python
worker reloads do not rerun the container's startup command. Validation rejects
an old schema instead of serving requests against missing columns. Take a
database backup before upgrading an existing preview; do not reset its volumes
or stamp the latest revision to bypass migration operations.

Adoption compares the existing schema against frozen migration definitions,
including columns, types, nullability, indexes, foreign keys, unique constraints,
primary keys and checks. It recognizes the core baseline (`c82e7f4a901d`), the
baseline plus API-key registry (`d34a021b0001`), the schema including entity
touch fields (`d34a021b0002`), and optional document names (`d34a021b0003`).
The document-name migration adds a nullable text column without changing source
identities; existing names remain NULL until explicitly supplied on a new registration.
The link-state migration (`d34a021b0004`) also accepts an enum type left behind
by bootstrap, provided its values and order match exactly in the current schema,
and replaces bootstrap's link-cleanup triggers with the migration definitions.
It still applies the columns, historical automatic backfill, constraints, and
indexes normally. A conflicting enum is rejected without advancing the revision.
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

After the frozen bootstrap snapshots, an existing known Alembic revision remains
unchanged by `--adopt-bootstrap`; normal migrations advance it to the new head.
This includes upgrading revision `d34a021b0004` to the source processing and
document search migrations. The resulting schema is validated before the same
transaction commits. Unknown or conflicting revision histories still fail.

The annotation metadata upgrade (`d34a021b0008`) preserves recorded creation and
last-change times, actors, assignments and all record identities while dropping
the unused classification JSON payload. Previously deployed revision
`d34a021b0007` upgrades normally; no preview reset or reseeding of existing
records is needed. Downgrading restores nullable columns without fabricating
removed values.

The person-portrait migration (`d34a021b0009`) adds a nullable face reference and
an automatic/manual policy. Historical people receive the lowest linked face UUID
(or no thumbnail), always in automatic mode. It preserves identities, annotations,
verification and all creation/processing metadata; it does not access media or
external services. Foreign keys, checks and triggers maintain ownership through
reassignment and cascade deletion. Run the normal migrate/check commands before
starting this application revision; bootstrap alone cannot upgrade retained tables.
Back up the retained database and matching storage first. Downgrade discards
portrait preferences but preserves people and evidence. See
[person portraits](PERSON-THUMBNAILS.md) for PATCH, selection and lifecycle details.
