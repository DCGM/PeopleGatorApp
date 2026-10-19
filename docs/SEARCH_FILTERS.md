# Search and configurable filters

The API exposes GET `/api/v1/search-entities`, `/search-faces`, `/search-pages`
and `/search-documents`. Ordinary resource lists use the same resource filter
schemas without requiring a search modality. Filter configuration is typed in
`schemas/` and exposed by `routes/v1/query_dependencies.py`; there is no separate
runtime filter-definition file or saved search-profile service.

## Queries, ranking and pagination

| Parameter | Meaning |
| --- | --- |
| `query.text` | Repeated unique nonblank text queries |
| `query.face_id` | Repeated unique existing reference-face UUIDs |
| `query.face_embedding_model` | Registered model stub; every reference needs a vector for it |
| `query.exclude_reference_face_id` | Exclude the reference faces; defaults to true |
| `query.score_aggregation` | `min` (default), `max` or `average` across query items within a modality |
| `query.score_fusion` | `rrf`, the supported rank-fusion mode |
| `limit`, `cursor`, `return_total_count` | Page size, opaque continuation token and optional full-match count |

At least one nonempty modality is required. Text relevance and cosine similarity
use higher-is-better semantics. Modalities rank independently after aggregation;
RRF sums `1 / (60 + rank)` using one-based ranks and equal modality weights.
Final order is score descending, then object UUID ascending. Raw text scores
are backend-specific; final scores are rank signals, not identity probabilities.
Reference vectors are already stored; this search does not require an inference
service. Large reference sets use bounded representative/candidate retrieval as
documented in the [persistence guide](../people-gator-api/src/people_gator_api/persistence/README.md).

Ordinary lists sort UUID ascending. Responses contain `items`, `limit`, `cursor`
and nullable `total_count`. Reuse a cursor only with the same inputs; changing a
query or filter restarts pagination. Lists default to 50 items, searches to 20.
`limit=0` returns no items/cursor and can request a count.

## Filter reference

Prefix each field with `filter.` in HTTP requests. Different fields combine with
AND, repeated values within one field with OR. Omit inactive list fields instead
of sending empty lists. Unknown IDs do not mean unassigned annotations.

| Resource | Supported filter groups |
| --- | --- |
| Entities | `entity_id`, `entity_type`, `wikidata_id`, `nlcr_authority_id`; related `source_id`, `detection_id`, `mention_id`; `has_mentions`, `has_detections`; `document_source_id`; processing fields and link state |
| Faces | `entity_id`, `source_id`, `detection_id`, `entity_link_state` |
| Text mentions | `entity_id`, `source_id`, `entity_link_state` |
| Documents | `url`, `library`, archive `document_id`, internal `source_id`; `entity_id`, `detection_id`, `mention_id`; `has_unassigned_faces`; processing fields and link state |
| Pages | `url`, `library`, `document_id`, `page_id`, `source_id`; `entity_id`, `detection_id`, `mention_id`; `has_mentions`, `has_faces`, `has_entities`; processing fields and link state |
| Images | `url`, `source_id`, `entity_id`, `detection_id`, `mention_id`; processing fields and link state |

`entity_link_state` accepts repeated `automatic`, `manual`, `verified` values.
It matches the same annotation as the other evidence criteria, avoiding a match
assembled from unrelated faces/mentions. Omit it to include unassigned evidence.
Document evidence covers its direct source plus registered pages with the same
library and archive document UUID. Link statistics describe the full evidence
scope, independently of pagination/current result filters.

`has_unassigned_faces=true` finds documents with an unassigned face;
`false` excludes documents with unassigned faces and includes documents without
faces. Text-mention assignment does not satisfy this face-specific condition.

Entities and source projections accept inclusive `last_touched_from` and
`last_touched_to`, plus repeated `last_touched_by_user_id` and
`last_touched_by_api_key_id`. Timestamps must include a timezone; invalid or
inverted ranges return 422. Historical null touch metadata is retained, but does
not satisfy a touch criterion. Entity `document_source_id` takes the registered
document's **internal source UUID**, not its archive `document_id`. See
[processing filters](../people-gator-api/docs/ENTITY-PROCESSING-FILTERS.md).

With `$TOKEN` supplied securely, a text/assignment search looks like:

```sh
curl --fail --get http://127.0.0.1:8000/api/v1/search-entities \
  -H "Authorization: Bearer $TOKEN" \
  --data-urlencode 'query.text=Ada' \
  --data-urlencode 'filter.entity_type=person' \
  --data-urlencode 'filter.entity_link_state=manual' \
  --data-urlencode 'filter.entity_link_state=verified' \
  --data-urlencode 'return_total_count=true'
```

