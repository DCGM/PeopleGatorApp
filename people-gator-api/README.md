# people-gator-api

Backend service for People Gator.

This repository keeps specification content in focused documents to avoid contradictions between product goals, architecture choices, and API contracts:

1. Product specification: `docs/01-product-spec.md`
2. Entity relations: `docs/02-entity-relations.md`
3. Architecture specification: `docs/03-architecture-spec.md`
4. API contract: `docs/04-api-contract.md`

## Quick Summary

- Primary goal: annotation-first person search and grounding tool.
- Core flow: search evidence -> build grounding versions and entity proposals -> annotate -> review.
- Inference is out of scope for this package; only prepared artifacts are ingested.
- Search uses a single MVP endpoint: `POST /search`.
- Fusion weights come only from saved search profiles.
- All collection endpoints use the contract list envelope: `items`, opaque
  string `cursor`, `limit`, and optional `total_count`.

## Filesystem storage

Storage defaults to S3. To use local storage instead, configure:

```dotenv
PEOPLE_GATOR_API__STORAGE__LOCAL__ENABLED=true
PEOPLE_GATOR_API__STORAGE__LOCAL__ROOT=/var/lib/people-gator/storage
```

Exactly one backend must be enabled. Configured S3 defaults to enabled; local
storage defaults to disabled. If S3 settings are also supplied, set
`PEOPLE_GATOR_API__STORAGE__S3__ENABLED=false` when enabling local storage.
The `STORAGE__BACKEND` selector is replaced by these enabled flags.

Local mode does not require S3 credentials. Services use `get_filesystem()` and
FastAPI routes can inject `FilesystemDependency` from
`people_gator_api.services.filesystem_service`. See the
[filesystem documentation](src/people_gator_api/filesystem/README.md) for usage.

## Login users file

Login credentials and allowed scopes are stored in a dedicated JSON file using
the same configured filesystem as the JWK key set. Configure its relative path:

```dotenv
PEOPLE_GATOR_API__JWK__USERS_PATH=peoplegator_api/users.json
```

This is also the default. With local storage, the file is under
`STORAGE__LOCAL__ROOT`; with S3, the path is an object key in the configured bucket.
A missing file is created as `{}` on the first login attempt. Add users before
logging in; the hardcoded `test` account is no longer provided. The format is a
JSON object keyed by username:

```json
{
  "alice": {
    "hash": "<Argon2 password hash>",
    "scopes": ["people-gator:browse", "people-gator:annotate"]
  }
}
```

See [example.users.json](example.users.json) for a working example with username
`alice` and password `change-me`. Copy it to the configured users path in local
storage or upload it to the configured S3 key. Replace the example password hash
before using it outside development.

Generate a hash with `uv run python -c 'import argon2, getpass; print(argon2.PasswordHasher().hash(getpass.getpass()))'`.
Each entry requires `hash` and `scopes`; use an empty scopes list to grant no
permissions. Available scopes are `people-gator:browse`, `people-gator:annotate`,
`people-gator:ingest`, and `people-gator:admin`. Login requests can only request
scopes allowed for that user. Login and refresh reload the file, so credential
changes, user removal, and scope changes apply without restarting the API.
Refresh is rejected if a session's scopes are no longer allowed. Already issued
access tokens remain valid until they expire.

Refresh sessions are kept only in memory, rotate on use, and
remain limited to four per user. Restarting the API invalidates all refresh
sessions. With multiple workers, refresh requests must reach the worker that
issued the token. Login and refresh do not rewrite an existing users file.

## Page asset uploads

Users with the `people-gator:ingest` scope can create or replace assets for an
existing page Source UUID:

- `PUT /pages/{page_source_id}/image`: multipart form data with a `file` field.
  Images are validated and stored as JPEG; existing JPEG bytes are preserved.
  The original and all configured resized copies are replaced.
- `PUT /pages/{page_source_id}/page-layout`: a JSON `PageLayoutModel` body
  containing `id`, `page_size`, `regions`, and `reading_order`. Returns the
  upload receipt.

Both return `200` with a `FileUploadResponse` containing `source_id`,
`uploaded_at` (the UTC completion time), `size_bytes`, and `media_type`.
The size is the stored file's byte count after conversion or UTF-8 JSON
serialization; resized image copies are excluded. Fetch the image or layout
through the corresponding GET endpoint.

Both endpoints return `404` for an unknown page, `422` for invalid uploads,
and `502` for storage failures.

## Authority Import

Authority ingestion CLI now lives in `people-gator-common` as `people-gator-import-authorities`.

Run it from the common package:

```bash
cd ../people-gator-common
uv run people-gator-import-authorities --help
```

## Weaviate operations

`compose.dev.yaml` keeps the Weaviate version pinned and enables single-node
Raft recovery so persisted collections survive container recreation. Its health
check waits for the database, Raft leader, and schema to be ready before API or
backup services start.

The compose stack creates a verified native filesystem backup when none exists
and every 24 hours thereafter. Backups are stored outside the live-data
filesystem and the three newest backups are retained. These optional `.env`
settings override the defaults:

```dotenv
WEAVIATE_BACKUP_HOST_PATH=/mnt/backup/PeopleGator-backups/weaviate-dev
WEAVIATE_BACKUP_KEEP_COUNT=3
WEAVIATE_BACKUP_INTERVAL_SECONDS=86400
WEAVIATE_BACKUP_RETRY_SECONDS=300
WEAVIATE_BACKUP_TIMEOUT_SECONDS=21600
```

To inspect backups:

```bash
curl http://localhost:8080/v1/backups/filesystem
```

## Persistence selection

Exactly one persistence backend must be enabled. Configured PostgreSQL defaults
to enabled; Weaviate defaults to disabled. To select Weaviate when both are
configured:

```dotenv
PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__ENABLED=false
PEOPLE_GATOR_API__PERSISTENCE__WEAVIATE__ENABLED=true
```

Unused connection configurations can be omitted. See the
[persistence documentation](src/people_gator_api/persistence/README.md) for details.

## PostgreSQL persistence

The API persistence boundary is implemented by PostgreSQL using SQLAlchemy,
pgvector embeddings, and PostgreSQL trigram text search. API routes receive the
backend-neutral `Database` facade and do not depend on SQLAlchemy sessions.
The relational models and schema bootstrap currently live in
[`src/people_gator_api/services/postgres_demo`](src/people_gator_api/services/postgres_demo/README.md).

The shared Weaviate/PostgreSQL repository contracts and concrete adapters are
documented in
[`src/people_gator_api/persistence`](src/people_gator_api/persistence/README.md).

### Database migrations

For production container startup, schema validation, and the one-shot migration
job, see [production startup](docs/production-startup.md). The production image
validates schema at startup; development retains automatic schema bootstrap.

Alembic uses the SQLAlchemy metadata in `people_gator_api.persistence.postgres.models` and the
PostgreSQL settings from `.env`:

```bash
uv run alembic revision --autogenerate -m "describe schema change"
uv run alembic upgrade head
```

Review autogenerated revisions before applying them. A fresh PostgreSQL database
can be initialized with `alembic upgrade head`. Existing databases bootstrapped by
`people-gator-init-db` must be verified and stamped as described in the production
startup documentation before adopting the migration history.
