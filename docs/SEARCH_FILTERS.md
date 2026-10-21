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
| `query.face_id` | Repeated unique existing reference-face UUIDs with usable cosine embeddings |
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
For `/search-faces` and `/search-entities` only, `query.entity_id=<UUID>`
resolves reference inputs on the server. Repeat `query.entity_annotations=faces`,
`aliases`, or `name` to select any combination; omission equals all three. Faces
use every linked, compatible finite nonzero vector for the selected model,
independently of frontend pagination and result filters. Aliases and name use the
recorded reference text. Alias selection does not restrict candidate matching to
candidate aliases. Explicit text/face inputs supplement selected entity inputs;
duplicated derived signals are counted once. `filter.entity_id` still restricts
results and never supplies reference inputs.

```text
/api/v1/search-faces?query.entity_id=<UUID>&query.entity_annotations=faces
/api/v1/search-entities?query.entity_id=<UUID>&query.entity_annotations=aliases&query.entity_annotations=name
```

Unknown entities and selections with no usable combined signal return **422
`invalid_search`**. Unsupported annotation values return 422 validation errors;
annotations without an entity are invalid. Individual derived faces with missing,
other-model or zero embeddings are skipped. Explicit face IDs remain strict:
missing IDs, missing model embeddings and zero/unusable cosine embeddings return
422 even alongside usable inputs. Undefined candidate cosine distances are
excluded before aggregation; a text match may still return that candidate with
`face_score=null`. Scores retain finite validation; internal result validation
failures are server errors, not malformed-query errors. No scores are fabricated.

With default reference exclusion, entity search excludes the reference entity;
face search excludes all of its linked faces, also for name/alias-only searches.
`query.exclude_reference_face_id=false` includes them. Explicit queries retain
their existing face-ID exclusion behavior. Scoring, sorting, RRF fusion and
bounded HNSW retrieval (at most eight representatives, 200 candidates each) are
unchanged. Cursors bind the original entity and canonical annotation selection;
changing either rejects reuse. Equivalent omitted/all or reordered selections
share the same fingerprint. Stored-input edits can change subsequent rankings.
Entity references require PostgreSQL; Weaviate returns 501 unsupported_operation
instead of silently ignoring them. Other explicit Weaviate behavior is unchanged.

Discover uses this compact contract for both result lists. **Reference inputs**
selects sources; **Face model** chooses a registered embedding model (listing
models requires browse scope; registration remains admin-only). Optional search
text adds another signal. Choices are shareable through `discovery_annotations`,
`discovery_model` and `discovery_text`; changes restart pagination. Selected source
tags remain available with mobile controls collapsed. Empty/error states allow
changing inputs and retrying without resetting evidence filters or assignments.

Reference vectors are already stored; this search does not require an inference
service. Large reference sets use bounded representative/candidate retrieval as
documented in the [persistence guide](../people-gator-api/src/people_gator_api/persistence/README.md).

