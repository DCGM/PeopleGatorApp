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
unchanged. Face text retrieval uses three separate trigram GIN predicates on
identifier, normalized entity name and normalized alias. Each branch applies
face/evidence filters before taking at most 200 candidates per term, with UUID
tie-breaking, then only those candidates enter the existing similarity scoring
and aggregation. PostgreSQL's `pg_trgm.similarity_threshold` (default 0.3)
gates text candidates; weak incidental overlaps no longer expand the face pool.
The identifier index is added by migration `d34a021b0012`. Cursors bind the original entity and canonical annotation selection;
changing either rejects reuse. Equivalent omitted/all or reordered selections
share the same fingerprint. Stored-input edits can change subsequent rankings.
Entity references require PostgreSQL; Weaviate returns 501 unsupported_operation
instead of silently ignoring them. Other explicit Weaviate behavior is unchanged.

Discover uses this compact contract for both result lists. **Reference inputs**
selects sources; **Face model** chooses a registered embedding model (listing
models requires browse scope; registration remains admin-only). Optional search
text adds another signal. Choices are shareable through `discovery_annotations`,
`discovery_model` and `discovery_text`; changes restart pagination. Selected source
tags remain available with mobile controls collapsed. Nondefault Face model
choices have a removable tag; Clear filters resets reference inputs and the
model override together while preserving search text and evidence settings.
Assignment and merge failures retain selections and direct recovery through
their corresponding action; Retry only repeats searches and model loading. Empty/error states allow
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
first and labelled **Search hit**; the remaining faces follow the selected order.

## Filter reference

Prefix each field with `filter.` in HTTP requests. Different fields combine with
AND, repeated values within one field with OR. Omit inactive list fields instead
of sending empty lists. Unknown IDs do not mean unassigned annotations.

Every document, page/scan, entity, face and text-mention list/search uses the
same shared criteria. The API applies modification fields to the **returned
record's own latest recorded change**, never to its owner, creator/importer,
verifier, an earlier editor or a linked annotation.

| Shared API field | Meaning |
| --- | --- |
| `library` | Actual source library; on entities, a linked annotation in that library |
| `document_source_id` | Internal registered document source UUID, including its direct annotations and registered pages in the same library/archive document |
| `page_source_id` | Internal registered page source UUID; source lists return only selected pages, never their parent documents. Other collections match records linked on those pages. Non-page UUIDs do not match |
| `entity_link_state` | OR of `automatic`, `manual`, `verified` assignment states; omit to include unassigned annotations |
| `last_touched_by_user_id` | Users responsible for the record's latest recorded change |
| `last_touched_by_api_key_id` | Registered API keys used for that latest change |
| `last_touched_from`, `last_touched_to` | Inclusive, timezone-aware modification bounds, normalized to UTC |

Library/document/page scope on sources does not require annotations: unannotated
sources remain browsable. Page scope does not expand to containing documents:
Documents returns no matches while a page selection is active. Library and archive
IDs are paired, so an archive UUID reused in another library cannot leak results.
On entities, scope and link state
must match one assigned face or mention. On documents, an explicit link criterion
must match an annotation within the selected document scope. Predicates
cannot combine unrelated links to manufacture a match. Faces and mentions apply
both scope and modification directly to themselves. Unknown history stays null
and cannot satisfy a modification criterion. Empty selections, invalid/timezone-less
bounds and reversed ranges return 422. Filtering and full counts precede pagination;
cursors include the criteria and must be discarded when they change.

| Resource | Additional applicable criteria |
| --- | --- |
| Entities | `entity_id`, `entity_type`, `wikidata_id`, `nlcr_authority_id`, related `source_id`, `detection_id`, `mention_id`, `has_mentions`, `has_detections` |
| Faces | `entity_id`, exact `source_id`, `detection_id`; face-similarity search remains a separate modality |
| Text mentions | `entity_id`, exact `source_id`, exact recorded `name` |
| Documents | `url`, archive `document_id`, exact internal `source_id`, linked `entity_id`, `detection_id`, `mention_id`, `has_unassigned_faces` |
| Pages | `url`, archive `document_id`, archive `page_id`, exact `source_id`, linked `entity_id`, `detection_id`, `mention_id`, `has_mentions`, `has_faces`, `has_entities` |
| Images | `url`, exact `source_id`, linked `entity_id`, `detection_id`, `mention_id` |

`has_unassigned_faces=false` includes documents without faces; text-mention
assignment never satisfies this face-specific condition. Link statistics describe
the full record scope independently of pagination and current filters. See
[modification metadata](../people-gator-api/docs/ENTITY-PROCESSING-FILTERS.md).

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

## One configuration across views (#52)

All panels use `SharedFilterControls`, `SharedFilterTags` and `shared-filters.ts`.
There are no separate evidence-library/document or annotation actor/date facets.

| Browser URL | Shared API field |
| --- | --- |
| `library` | `filter.library` |
| `document` | `filter.document_source_id` (internal registered UUID) |
| `page` | `filter.page_source_id` (internal page UUID; never a pagination number) |
| `link_state` | `filter.entity_link_state` |
| `touched_by`, `api_key` | `filter.last_touched_by_user_id`, `filter.last_touched_by_api_key_id` |
| `touched_from`, `touched_to` | `filter.last_touched_from`, `filter.last_touched_to` |

