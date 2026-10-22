# Person portraits

PostgreSQL stores `thumbnail_face_id` and `thumbnail_mode` on each entity.
Every entity response (including search results and nested merge results) carries
these fields. `automatic` with a null reference means no eligible portrait.
Clients load the saved reference through authenticated
`GET /api/v1/faces/{thumbnail_face_id}/aligned_crop`; failed media requests use
initials. Media failures do not change the saved choice.
Stored landmarks that cannot be aligned return the recoverable HTTP 422
`invalid_face_keypoints` error; see [aligned face crops](ALIGNED-FACE-CROPS.md).

In a person's evidence grid, select one face and choose **Use as portrait** in
its bottom action bar. To reset, select the face marked **Portrait** and choose
**Use automatic** in the same bar.

PATCH `/api/v1/entities/{entity_id}` and `/api/v1/entities:batch` accept:

- Omitted `thumbnail_face_id`: preserve the current choice and policy.
- A linked face UUID: select that face in `manual` mode.
- `"thumbnail_face_id": null`: return to `automatic` mode. A currently automatic,
  valid choice remains stable; resetting a manual choice selects the lowest
  eligible face UUID.

Selection requires the existing annotate permission. PostgreSQL validates the
entire batch before mutation and rolls failures back. Missing/foreign faces and
non-person selections return 422. Missing entities retain the existing single
404/batch-null behavior. Repeating an unchanged selection is a no-op, including
its last-change metadata. A mode change is a real edit even if the image is the
same. User/API-key attribution follows existing entity mutation rules.

Eligibility means an existing face linked to that person, regardless of evidence
link state, pagination or evidence filters. The first assigned face becomes the
saved automatic portrait. Later assignments, identity edits and merges keep that
choice while it remains linked; automatic mode does not continuously rank faces.
For historical records, faces inserted together in one SQL statement, an empty
merge target, a manual reset or an invalidated choice, the lowest eligible UUID
breaks ties over the available faces. Bulk requests that the ORM inserts in
separate statements keep the first statement's choice. These fallback choices are saved too. A reset already
in automatic mode preserves the saved choice. There is no image-quality service or storage probe in
this policy. A face can be eligible even when its media is temporarily unavailable.

Annotation graph mutations and thumbnail PATCH share the existing transaction
advisory lock, followed by row locks. Triggers validate ownership, fill an empty
choice once per distinct owner in a face-insert statement, repair both owners on reassignment/unlink, and repair
references during face/source cascade deletion. A face foreign key, policy checks
and lifecycle triggers also protect direct database writes. A valid target choice
survives merge; an empty target resolves over the complete merged face set by UUID.
Source portrait preferences are discarded when sources merge into a target.
Repairs are part of the evidence transaction; existing repository code attributes
the responsible mutation. Triggers and reads never invent actors or advance touch
times. Media bytes are neither copied nor stored on entities.

Run migrations before starting this revision. See [migration guidance](DATABASE-MIGRATIONS.md).
The migration adds nullable references plus an automatic policy and backfills
without changing identity IDs, evidence, link verification, creation metadata or
last-change metadata. Downgrade removes portrait preferences only; back up before
upgrading a retained store. Never apply destructive schema tests to retained data.

The legacy Weaviate adapter has no cross-object atomic transaction/lifecycle
contract for persisted portraits. It returns the compatible automatic/null
response defaults and explicitly rejects thumbnail PATCH (including reset).
It rejects a thumbnail-containing batch before writing any item. Other existing
entity operations remain supported. PostgreSQL is required for this feature.
