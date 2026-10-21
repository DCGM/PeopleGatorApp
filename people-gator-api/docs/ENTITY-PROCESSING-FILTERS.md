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

## Unified source and latest-modification criteria (#52)

Documents, pages, entities, faces and mentions share `library`,
`document_source_id`, `page_source_id`, `entity_link_state` and `last_touched_*`.
The latest-modification criteria always describe the records returned by that
collection. A user's document selection transfers to People as an entity's own
latest modifier; it does not mean an entity with a face/mention edited by that
user. Faces and mentions apply these same fields to their own metadata. Creation,
ownership, verification and historical edits remain independent.

Scope follows real source relationships. A registered document includes its
pages in the same library/archive document; a page scope returns its registered
parent in Documents, that page in Scans, and linked annotations/entities on that
page elsewhere. Source-only browsing includes unannotated documents/pages.
Repeated values OR and different fields AND. Linked criteria must match the same
annotation. Counts and filters precede pagination. Unknown history never matches
a time or actor criterion. No migration invents historical attribution.

The former `filter.evidence_*` HTTP parameters now fail with 422 and a replacement
name. They must not silently change meaning. The browser migrates same-meaning
scope names, removes obsolete origin context and shows a notice when it drops
annotation-edit criteria on a resource list. See the complete
[filter reference and URL compatibility policy](../../docs/SEARCH_FILTERS.md).

Material annotation changes, including merges, unassignments and embedding edits,
update annotation time/actor. Identical writes and reads do not. JWT changes clear
previous API-key attribution; creation/import attribution remains unchanged.