Times are UTC in URLs and browser-local in controls. Different fields AND;
multi-select values OR. Shared controls, tags and outgoing predicates stay active
through Documents ↔ People, profile tabs, scan lists, related cards, breadcrumbs
and the logo. Page workspaces retain them for return navigation. In Documents, **Modified by U** filters documents; in
People it filters entities; on profile Faces/Mentions it filters each annotation's own change.
Scan page panels ignore these predicates. A profile identity remains visible even when
none of its annotations match. Discover searches similar faces and people across all data accessible to the
current user. It does not inherit source, modifier, date or assignment predicates
from shared browsing filters. Those filters remain in the URL and still apply
when returning to Faces/Mentions or navigating to related views. Reference inputs,
face model, discovery text and each result list’s sort remain explicit discovery
choices; only changes to those effective criteria change the discovery cache key
and restart pagination. Invalid shared filters do not block global discovery.

Individual tag removal updates controls, URL and results immediately. Clear all
removes shared and the screen's specific filters while preserving search and sort.
Search clearing is separate. Copied links, reload and Back/Forward restore effective
state. New criteria restart pagination. Related navigation transfers no cursor,
sort or text modality: a person's name never becomes a literal face-image query.
Assignment/page-content/unassigned-face and discovery choices stay on their
applicable view. Similarity witnesses (`origin_matched_face`, `origin_reference_face`)
identify real detections; they are not hidden filters. Witness faces are loaded
inside the current person and shared scope, independently of the first result page.

A document heading or +more link explicitly selects that document's internal source
UUID for its scan list. Opening a page keeps existing shared scope without adding
an implicit page filter. Page document breadcrumbs use a scans-only
`archive_document` scope, resolved to the registered internal document when one
exists. Without a registered document it remains an explicit, removable archive
scope alongside its library on Scans; it does not restrict unrelated resources.

Below 640px, filters start collapsed beside the search/sliders row. Tags remain
visible and settings survive collapse. Invalid copied UUIDs or bounds remain
visible as removable tags and block list requests until corrected or removed.
Controls use standard shadcn-vue components and the layout in [AGENTS.md](../AGENTS.md).

### Legacy URL and API compatibility

The router replaces copied #31 URL names deliberately:

- `evidence_library`, `evidence_document`, `evidence_source` become `library`,
  `document`, `page`. Same-meaning multi-selections are combined.
- `evidence_user/key/from/to` become the canonical modification keys only on
  profiles and page workspaces, where the returned records are annotations.
  On Documents, People and scan search they are removed with a visible notice;
  applying them to those resources would change their meaning. Current date
  bounds take precedence when a link contains both old and new bounds.
- Existing resource `touched_*`/`api_key` criteria remain active canonical criteria.
  Obsolete `origin_person_*`, `origin_source_*`, `origin_discovery_*`,
  `origin_text` and `origin_return` context is removed. It never silently filters
  results or restores stale selections on return navigation.
- Old Scans `library` + archive `document` links resolve to internal registered
  document UUIDs before querying. A missing/unresolvable UUID is not treated as
  an unrestricted scope. Explicit archive breadcrumbs support pages registered
  before their parent document. Lookup failures are reported with Retry.
- HTTP `filter.evidence_*` parameters return 422 naming the replacement, rather
  than silently broadening results or reinterpreting annotation edits. API callers
  must migrate intentionally. The schemas reject obsolete filter properties.
  No historical attribution is backfilled and no schema migration is needed.

PostgreSQL implements the shared predicates. Weaviate rejects unsupported shared
scope/modification criteria instead of pretending to evaluate them.

## Page workspace activity

Faces, Activity and Statistics tabs replace the sidebar pane while preserving
selection and candidate settings. `panel=activity|statistics` chooses the pane;
`activity_group=user` groups edits by latest user instead of local day. Activity
loads the page's complete faces/mentions independently of workspace filters.
Day/user headings summarize the recorded edits without workspace-filter actions
or selected workspace groups. Unknown history is shown explicitly. Activity
entries display their own annotation times. `#link-statistics` still opens Statistics.

## Extending filters

Update the schema and HTTP dependency, repository predicates/counts/cursors,
export OpenAPI locally and regenerate the SDK, then update shared state, controls,
tags and query keys. Test actual AND/OR results, same-link restrictions, own-record
modification, unknown metadata and cursor reset. Extend the synthetic preview and
its preservation tests; follow [AGENTS.md](../AGENTS.md).

The scan editor's right panel shows entities on the current page, or text/face
search results across all accessible data. It does not inherit workspace source,
assignment, actor/date or API key predicates, and shows no workspace tags or
validation messages. Retained workspace URL values still apply when navigating
back to ordinary lists. Invalid workspace values cannot block page entities or
search. Text lookup works without selecting a face. The explicit page annotation
link-state control uses `page_link_state`; it affects annotation display rather
than the page's identity membership or global candidates. The workspace's
`link_state` remains separate. Page navigation drops the page-specific setting.
