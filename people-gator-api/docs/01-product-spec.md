# People Gator Product Specification

## 1. Purpose

People Gator API is an annotation-first backend for person-centric retrieval in historical document scans.

The main user workflow is:

1. Search for a person using name, face, text context, or combinations.
2. Build or update grounded person entities from evidence.
3. Run annotation and review to converge on verified master records.

## 2. Product Scope

### 2.1 In Scope

1. Search over prepared historical scan artifacts.
2. Person-centric evidence retrieval (face, image, page, line, region, named entity span).
3. Grounding to locally imported Wikidata candidates.
4. Annotation workflows, inter-annotator agreement tracking, and reviewer adjudication.
5. Auth, roles, audit logging, and export of reviewed records.

### 2.2 Out of Scope

1. Model training.
2. Model inference (face detection, OCR, embeddings, NER generation).
3. Live external authority queries at search time.

Upstream systems provide prepared artifacts to this API.

## 3. Geographic and Historical Focus

Grounding and search behavior must prioritize Middle Europe historical context with at least:

1. Czechoslovakia.
2. Czechia.
3. Slovakia.
4. Hungary.
5. Austria.
6. Austria-Hungary.
7. Germany.
8. Poland.

This regional scope is configurable but has the above defaults.

## 4. Design Principles

1. Annotation-first: the product exists to support search plus grounded entity creation and adjudication.
2. Typed canonical records: preserve canonical fields and provenance keys.
3. Explainable ranking: every result includes signal contributions.
4. Human-in-the-loop identity resolution: automated links are tentative until reviewed.
5. Separation of concerns: this package ingests and reasons over artifacts but does not infer them.

## 5. Canonical Domain Records

The service treats these structures as canonical:

1. PeopleGatorAnnotation
2. PeopleGatorDetection
3. PeopleGatorNamedEntitySpan
4. PeopleGatorNamedEntity
5. PeroLine
6. PeroRegion
7. PeroLayout

Mandatory semantics:

1. Preserve provenance keys: `library`, `document`, `page`.
2. Keep page-space coordinates in `page_*` fields only.
3. Keep face keypoint order stable: `[left_eye, right_eye, nose, left_mouth_corner, right_mouth_corner]`.
4. Keep linkage identifiers stable: `image_name`, `crop_name`.

## 6. Domain Models With Separated Responsibilities

### 6.1 PersonEntity

1. Identity aggregate record.
2. Stores canonical display name, aliases, optional authority linkage, and current resolved status.
3. Does not store per-annotator decisions directly.

### 6.2 EntityInstance

1. Versioned hypothesis snapshot for one `PersonEntity` over a concrete evidence set.
2. Carries confidence, explanation metadata, and lifecycle state.
3. Immutable after review; new evidence creates a new instance version.

### 6.3 EvidenceItem

1. Atomic evidence object (face, image, page, region, line, named entity span).
2. Stores modality-native payload plus provenance.

### 6.4 EvidenceLink

1. Association between one `EntityInstance` and one `EvidenceItem`.
2. Stores relation status (accepted, rejected, tentative) and scoring metadata.

### 6.5 AnnotationTask

1. Workflow container for annotation assignment.
2. Points to a frozen `EntityInstance` version.
3. Holds assignment policy and lifecycle state.

### 6.6 AnnotationDecision

1. One annotator submission for one `AnnotationTask`.
2. Contains acceptance and rejection decisions for grounding and evidence.

### 6.7 ReviewTask

1. Reviewer work item for one `AnnotationTask` once policy conditions are met.

### 6.8 ReviewDecision

1. Reviewer adjudication output.
2. Produces the reviewed master outcome and closes or reopens workflow.

## 7. Formal State Machines

### 7.1 EntityInstance State Machine

States:

1. `tentative`
2. `annotation_pending`
3. `annotated`
4. `review_pending`
5. `reviewed`
6. `rejected`

Allowed transitions:

1. `tentative -> annotation_pending`
2. `annotation_pending -> annotated`
3. `annotated -> review_pending`
4. `review_pending -> reviewed`
5. `review_pending -> rejected`
6. `annotated -> rejected`

Rules:

1. `reviewed` is terminal for that instance version.
2. New evidence after `reviewed` creates a new `EntityInstance` version starting at `tentative`.
3. `rejected` instances are never silently deleted; they remain audit-visible.

