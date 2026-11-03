# Object versions and audit history

PostgreSQL keeps current entities, faces, text mentions and sources in their
existing tables. Each object starts at `version=1`. Migration
`d34a021b0015` initializes existing records at 1, without fabricating earlier
states, actors or timestamps. Run the normal database migration before starting
this API revision. Deploy the regenerated SDK and mutation callers together.

## Editing and deleting

Every patch body requires `version`, taken from the object the caller
read. A matching actual change archives the complete previous persisted state
and advances the current version once. A matching no-op retains its version and
creates no history. A stale request, including a stale no-op, returns HTTP 409
with `detail.code=version_conflict`. Reload and review the data before making a
new edit; clients never automatically retry an overwrite with a newer version.
The caller cannot assign the stored version.

Single-object DELETE endpoints take a JSON `VersionedTarget` body:
`{"object_id": "<UUID from the URL>", "version": 3}`. Batch face/mention
DELETE endpoints take a list of these targets. Entity bulk deletion uses a
`targets` list alongside its filter and limit; every matched object needs a
supplied target. Merge bodies carry the target's `version` and a `sources`
list of versioned targets. The single-source merge accepts exactly one source.
Missing preconditions are invalid; all existing explicit targets are checked
before any write. Conflicts and failures roll back the entire operation,
including history inserts and server effects.

All ordinary list/search/detail objects and historical states require the shared
`version` field. Responses never substitute version 1 for missing data.
Creation initializes the version on the server. Frontend drafts and selections
retain the version of their exact data through background refreshes; mutations
never search the query cache or fetch newer versions to authorize older edits.
Page-number drafts reset on source navigation and ignore late responses for an
earlier page. Group selections enumerate their occurrences when selected and retain those
versions before any mutation is submitted.

Repository graph mutations use the existing transaction advisory lock, followed
by stable object row locks. Capture, comparison, archival, version updates and
the mutation commit on the same request-scoped SQLAlchemy session. This simple
implementation serializes graph writes; it does not introduce an event replay
engine or a global version sequence. Direct SQL/operator changes outside the
repository contract are not audited.

## Object boundaries and retention

Entity profile history includes the full alias collection, original creation
metadata, and explicit portrait selection. Face history includes the inherited
occurrence fields, keypoints and every stored model vector. Mention history
includes the text/context, assignment and previous verification metadata. Source
history includes the appropriate page/document subtype fields.

Derived activity timestamps and automatic portrait resolution do not create
profile revisions merely because evidence changed. Invalidating a *manual*
portrait selection does archive its previous selection and advance that profile.
Source activity propagation likewise does not create source content revisions;
editing a page number does. Original creation metadata remains unchanged.

`pg_demo_audit_changes` records transition time and real user/API-key IDs for
internal transition filters. Separate `pg_demo_entity_history`,
`pg_demo_face_history`, `pg_demo_text_mention_history` and
`pg_demo_source_history` tables store predecessors under `(id, version)`.
They retain original column types, stored normalized/search values, verification
fields, subtype fields and filter indexes. Versioned alias and embedding tables
reference their immutable historical parent with composite foreign keys.
There are no foreign keys from history to live entities, sources, annotations,
users or models, so live deletion neither blocks on history nor rewrites its IDs.
Migration `d34a021b0016` converts previously deployed JSON snapshots and their
children into these tables without resetting preview data or checkpoints.

Deletion archives the final current state with `deleted=true`, at that state's
existing version. Merge archives deleted source profiles and revisions of
changed dependent annotations and target profiles. Live cascades are preceded
by capture of affected annotations.

Historical IDs are plain UUID values, without foreign keys to live objects or
users; audit rows survive deletion of referenced live data. Related objects are
referenced only by ID, never by related version. New objects receive fresh
server-generated UUIDs. No normal API edits or deletes history. This API does not
provide reconstruction, restore, undo or an audit timeline UI.

## Read endpoints

All four list endpoints require `people-gator:audit`. An auditor can hold this
scope alone, without `people-gator:admin` or `people-gator:browse`. Browse/admin
scopes do not implicitly grant audit access. Configure the scope on a user or API
key explicitly; for bearer login request `scope=people-gator:audit`. Existing
tokens must be reissued with that scope. The frontend keeps its existing scopes
because it has no audit UI; the example demo user also permits audit requests.

| GET endpoint | Identity/relationship filters | Typed historical item |
| --- | --- | --- |
| `/api/v1/audit-entities` | `filter.entity_id` | Entity profile, aliases and portrait selection |
| `/api/v1/audit-faces` | `filter.detection_id`, `filter.entity_id`, `filter.source_id` | Face, keypoints, vectors and assignment/verification |
| `/api/v1/audit-text-mentions` | `filter.mention_id`, `filter.entity_id`, `filter.source_id` | Recorded text/context and assignment/verification |
| `/api/v1/audit-sources` | `filter.source_id`, `filter.source_type`, `filter.library`, `filter.document_id`, `filter.page_id` | Discriminated page, document or image state |

Lists return archived revisions and final deleted states; current records remain
available through the ordinary resource endpoints. A never-edited current object
has no archived revision yet.

Items are the historical states themselves, including their resource-specific
UUID, required version, original creation/last-touch metadata and deletion marker.
There is no redundant metadata/state wrapper, generic object-kind selector or
untyped snapshot dictionary. Vectors are numeric arrays. Source states
discriminate on `source_type`. Audit queries never require the referenced live
objects. Public repository access provides resource-specific lists and
`get_entity`, `get_face`, `get_text_mention` and `get_source` methods.

For faces previously linked to an entity, use:

```text
GET /api/v1/audit-faces?filter.entity_id=<entity-UUID>&sort=version&direction=asc
```

Repeat an ID parameter to match any of several IDs, and combine different
criteria with AND. For example, add `filter.source_id=<source-UUID>` to restrict
those historical assignments to a source. These filters match the persisted
snapshot, so reassignment and live-object deletion do not erase earlier links.
One item represents one revision; the same face ID can appear several times.

All lists also accept:

| Parameter | Meaning |
| --- | --- |
| `filter.actor_user_id` | One or more transition actors |
| `filter.since`, `filter.until` | Inclusive transition timestamps with timezone |
| `filter.version_min`, `filter.version_max` | Inclusive object-version range |
| `filter.deleted` | Whether the revision is a final deletion |
| `sort` | `time` (default) or `version` |
| `direction` | `asc` or `desc` (default) |
| `limit`, `offset` | Page size 1–500 (default 50) and offset (default 0) |

Responses reuse `GenericListResponse`: `items`, `total_count`, `limit` and
`cursor` (null for these offset-paginated audit requests). Use the same
minimum and maximum version to select an exact archived version. A list with no
matching revision returns an empty `items` array. The old generic `/api/v1/audit`
and generic single-version route have been removed.

UUID and version provide deterministic tie breakers. Versions are independent per
object; ordering different objects by version is not a global chronology. Offset
pagination can shift if other users create revisions between requests. Compare
adjacent annotation versions and the current record to understand transitions.

The optional Weaviate adapter explicitly rejects versioned edits and audit reads
with HTTP 501. It cannot provide PostgreSQL's transactional archival guarantee.
