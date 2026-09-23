# Persistence interface

This package is the backend-neutral persistence boundary. Routes and services
depend on the Database facade; repositories do not expose Weaviate clients,
SQLAlchemy sessions, backend filters, or transaction objects.

Database exposes repositories for entities, sources, faces, text mentions, and
users. Page, document, and image APIs are typed projections of the source
repository.

## Shared behavior

Ordinary list operations order records by UUID ascending. Search operations
order by final score descending and UUID ascending. Cursors are exclusive and
may only be reused with the same query and filter. total_count, when requested,
counts all filter matches before cursor and limit.

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

## Batch behavior

Successful create and patch results preserve input order. Patch commands require
unique object IDs and return None for missing objects. Delete batches
de-duplicate IDs and return the number of stored objects deleted. Empty batches
return an empty result or zero.

Batch operations are not guaranteed to be atomic. If an operation raises,
backends without rollback support may retain earlier successful writes.
Callers must not infer PostgreSQL transaction behavior from this interface.

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
