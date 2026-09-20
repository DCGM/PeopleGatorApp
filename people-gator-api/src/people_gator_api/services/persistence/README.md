# Persistence interface

This package is the backend-neutral boundary for API persistence. Routes and
higher-level services should depend on `Database`, not on a Weaviate client or
SQLAlchemy session.

`Database` exposes one repository per public aggregate:

- `entities`
- `sources` (`Page`, `Document`, and `Image` are typed source projections)
- `faces` (`Face` owns its image-occurrence data and embeddings)
- `text_mentions`
- `users`

Aliases and embeddings are children of their owning aggregate and are updated
through that repository.

Entity and face creation accept an `embeddings` list. Entity items identify the
semantic `field`, while every item identifies its producing model:

```python
EntityCreateRequest(
    name="Ada Lovelace",
    embeddings=[
        EntityEmbeddingInput(
            field="name",
            model_identifier="text/model-a",
            vector=[0.1, 0.2],
        ),
        EntityEmbeddingInput(
            field="description",
            model_identifier="text/model-b",
            vector=[0.3, 0.4],
        ),
    ],
)
```

`update_embeddings_batch` accepts several object commands, and each command can
upsert several embeddings. Its return value counts vectors written, not objects.
Duplicate entity `(field, model_identifier)` slots and duplicate face model slots
are rejected. PostgreSQL accepts new model identifiers dynamically. Weaviate
requires the corresponding named-vector slot to exist in its collection schema.

## Batch semantics

Batch methods are abstract, mandatory backend operations. They never inherit a
per-item loop from the contract.

- PostgreSQL imports and heterogeneous patches use one transaction; SQLAlchemy
  groups dirty rows into executemany statements. Deletes use one set-based
  `DELETE ... WHERE id IN (...)` statement.
- Weaviate imports use its batch APIs and deletes use one `delete_many` call.
  The Weaviate client has no property-update batch primitive, so heterogeneous
  patch batches perform one bulk prefetch followed by bounded concurrent update
  calls. This limitation is visible in the adapter rather than hidden behind a
  misleading sequential default.

Batch patch commands require unique object IDs. Results preserve command order
and contain `None` where a requested object did not exist.

## Binding a backend

Both factories return the same `Database` facade:

```python
database = weaviate_database(weaviate_client)
# or
database = postgres_database(sqlalchemy_session)

entity = await database.entities.insert(payload, WriteContext(user_id))
hits = await database.entities.search(query)
```

The existing routes have not yet been switched to this facade. That migration
can be performed one aggregate at a time without changing the contract.