Use the token-in-memory [smoke example](START_HERE.md#check-the-api-without-printing-credentials)
for a credential-safe first request. For document search, text can match document
names, archive identifiers or evidence-linked entity names/aliases; ordinary
`/documents` lists do not accept `query.text`.

## Browser state and extending filters

People filters use URL keys `touched_from`, `touched_to`, `document`, `touched_by`
and `api_key`; document filters also use `library`, `link_state` and `unassigned`.
These screen URLs differ from the namespaced API parameters. Times are stored as
UTC and rendered in browser local time. Viewmodels map URL state to API criteria;
query keys include active filters. Individual chips and Clear all filters retain
the search text. On small screens the sliders button expands collapsed filters.

To add a filter, update the schema and typed HTTP dependency, repository query
and count/cursor behavior, export/regenerate the SDK, then update query keys,
viewmodel URL parsing and controls together. Test AND/OR combinations, empty or
invalid inputs, evidence scope and cursor reset. Follow the shared layout rules
in [AGENTS.md](../AGENTS.md) and extend the preview fixtures. A UI control must
represent a working server criterion.

## Shared evidence navigation (#31)

Documents, scan search, people search and person details expose one shared set
of annotation criteria. Page workspaces apply and forward those URL criteria
without an additional filter panel or tags, preserving space for the scan; edit
shared criteria in a related list/profile. The existing compact scan toolbar
continues to control annotation link state. Their names, OR selections, inclusive time
bounds and AND combination match the API fields documented in
[annotation processing](../people-gator-api/docs/ENTITY-PROCESSING-FILTERS.md#annotation-criteria-versus-resource-processing-31).
Documents/people return resources containing matching evidence. Profiles return
that person's matching faces/mentions with filtered counts alongside overall
statistics. Every condition must match the same annotation, including document,
state and actor; results cannot combine unrelated annotations.

| Browser URL | API criterion / scope |
| --- | --- |
| `link_state` | `filter.entity_link_state` |
| `evidence_origin` | `filter.evidence_origin`: automatic/manual/authority/unknown, independent of link state |
| `evidence_library` | `filter.evidence_library` |
| `evidence_document` | `filter.document_source_id`: internal registered document source UUID |
| `evidence_source` | `filter.evidence_source_id`: exact source UUID |
| `evidence_from`, `evidence_to` | `filter.evidence_touched_from/to`: annotation edit time, timezone required |
| `evidence_user`, `evidence_key` | `filter.evidence_touched_by_user_id/api_key_id`: annotation's last actor |
| People `document` | Legacy internal document selection; mapped to active shared evidence on navigation |
| Scan `library`, `document` | Resource library/archive UUID; opening a scan also retains its exact source |
| `touched_from/to`, `touched_by`, `api_key` | Current person/source processing, **never** annotation edits |
| `origin_person_*`, `origin_source_*` | Visible originating resource criteria retained with their original meaning |
| `origin_text` | Name/alias/source search signal; never literal text filtering of face images |
| `origin_matched_face`, `origin_reference_face` | Actual matching detection / reference face signals |
| `origin_return` | Internal cursor-free originating URL; Return restores the original search |
| `tab` | Faces (default), mentions or discover; incoming assigned-mentions searches open Mentions |
| `discovery_assignment`, `discovery_text`, `candidate_mode`, `candidate_text` | View-specific discovery/candidate choices, retained as origin context on related navigation |

Related links copy the current shared selections and scope resource-specific
criteria as origin context. Changes carry forward on the next related link.
Each view is reproducible from its URL, including copied links and browser
Back/Forward. Destination queries start at their own first page; source cursors
never travel across resources. Removing a filter tag changes controls, URL and
server results. A single Clear all filters action per panel and profile broadening preserve origin
text and the return URL; clearing text remains a separate action. Invalid copied
annotation bounds/origins/UUIDs show recoverable criteria and block evidence
requests until corrected/removed. Missing matched detections and unavailable
source pages are reported without blocking identity details. Missing option
labels fall back to identifiers without exposing credentials.

Face-similarity entity results include `matched_detection_ids`; profile links
retain these actual witnesses. They are loaded within the fixed person and
current evidence scope, independently of the first evidence page. Verification
metadata and actions remain available. Provenance details identify detection
confidence separately from similarity and show recorded creation and annotation
edit attribution; owner, verifier and last editor are independent.

PostgreSQL implements these persisted metadata and shared filters. The optional
Weaviate adapter explicitly rejects the new provenance/edit filter groups and
recorded provenance ingestion; it must not silently return unfiltered results.
No authority crawler or historical audit log is introduced. Synthetic authority
references use `preview.invalid`; no external authority data is fetched.
