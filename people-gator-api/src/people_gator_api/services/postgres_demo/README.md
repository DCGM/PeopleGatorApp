# PostgreSQL persistence demo

This package is an opt-in relational implementation that can run beside the
current Weaviate service. Nothing imports it from API startup, so merely adding
the demo does not alter production persistence.

It uses:

- SQLAlchemy 2 async ORM and `asyncpg`;
- `pgvector` for model-keyed entity and image-occurrence embeddings;
- PostgreSQL `tsvector`/`websearch_to_tsquery` for full-text search;
- the `pg_trgm` extension for typo-tolerant name and alias similarity;
- joined-table inheritance for `Source -> Document | Page | Image` and
  `ImageOccurrence -> Face`.

## Run it

Start only the demo database from `people-gator-api`:

```bash
docker compose --profile postgres-demo up -d people-gator-postgres-demo
```

Create the schema explicitly (the existing API lifecycle remains untouched):

```python
import asyncio

from people_gator_api.services.postgres_demo import (
    create_postgres_schema,
    make_postgres_engine,
)

engine = make_postgres_engine(
    "postgresql+asyncpg://people_gator:people_gator@localhost:5433/people_gator"
)
asyncio.run(create_postgres_schema(engine))
```

The requested cross-domain query is exposed as:

```python
hits = await search_entities_by_alias_excluding_document(
    session,
    "Tomas Garrigue Masaryk",
    DocumentRef(library="mzk", document_id=document_id),
)
```

The query ranks aliases with the better of trigram and full-text scores. Its
correlated `NOT EXISTS` removes an entity when any assigned `Face` comes from
the exact document source or from a page carrying the same `(library,
document_id)` identity. Unassigned faces do not exclude anything.

## Per-model vector indexes

The vector columns are dimensionless so models of different sizes can coexist.
For each production model, add a partial expression index with its dimension;
the query builders make the matching cast:

```sql
CREATE INDEX ix_pg_demo_entity_harrier_description_hnsw
ON pg_demo_entity_embeddings
USING hnsw ((embedding::vector(768)) vector_cosine_ops)
WHERE model = 'microsoft/harrier-oss-v1-0.6b'
  AND field = 'description'
  AND dimensions = 768;

CREATE INDEX ix_pg_demo_face_vit_hnsw
ON pg_demo_image_occurrence_embeddings
USING hnsw ((embedding::vector(512)) vector_cosine_ops)
WHERE model = 'vit_small_patch8_gap_112.cosface_ms1mv3'
  AND dimensions = 512;
```

Adding another model is a data operation plus an optional model-specific index,
not a table migration.

Creation and update commands can write several embeddings at once. Entity
embeddings are keyed by `(entity_id, field, model)` and face embeddings by
`(occurrence_id, model)`, so a batch can update existing vectors and insert new
model slots in the same transaction.
