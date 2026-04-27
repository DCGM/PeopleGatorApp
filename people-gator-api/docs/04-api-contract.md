# People Gator API Contract (MVP)

## 1. Contract Rules

### 1.1 Transport and Encoding

1. JSON request and response with `application/json`.
2. UTC ISO-8601 for all datetime fields.

### 1.2 Authentication and Authorization

1. JWT bearer authentication for protected routes.
2. `POST /auth/login` and `POST /auth/refresh` are public.
3. Roles: `admin`, `annotator`, `reviewer`, `reader`.

### 1.3 Typed Error Envelope

```json
{
  "error": {
    "code": "validation_error",
    "message": "Human-readable message",
    "details": {}
  }
}
```

### 1.4 Unified Pagination Envelope

All collection endpoints must return:

```json
{
  "items": [],
  "cursor": "opaque-cursor-or-null",
  "limit": 50,
  "has_more": false
}
```

Rules:

1. No unbounded list endpoints.
2. `cursor` is opaque and server-issued.
3. `limit` is validated server-side with configured min and max.

### 1.5 Provenance and Schema Guarantees

1. Preserve canonical field names.
2. Include `library`, `document`, and `page` whenever available.
3. Preserve coordinate semantics and linkage identifiers.

## 2. Search and Profiles

### 2.1 POST /search

Single MVP search primitive.

Request:

```json
{
  "inputs": [
    { "modality": "face", "reference": "crop_123" },
    { "modality": "text", "query": "Jan Novak" },
    { "modality": "page", "reference": "page_77" }
  ],
  "profile": { "id": "8f3f20a8-4b8a-4ab6-91c1-672585a88c75" },
  "filter": {
    "types": ["person", "face", "image", "line"],
    "library": "lib-1",
    "document": "doc-9",
    "page": 77
  },
  "cursor": null,
  "limit": 50
}
```

Rules:

1. `profile.id` is required for weighted fusion.
2. All weights come from the saved profile.
3. Per-request weight overrides are not allowed.
4. Multiple inputs per modality are allowed.

Response:

1. Pagination envelope with ranked search results.
2. Each item includes evidence buckets and signal contribution breakdown.
3. Each item includes effective `search_profile_id`.

### 2.2 Search Profile Endpoints

1. `GET /search/profiles`
2. `GET /search/profiles/{profile_id}`
3. `POST /search/profiles`
4. `POST /search/profiles/{profile_id}/clone`
5. `PATCH /search/profiles/{profile_id}`
6. `DELETE /search/profiles/{profile_id}`

Collection endpoints in this group use the unified pagination envelope.

## 3. Authority, Master Entities, and Proposals

### 3.1 Endpoints

1. `GET /authority/people`
2. `POST /authority/people`
3. `GET /authority/people/{person_id}`
4. `GET /authority/people/{person_id}/instances`
5. `GET /authority/people/{person_id}/evidence`
6. `GET /entity-proposals`
7. `POST /entity-proposals`
8. `GET /entity-proposals/{proposal_id}`
9. `GET /entity-proposals/{proposal_id}/evidence`

### 3.2 Notes

1. Grounding uses local Wikidata subset.
2. Regional defaults: Czechoslovakia, Czechia, Slovakia, Hungary, Austria, Austria-Hungary, Germany, Poland.

### 3.3 Identifier Notation (Normative)

Authority identifiers must be represented as typed identifier objects.

```json
{
  "scheme": "wikidata_qid",
  "value": "Q191341",
  "state": "proposed",
  "confidence": 0.87,
  "asserted_at": "2026-04-24T12:00:00Z",
  "asserted_by": "user-123"
}
```

Rules:

1. `scheme` is required and extensible.
2. Initial required scheme values:
   1. `wikidata_qid`
   2. `nkcr_authority_id`
   3. `google_entity_graph_mid`
3. `value` must preserve provider-native format.
4. `state` must follow grounding transition rules in section 8.1.

### 3.4 Grounding Record Notation (Normative)

Grounding evidence records must use typed records.

```json
{
  "record_type": "photo_record",
  "source": {
    "provider": "kramerius",
    "library": "lib-1",
    "document": "doc-9",
    "page": 77,
    "uri": "https://example.invalid/source/record"
  },
  "content": {
    "summary": "portrait crop"
  },
  "local_asset": {
    "path": "s3://people-gator/grounding/photo/abc123.jpg",
    "media_type": "image/jpeg",
    "content_hash": "sha256:..."
  }
}
```