### 7.2 Grounding State Machine

States:

1. `none`
2. `proposed`
3. `accepted`
4. `rejected`

Allowed transitions:

1. `none -> proposed`
2. `proposed -> accepted`
3. `proposed -> rejected`
4. `accepted -> proposed`
5. `rejected -> proposed`

Rules:

1. Only reviewer actions can move to `accepted`.
2. Re-proposal is allowed when new evidence appears.

### 7.3 AnnotationTask State Machine

States:

1. `draft`
2. `published`
3. `in_progress`
4. `ready_for_review`
5. `completed`
6. `cancelled`

Allowed transitions:

1. `draft -> published`
2. `published -> in_progress`
3. `in_progress -> ready_for_review`
4. `ready_for_review -> completed`
5. `draft -> cancelled`
6. `published -> cancelled`
7. `in_progress -> cancelled`

Rules:

1. Completed tasks are immutable except for administrative audit metadata.
2. Any cancellation requires reason code.

## 8. Search and Grounding Behavior

1. Search uses multi-signal retrieval over text, visual similarity, metadata context, and face-to-name page co-occurrence.
2. Result objects must include:
   1. Best identity hypothesis.
   2. Ranked `face_evidence`, `image_evidence`, and `text_evidence`.
   3. Per-signal contribution scores.
   4. Effective `search_profile_id`.
3. Weights are sourced only from saved search profiles.
4. Search never accepts ad hoc per-request weight overrides.

## 9. MVP Scope (Reduced But Annotation-Centered)

### 9.1 MVP Must-Haves

1. Ingestion of prepared artifacts.
2. `POST /search` as the primary search primitive.
3. Search profile CRUD.
4. PersonEntity and EntityInstance creation and retrieval.
5. Annotation and review tasks with submit endpoints.
6. Grounding states and reviewer adjudication.
7. Auth, roles, audit log, and basic export job support.

### 9.2 Deferred

1. Advanced graph projection.
2. Full analytics dashboarding.
3. Broad workflow automation beyond targeted reindex and assignment queues.

## 10. Success Criteria

1. Annotators can go from search to grounded entity update in one workflow.
2. Reviewers can adjudicate disagreements and produce reviewed master records.
3. Every result and decision is provenance-traceable and audit-loggable.
4. Reindex work is incremental and avoids global recomputation.

## 11. Grounding Notation and Evidence Model

To keep external authority linkage stable and extensible, grounding data must follow a typed identifier and evidence-record model.

### 11.1 Authority Identifier Notation

Each external identifier must be represented as a typed identifier object instead of adding ad hoc columns per authority provider.

Required fields:

1. `scheme` (identifier namespace)
2. `value` (identifier value in provider-native format)
3. `state` in `{proposed, accepted, rejected}`
4. `confidence` (float in `[0,1]`)
5. `asserted_at` (UTC ISO-8601)
6. `asserted_by` (actor id)

Initial required schemes:

1. `wikidata_qid` (for example `Q12345`)
2. `nkcr_authority_id` (Narodni Knihovna CR authority identifier)
3. `google_entity_graph_mid` (for example `/m/012abc`)

New schemes may be added without schema-breaking changes.

### 11.2 Grounding Evidence Record Types

Grounding decisions must be backed by typed evidence records:

1. `name_record`
2. `text_record`
3. `photo_record`

Each evidence record must carry:

1. source metadata (`provider`, `library`, `document`, `page`, and source URI where available)
2. content payload or structured reference to payload
3. `local_asset_path` (pointer to local object storage or filesystem asset)
4. `content_hash` (for reproducibility and dedup)

### 11.3 Language Representation Rules

All human-readable name or text values used by grounding must carry explicit language metadata.

Required fields:

1. `text`
2. `language_tag` (BCP-47; for example `cs`, `sk`, `de`, `hu`, `pl`, `und`)
3. `normalized_text` (normalization profile documented by implementation)

Optional fields:

1. `script`
2. `transliteration`
3. `language_confidence`

Rules:

1. Preserve original source text unchanged.
2. Keep normalization output in a separate field.
3. Use `und` when language cannot be determined reliably.

### 11.4 Grounding Entity Model Diagram
