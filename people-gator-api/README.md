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

## PostgreSQL persistence

The API persistence boundary is implemented by PostgreSQL using SQLAlchemy,
pgvector embeddings, and PostgreSQL trigram text search. API routes receive the
backend-neutral `Database` facade and do not depend on SQLAlchemy sessions.
The relational models and schema bootstrap currently live in
[`src/people_gator_api/services/postgres_demo`](src/people_gator_api/services/postgres_demo/README.md).

The shared Weaviate/PostgreSQL repository contracts and concrete adapters are
documented in
[`src/people_gator_api/persistence`](src/people_gator_api/persistence/README.md).