Allowed `record_type` values:

1. `name_record`
2. `text_record`
3. `photo_record`

Rules:

1. Every grounding record must include source provenance.
2. Every grounding record must include local asset pointer or typed content reference.
3. Responses from authority and person endpoints that return grounding details must preserve this notation.

### 3.5 Language Notation for Names and Text (Normative)

All name and text values used for grounding must include language metadata.

```json
{
  "text": "Jan Novak",
  "language_tag": "cs",
  "normalized_text": "jan novak",
  "script": "Latn",
  "transliteration": null,
  "language_confidence": 0.95
}
```

Rules:

1. `language_tag` uses BCP-47.
2. Use `und` when language is unknown.
3. Preserve source text unchanged in `text`.
4. Keep normalization output in `normalized_text`.

## 4. Entity and Evidence Retrieval

### 4.1 Endpoints

1. `GET /people`
2. `GET /people/{person_id}`
3. `GET /people/{person_id}/evidence`
4. `GET /evidence/types`
5. `GET /evidence/{evidence_id}`
6. `GET /evidence/{evidence_id}/people`
7. `GET /data/{modality}/{evidence_id}`

### 4.2 Pagination Rules

1. Collection routes use unified envelope.
2. Single-object routes return typed object only.

## 5. Annotation and Review Workflow API

The workflow is proposal-first:

1. Start annotation from one `EntityProposal`.
2. Keep each annotation update as a separate `AnnotationInstance` revision.
3. Keep the original proposal immutable.

## 5.1 Annotation Task Drafts

1. `GET /annotation/task-drafts`
2. `POST /annotation/task-drafts`
3. `GET /annotation/task-drafts/{draft_id}`
4. `PATCH /annotation/task-drafts/{draft_id}`
5. `POST /annotation/task-drafts/{draft_id}/publish`
6. `POST /annotation/task-drafts/publish`
7. `DELETE /annotation/task-drafts/{draft_id}`

## 5.2 Annotation Tasks

1. `GET /annotation/tasks`
2. `GET /annotation/tasks/{task_id}`
3. `PATCH /annotation/tasks/{task_id}`
4. `DELETE /annotation/tasks/{task_id}`

## 5.3 Annotation Decisions

1. `GET /annotation/instances`
2. `GET /annotation/instances/me`
3. `GET /annotation/instances/{task_id}`
4. `PATCH /annotation/instances/{task_id}/person`
5. `POST /annotation/instances/{task_id}/submit`

Revision rule:

1. Mutating operations in this section create a new annotation revision row and preserve prior revisions.

## 5.4 Review Decisions

1. `GET /review/instances`
2. `GET /review/instances/me`
3. `GET /review/instances/{task_id}`
4. `PATCH /review/instances/{task_id}/person`
5. `POST /review/instances/{task_id}/submit`

Removal logging rule:

1. Any remove or cancel operation in annotation or review flows must emit a `RemovalLog` record.

Collection routes in sections 5.1-5.4 use unified pagination envelope.

## 6. Export API

1. `POST /export/jobs`
2. `GET /export/jobs/{job_id}`
3. `GET /export/jobs/{job_id}/download`

Long-running exports return asynchronous job handles.

## 7. Auth and User API

1. `POST /auth/login`
2. `POST /auth/refresh`
3. `POST /users`
4. `GET /users/me`
5. `GET /users/{user_id}`
6. `PATCH /users/{user_id}`

## 8. Domain State Machines (Normative)

### 8.1 Grounding

1. `none -> proposed`
2. `proposed -> accepted`
3. `proposed -> rejected`
4. `accepted -> proposed`
5. `rejected -> proposed`

Only reviewer actions can produce `accepted`.

### 8.2 EntityProposal

1. `draft -> ready_for_annotation`
2. `ready_for_annotation -> annotated`
3. `annotated -> reviewed`
4. `reviewed -> closed`
5. `annotated -> closed`

Proposal rows remain immutable baselines for annotation revisions.

### 8.3 AnnotationInstance

1. `in_progress -> submitted`
2. `submitted -> reviewed`
3. `in_progress|submitted|reviewed -> superseded`
4. `in_progress|submitted -> removed`

## 9. Audit and Idempotency

1. Every mutating action is audit-logged with actor, timestamp, old value, and new value.
2. Ingest and long-running mutation endpoints support idempotency keys.
