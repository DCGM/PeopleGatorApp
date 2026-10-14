# Persistence interface

This package is the backend-neutral persistence boundary. Routes and services
depend on the Database facade; repositories do not expose Weaviate clients,
SQLAlchemy sessions, backend filters, or transaction objects.

Database exposes repositories for entities, sources, faces, text mentions, and
users. Page, document, and image APIs are typed projections of the source
repository.

## Shared behavior

Ordinary list operations order records by UUID ascending. Search operations
order by final score descending and UUID ascending. Cursors are opaque strings,
exclusive, backend-defined, and valid only with the same query inputs.
`total_count`, when requested, counts all filter matches before cursor and
limit.

Different filter fields use logical AND. Values inside one filter list use
logical OR. Empty filter lists are invalid.

Search aggregates higher-is-better scores independently inside the text and
face modalities. It then fuses modality ranks with reciprocal-rank fusion using
the constants documented in schemas.search.
Raw text relevance is backend-native; only score direction, aggregation, fusion,
and deterministic tie-breaking are portable.

## Source identity

Source URLs are globally unique. Type-specific identities are immutable:

- page: (library, document_id, page_id)
- document: (library, document_id)
- image: normalized URL

Page and document URLs are their canonical Digitalni Knihovna URLs.
get_or_create returns CreateResult.CREATED or CreateResult.EXISTING. Within a
batch, the first new occurrence is CREATED; later duplicate occurrences are
EXISTING. Results preserve input order.

## Relationships and deletion

Every referenced user, source, entity, or face must exist before a write.
Deleting an entity unassigns its faces and text mentions. Deleting a source
cascades its faces and text mentions because those records cannot exist without
provenance. Deleting a referenced user is rejected.

## Embeddings

Face creation can include one finite vector per configured embedding model.
Face patching upserts the supplied model vectors, leaves unmentioned vectors
unchanged, and treats an empty embeddings list as a no-op. A vector dimension
must match the configured dimension for its model. Weaviate requires a named
vector slot for every accepted model; PostgreSQL must enforce the same model
and dimension behavior.

PostgreSQL registers face models in `pg_demo_face_models`, keyed by the model
stub, and stores one row per face and model in `pg_demo_face_embeddings`.
Registering a model records its vector dimension and creates a partial cosine
HNSW expression index for that model. The index casts the generic embedding
column to `vector(<dimension>)` and uses `WHERE model_id = <stub>`, so models
with different dimensions can share the table while each search uses a
dimension-specific index.

Face search uses at most eight query representatives and retrieves at most 200
nearest faces per representative through a lateral HNSW query. Searches with
eight or fewer reference faces remain exact. Larger sets use deterministic
spherical k-means centroids; cluster sizes weight average aggregation, while
min/max aggregate over the covered query regions. Candidate generation and
rescoring run in one statement, with result filters applied at both stages, so
database work is bounded independently of the number of reference faces. A
model must be registered through the admin API before its vectors can be
written or searched; registration is idempotent when the stub and dimension
match and rejects changing the dimension of an existing stub.

## Batch behavior

Successful create and patch results preserve input order. Patch commands require
unique object IDs and return None for missing objects. Delete batches
de-duplicate IDs and return the number of stored objects deleted. Empty batches
return an empty result or zero.

Batch operations are not guaranteed to be atomic. If an operation raises,
backends without rollback support may retain earlier successful writes.
Callers must not infer PostgreSQL transaction behavior from this interface.

## Configuration

Exactly one persistence configuration must be non-null. The selected object
requires its connection fields. Omit or set the unused object to null; current
settings do not use `ENABLED` flags. For PostgreSQL, for example:

```dotenv
PEOPLE_GATOR_API__PERSISTENCE={"postgres":{"host":"localhost","port":5432,"user":"test","password":"test","database":"test"},"weaviate":null}
```

To select Weaviate, provide only its complete connection object. PostgreSQL
startup either bootstraps or validates according to `schema_mode`;
`DatabaseDependency` uses the selected adapter for requests. Shutdown releases
initialized resources. Alembic and the preview seed require PostgreSQL. See
[local setup](../../../../docs/DEVELOPMENT.md) for migrated development stores.

Routes use `DatabaseDependency` for either backend. OCR span rendering is handled
by `media/text_mention_spans.py` through the persistence contracts.

## Binding a backend

Backend factories are loaded lazily and return the same facade:

    from people_gator_api.persistence import (
        postgres_database,
        weaviate_database,
    )

    database = weaviate_database(weaviate_client)
    # or
    database = postgres_database(sqlalchemy_session)

    entity = await database.entities.create(payload, actor)
    hits = await database.entities.search(query)

The adapters may be migrated independently, but both must implement the
observable behavior above.

## Weaviate ownership

`persistence/weaviate` owns repository implementations, client construction,
collection schemas, and backend query helpers. `services/database_service.py`
owns process-wide client state, startup retries, shutdown, and request dependencies
for both database backends. There is no separate Weaviate service package.

The public factory remains `people_gator_api.persistence.weaviate.weaviate_database`.
Collection definitions are in `people_gator_api.persistence.weaviate.schema`;
client construction and schema setup are in its `client` module.

The Weaviate package passes the repository's strict Pyright configuration:

```bash
.venv/bin/pyright --pythonpath .venv/bin/python src/people_gator_api/persistence/weaviate
```

All repository methods use their contract parameter names and request/response
types. Client results are validated at the schema boundary; named vector specs
are declarative and built through the public Weaviate configuration API.

Entity links on faces and mentions use the shared `EntityLinkState` enum.
Create defaults an assigned annotation to `automatic`; manual callers explicitly
send `manual`. PATCH distinguishes omission from null and defaults a changed
entity to `manual`. Verification applies only to an existing link, records the
actor's user ID and server UTC time, and is idempotent. Reassignment, unlinking,
and manual merges clear prior verification. PostgreSQL validates transitions
under row locks and enforces the state/verification invariants with CHECKs;
a trigger clears link metadata when an entity FK is set null, including raw SQL
deletes. Link statistics are two batched grouped queries, independent of filters
and pagination. Document filters and statistics share the direct-source plus
registered-pages scope, identified by both library and archive document ID.

The optional Weaviate adapter stores the same link fields, backfills missing
legacy states and aggregation keys additively, and uses grouped server aggregates
for response-page statistics. An annotation replacement writes the current entity,
state, verifier and time together, retaining geometry, provenance and named vectors.
PATCH batches preflight semantic validation before writing, preserve input order,
and return null for missing annotations. Manual merge clears verification only on
transferred links; entity deletion clears annotations before removing the entity.

Weaviate has no relational transactions or cross-process row locks: in-process
annotation locks serialize read/replace transitions, while separate workers use
whole-object last-writer-wins updates. Multi-object operations can be partially
applied by a network failure. PostgreSQL provides transactional batch/merge
behavior and database CHECK/FK protection. The optional live adapter test accepts
`PEOPLE_GATOR_WEAVIATE_TEST_HTTP_PORT` and `PEOPLE_GATOR_WEAVIATE_TEST_GRPC_PORT`
for a disposable local Weaviate instance.
