# Object versions and audit history

PostgreSQL keeps current entities, faces, text mentions and sources in their
existing tables. Each object starts at `version=1`. Migration
`d34a021b0015` initializes existing records at 1, without fabricating earlier
states, actors or timestamps. Run the normal database migration before starting
this API revision. Deploy the regenerated SDK and mutation callers together.

## Editing and deleting

Every patch body requires `expected_version`, taken from the object the caller
read. A matching actual change archives the complete previous persisted state
and advances the current version once. A matching no-op retains its version and
creates no history. A stale request, including a stale no-op, returns HTTP 409
with `detail.code=version_conflict`. Reload and review the data before making a
new edit; clients never automatically retry an overwrite with a newer version.
The caller cannot assign the stored version.

Single-object DELETE endpoints require the `expected_version` query parameter.
Face and text-mention batch DELETE endpoints accept a JSON object mapping target
UUIDs to expected versions. Entity bulk deletion and merge bodies require
`expected_versions`, mapping every selected entity (including the merge target)
to its read version. Missing preconditions are invalid; all existing explicit
targets are checked before any write. Conflicts and other failures roll back the
entire repository operation, including history inserts and server effects.

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

`pg_demo_audit_changes` records the transition time and real user/API-key IDs.
`pg_demo_object_history` stores predecessors under the composite key
`(object_type, object_id, version)`. Deletion archives the final current state
with `deleted=true`, at that state's existing version. Merge archives the deleted
source profiles and revisions of changed dependent annotations and target
profiles. Live cascades are preceded by capture of affected annotations.

Historical IDs are plain UUID values, without foreign keys to live objects or
users; audit rows survive deletion of referenced live data. Related objects are
referenced only by ID, never by related version. New objects receive fresh
server-generated UUIDs. No normal API edits or deletes history. This API does not
provide reconstruction, restore, undo or an audit timeline UI.

## Read endpoints

Both endpoints require `people-gator:audit`. An auditor can hold this scope alone,
without `people-gator:admin` or `people-gator:browse`. Browse/admin scopes do not
implicitly grant audit access; grant `people-gator:audit` explicitly to any
credential that should read history. This works with bearer tokens and API keys.
For bearer login request `scope=people-gator:audit`; configure that scope on the
user credential first. Existing tokens must be reissued with the new scope.

The frontend continues requesting its existing browse/annotate/ingest/admin
scopes because it has no audit UI. The example demo user also permits audit
requests; existing configured users and keys are not upgraded automatically.

Endpoints:

- `GET /api/v1/audit` returns archived states with transition metadata,
  `total_count`, `limit` (1–500, default 50), and `offset` (default 0).
- `GET /api/v1/audit/{object_type}/{object_id}/versions/{version}` returns one
  archived version, including deleted objects. An unarchived current version or
  unknown version returns 404; read current objects through their usual endpoint.

List filters combine with AND:

| Parameter | Meaning |
| --- | --- |
| `object_type` | `entity`, `face`, `mention`, or `source` |
| `object_id` | Exact historical object UUID |
| `entity_id` | Entity profile UUID or assignment in the archived state |
| `source_id` | Source UUID or evidence source in the archived state |
| `actor_user_id` | Actor responsible for the transition |
| `since`, `until` | Inclusive transition timestamps with timezone |
| `version_min`, `version_max` | Inclusive object-version range |
| `deleted` | Whether the archived state is a final deletion |

Use `sort=time` (default) or `sort=version`, and `direction=asc|desc` (default
descending). Object type, UUID and version provide deterministic tie breakers.
Versions are independent per object; version ordering across different objects
is not a global chronology. Offset pagination is intentionally simple and can
shift if other users create revisions between requests. Filters on related IDs
refer to the archived predecessor, not the current assignment. Compare adjacent
annotation versions and the current record to understand assignment transitions.

The optional Weaviate adapter explicitly rejects versioned edits and audit reads
with HTTP 501. It cannot provide PostgreSQL's transactional archival guarantee.