Without `sort`, ordinary lists sort UUID ascending. See [Sorting](#sorting).
Responses contain `items`, `limit`, `cursor` and nullable `total_count`. Reuse a
cursor only with the same inputs; changing a query, filter or sort restarts
pagination. Lists default to 50 items, searches to 20.
`limit=0` returns no items/cursor and can request a count.

## Sorting

Every browsable list accepts `sort` (a resource-allowlisted field, never a
column name) and `sort_direction` (`asc`/`desc`, requires `sort`). Unknown fields
or directions, Relevance on an ordinary list and `sort_direction` alone return
422. A field without a direction uses its natural one: descending for
relevance, times and counts, otherwise ascending. The order applies to the
complete matching set **before** pagination and `total_count` is unaffected.

Semantics shared by every resource:

- Text compares lowercased, unaccented text in Unicode code-point order, then the
  exact recorded text, so `Ada`/`ADA`/`Áda` sort together but stay distinct.
- Counts compare numerically, times chronologically and IDs by UUID value.
- Assignment state orders `verified`, `manual`, `automatic`, then unassigned.
- Unknown values (no name, no edit time, no source context, unassigned) sort
  last in **both** directions.
- The canonical UUID ascending is the final tie-breaker; an ID sort may be
  descending and is its own tie-breaker.
- PostgreSQL list cursors carry every key value and are bound to the query,
  filters, field and direction. Rows whose sortable value changes between pages
  can move across the boundary; no snapshot is promised.
- Searches sort their **complete ranked candidate set** before paging. Face
  similarity is bounded (200 HNSW neighbours per representative reference face,
  at most 8 representatives); people/document/page text retrieval keeps about
  200 candidates per term and signal. A non-relevance sort orders that whole
  set; it is not an exhaustive corpus-wide similarity scan. Discover shows the
  first 40 results of the sorted set.
- Weaviate keeps only the default orders. It accepts an explicit request for
  identity ascending (lists) or relevance descending (searches) and rejects
  other sorts (501). It also rejects exact text-mention `filter.name` (501).

| Collection (endpoint) | Fields | API default | UI default |
| --- | --- | --- | --- |
| People browse/search, Discover people, scan candidates (`/entities`, `/search-entities`) | `relevance` (search), `name`, `last_touched_at`, `created_at`, `entity_id` | UUID / relevance | Name A–Z; Relevance while a query or face signal exists |
| Documents (`/documents`, `/search-documents`) | `relevance` (search), `name`, `library` (then archive ID), `document_id`, `page_count` (registered pages with the same library/archive ID), `last_touched_at` (document processing) | UUID / relevance | Name A–Z (unnamed last); Relevance while searching |
| Scans (`/pages`, `/search-pages`) | `relevance` (search), `library` (then document, page ID), `document_id` (then page ID), `page_id`, `last_touched_at` | UUID / relevance | Library A–Z; Relevance while searching |
| Document page gallery and document previews (`/pages`) | `page_id`, `last_touched_at` | UUID | Page ID ascending. No physical page sequence is recorded; page IDs are never shown as page numbers |
| Person faces, scan page faces, Discover similar faces (`/faces`, `/search-faces`) | `relevance` (similarity, search), `last_touched_at`, `link_state`, `confidence`, `source` (library, document, page), `detection_id` | UUID / relevance | Face ID; Similarity in Discover. Scan page faces omit Source |
| Person mentions, group occurrences (`/text-mentions`) | `text`, `last_touched_at`, `link_state`, `source`, `mention_id` | UUID | Text A–Z |
| Exact appearance groups (`/text-mention-groups`) | `text`, `count`, `last_touched_at` (latest edit in the group) | Text A–Z | Text A–Z; groups and occurrences sort independently |
| Scan Activity (client grouping of the page's complete collection) | Day groups newest/oldest, user groups by label A–Z/Z–A; edits newest/oldest | — | Newest day / user A–Z; newest edit. Unknown day/user groups and unknown times stay last |

Fixed-order exceptions: filter option lists (users, API keys, libraries,
documents) keep their predictable label order; static navigation, statistics
and batch-mutation responses are not browsable result lists.

`GET /text-mention-groups` takes the mention filters and returns `name`,
`occurrence_count` and `last_touched_at` for every exact recorded text in the
complete filtered set, never normalizing spelling, case, accents or punctuation.
`filter.name` on `/text-mentions` selects one group's occurrences.

Each panel has one standard **Sort** select whose options are complete
strategies: every field in both directions, natural direction first (for
example *Name · A–Z*, *Name · Z–A*, *Last change · Newest first*). Activity's
select combines its two keys, group order and edit order, into four strategies
(for example *Days newest first · Edits oldest first*).

Browser URLs keep one independent choice per panel, omitting defaults:

| Panel | URL keys |
| --- | --- |
| People, Documents, Scans | `sort`, `dir` |
| Person faces / scan page faces | `face_sort`, `face_dir` |
| Person mentions and group occurrences | `mention_sort`, `mention_dir`; `mention_view=groups` |
| Exact appearance groups | `group_sort`, `group_dir` |
| Discover similar faces / people | `similar_sort`, `similar_dir` / `people_sort`, `people_dir` |
| Scan gallery / candidates | `gallery_sort`, `gallery_dir` / `candidate_sort`, `candidate_dir` |
| Activity | `activity_order`, `activity_items` |

Sort values are part of each query key, so a new order starts at the first page.
Invalid or inapplicable values recover to the panel default with truthful
controls; an explicit choice that remains applicable survives switching between
browse and search. Filter tag removal and **Clear all filters** keep search and
sort. Related navigation to another resource carries no sort or cursor; links to
another page of the same document keep the workspace's face, gallery and
candidate orders. Profile witnesses from an originating face search are pinned
first and labelled **Match**; the remaining faces follow the selected order.

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
without an additional filter panel above the scan. Its sidebar Activity tab
lists the current page’s faces and mentions by local edit day or last user.
Selecting a group applies inclusive annotation-day bounds or an annotation-user
criterion; groups retain the complete source collection so selections can be
broadened. Unknown historical metadata remains explicit and is not a time/user
filter. Other shared criteria remain editable in a related list/profile. The existing compact scan toolbar
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
| `evidence_library` | `filter.evidence_library` |
| `evidence_document` | `filter.document_source_id`: internal registered document source UUID |
| `evidence_source` | `filter.evidence_source_id`: exact source UUID |
| `evidence_from`, `evidence_to` | `filter.evidence_touched_from/to`: annotation edit time, timezone required |
| `evidence_user`, `evidence_key` | `filter.evidence_touched_by_user_id/api_key_id`: annotation's last actor |
| People `document` | Legacy internal document selection; mapped to active shared evidence on navigation |
| Scan `library`, `document` | Resource library/archive UUID; opening a scan does not add an annotation-source filter |
| `touched_from/to`, `touched_by`, `api_key` | Current person/source processing, **never** annotation edits |
| `origin_person_*`, `origin_source_*` | Resource-specific processing context; never applied as annotation edits |
| `origin_text` | Name/alias/source search signal; never literal text filtering of face images |
| `origin_matched_face`, `origin_reference_face` | Actual matching detection / reference face signals |
| Legacy `origin_return` | Ignored by breadcrumbs and omitted from related navigation |
| `tab` | Faces (default), mentions or discover; incoming assigned-mentions searches open Mentions |
| `discovery_assignment`, `discovery_text`, `candidate_mode`, `candidate_text` | View-specific discovery/candidate choices, retained as origin context on related navigation |

Related links copy the current shared selections and keep resource-specific
criteria separate. Source metadata is not rendered as removable origin tags.
Opening a document's scan list uses library/archive scope and shows all
registered pages by default, including pages without faces or mentions. Document
heading, +more and page links copy only the selected annotation criteria;
ordinary document browsing does not add an evidence-presence restriction.
Opening a scan preserves explicitly selected evidence filters without adding
`evidence_source` for the opened page. The workspace already constrains its
annotations to that page; database assignment searches can still find people
whose evidence is elsewhere. Explicit evidence-source selections remain effective.
Profiles use the normal **PeopleGator → People → person ID** breadcrumb. The
People link forwards the profile's current shared filters, including edits and
removals. It does not restore a saved source URL or old filter selections.
Shared criteria populate the actual filter controls and their removable
active-filter tags. Changes carry forward on the next related link.
Each view is reproducible from its URL, including copied links and browser
Back/Forward. Destination queries start at their own first page; source cursors
never travel across resources. Removing a filter tag changes controls, URL and
server results. A single Clear all filters action per panel and profile broadening preserve unrelated
search context; clearing text remains a separate action. Invalid copied
annotation bounds/UUIDs show recoverable criteria and block evidence
requests until corrected/removed. Missing matched detections and unavailable
source pages are reported without blocking identity details. Missing option
labels fall back to identifiers without exposing credentials.

Face-similarity entity results include `matched_detection_ids`; profile links
retain these actual witnesses. They are loaded within the fixed person and
current evidence scope, independently of the first evidence page. Person face
cards use compact assignment/confidence, library/document and last-change/editor
rows. Identity creation/import time and actor remain separately labeled in the
profile statistics; owner, verifier and last editor are independent.

PostgreSQL implements the persisted annotation metadata and shared filters. The
optional Weaviate adapter explicitly rejects unsupported annotation edit filters.

The scan pane has top-level Faces, Activity and Statistics tabs. Activity and
Statistics replace the entire pane content and scroll within its remaining height;
face selection and candidate settings survive tab switches. Statistics presents
page/document totals with explicit state labels and has no disclosure. The legacy
`#link-statistics` URL opens Statistics too.

Page sidebar URLs use `panel=activity` or `panel=statistics` (default `face`) and
`activity_group=user` (default local day). Day boundaries use consecutive local
midnights, including daylight-saving changes; the upper bound is inclusive at
23:59:59.999999 local time, preserving database microsecond precision. Group entries show their own recorded annotation edit
time, rather than the page/document processing timestamp. Activity time/user
chips can be removed independently and clearing them retains other criteria.
