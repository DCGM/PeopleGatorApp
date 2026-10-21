# Synthetic HTTP reproduction of the numerical failure

The reported private dataset was unavailable. This read-only experiment used the
maintained synthetic preview, with the search route handlers and shared scoring
functions loaded from reviewed `main` (`eb133fd`) inside a separate diagnostic
process. Repository calls used explicit face inputs, so the new entity resolver
was not involved. No checkout or stored records were reverted.

For each endpoint, the request was:

```text
GET /api/v1/search-entities?query.face_id=<discovery-reference-0 UUID>&query.face_embedding_model=preview-discovery-8d-v1
GET /api/v1/search-faces?query.face_id=<discovery-reference-0 UUID>&query.face_embedding_model=preview-discovery-8d-v1
```

The reference has a usable vector. Candidate entities/faces include the fixture's
zero vectors; Orion Portrait also has a usable matching face. PostgreSQL returns
`NaN` for cosine distance involving a zero vector. Its `max()` aggregate prefers
`NaN` over finite numbers, so the entity score becomes undefined even with another
useful face. Zero vectors can also enter the face result pool with the small
synthetic store's candidate plan. Both actual HTTP responses were **422**:

```text
invalid_search: 1 validation error for FoundEntity
face_score: Input should be a finite number
[type=finite_number, input_value=nan, input_type=float]

invalid_search: 1 validation error for FoundFace
face_score: Input should be a finite number
[type=finite_number, input_value=nan, input_type=float]
```

With the fixed scoring/routes, the same two requests returned **200**, with four
entity results and fifteen face results, all with finite scores. The fix excludes
undefined distances before candidate ranking and aggregation; it retains strict
finite-score response validation and does not invent replacement scores. Explicit
zero/missing-model references remain 422 errors, whereas entity-derived unusable
faces are skipped when other selected signals are usable.

This establishes both synthetic numerical failure paths. It does not establish
that zero vectors caused the original reporter's dataset-specific failure.
