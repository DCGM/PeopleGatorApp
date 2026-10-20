# Entity processing filters

PostgreSQL entity lists and searches accept the same optional query parameters:

| Parameter | Value |
| --- | --- |
| `filter.last_touched_from` | Inclusive, timezone-aware lower bound |
| `filter.last_touched_to` | Inclusive, timezone-aware upper bound |
| `filter.document_source_id` | Repeated internal document source UUIDs |
| `filter.last_touched_by_user_id` | Repeated last-actor user UUIDs |
| `filter.last_touched_by_api_key_id` | Repeated registered API-key UUIDs |

Combine different fields with AND and repeated IDs within a field with OR.
Existing assignment filters and `query.text` compose with these fields. Invalid
or timezone-less timestamps and inverted ranges return 422. Times normalize to
UTC; historical unknown metadata remains null and is included without a matching
touch filter. Counts and cursors include all active filters.

A document matches assigned faces or text mentions on any page identified by the
same `(library, document_id)`. Pass the document's internal `source_id`, rather
than its archive `document_id`. Repeated occurrences do not duplicate identities.

Entity responses expose `last_touched_at`, `last_touched_by_user_id` and nullable
`last_touched_by_api_key_id`. `user_id` remains the original owner. Entity creation,
actual field/alias changes, evidence creation/reassignment/removal, source cascade
deletions and merges update touch in the same transaction. Reassignment touches
both identities; merge touches the result. Reads, identical assignments, empty
patches and alias reordering preserve touch. JWT changes clear prior API-key
attribution. Batch and automated HTTP requests use the same repository paths.

Direct repository callers must provide their `GenericActor` (or `AuthContext`)
for mutations; merge and evidence/source delete methods require `context=`.
The transactional implementation and migrations target PostgreSQL. The legacy
Weaviate adapter already lacks atomic merge support and is not a transactional
alternative for this feature.

The people search screen stores filters in `touched_from`, `touched_to`, repeated
`document`, `touched_by` and `api_key` URL parameters. URL timestamps are UTC; the
controls use the browser's local timezone. Filter changes select a new query
cache entry and start from its first page. Individual chips and Clear all filters
remove filters while preserving the text query.

Person details include an expanded Last processed row in the statistics sidebar.
It shows the timestamp in the browser's local timezone (including seconds
and timezone), the last user's display name,
and the API-key name/identifier when present. Hovering the timestamp shows its
original UTC value; actor labels expose their IDs on hover and fall back to IDs
when lookup data is unavailable. Historical records show No processing recorded.
Saving a changed profile field updates the information immediately; its refresh
button reloads metadata after external processing without changing the record itself.

To regenerate the TypeScript client from a local schema, use the application's
normal environment/settings and run from `people-gator-api`:

```sh
uv run python scripts/export_openapi.py /tmp/people-gator-openapi.json
```

Then run from `people-gator-app`:

```sh
npm run openapi-ts -- --input /tmp/people-gator-openapi.json
```

## Annotation criteria versus resource processing (#31)

All entity, source projection, face and text-mention list/search filters now
share these evidence criteria (prefix with `filter.` over HTTP):

| Field | Meaning |
| --- | --- |
| `entity_link_state` | OR of Automatic, Manual, Verified assignment states |
| `evidence_library` | Library of the annotation's direct document/page source |
| `document_source_id` | Internal registered document source UUID, including its direct evidence and pages in the same library/document |
| `evidence_source_id` | Exact annotation source UUIDs |
| `evidence_touched_from`, `evidence_touched_to` | Inclusive, timezone-aware annotation-change bounds, normalized to UTC |
| `evidence_touched_by_user_id`, `evidence_touched_by_api_key_id` | Last annotation editor / registered key, independent of owner and verifier |

Different fields combine with AND; repeated values with OR. The same annotation
must satisfy every evidence criterion. Documents match containing annotations;
entities match assigned annotations; face/mention collections return those
annotations. Filtering and counts precede pagination; cursors include all criteria.
An explicit assigned-faces/mentions choice requires a matching annotation of that
kind. Null historical times cannot satisfy edit bounds/actors. Empty selections
are omitted; malformed/inverted/naive time bounds return 422.

Unprefixed `last_touched_*` still describes the selected **resource** (person or
source processing). It never becomes an annotation bound when navigating.
New records capture server creation/ingestion time and actor separately from
annotation edits; detector execution time is not inferred. Historical creation
and change metadata remain null when not recorded. Material annotation changes,
including merges/unassignments/embedding edits, update annotation time and actor.
Identical writes and reads do not. JWT changes clear previous API-key attribution.
Creation/import attribution stays unchanged when an annotation is reviewed.
