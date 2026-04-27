# People Gator Product Specification

## 1. Purpose

People Gator API is an annotation-first backend for person-centric retrieval in historical document scans.

The main user workflow is:

1. Search for a person using name, face, text context, or combinations.
2. Build grounding versions and entity proposals from evidence.
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

### 6.1 MasterEntity

1. Stable identity aggregate for one person.
2. Stores canonical display name and global status.
3. Connects to versioned grounding records.

### 6.2 GroundingVersion

1. Versioned grounding snapshot for one `MasterEntity`.
2. Contains candidate external identifiers (Wikidata and other schemes), names, and photos.
3. New grounding evidence creates a new version.

### 6.3 EntityProposal

1. Explicit proposal used as the baseline object for annotation.
2. Can optionally target an existing `MasterEntity`.
3. Connects proposed names, proposed grounding candidates, and linked evidence.

### 6.4 EvidenceItem

1. Atomic evidence object (face, image, page, region, line, named entity span, text).
2. Has required source provenance.
3. Has polarity constrained to `positive` or `negative`.

### 6.5 AnnotationInstance

1. One independently updatable annotation revision derived from an `EntityProposal`.
2. Updates create a new revision row and preserve previous revisions.
3. Original proposal remains unchanged.

### 6.6 AnnotatedEntity

1. Materialized annotation outcome for one `AnnotationInstance`.
2. Captures selected name and selected grounding.
3. Can link to an existing `MasterEntity` or stay unresolved.

### 6.7 ReviewInstance

1. Reviewer adjudication for one `AnnotationInstance`.
2. Produces accept/reject/request-changes decision.

### 6.8 RemovalLog

1. Immutable audit record for removals.
2. Stores target type, target id, actor, reason, and timestamp.

## 7. Formal State Machines

### 7.1 GroundingVersion State Machine

States:

1. `tentative`
2. `proposed`
3. `accepted`
4. `rejected`

Allowed transitions:

1. `tentative -> proposed`
2. `proposed -> accepted`
3. `proposed -> rejected`
4. `accepted -> proposed`
5. `rejected -> proposed`

Rules:

1. Each accepted or rejected grounding result remains in history through versioning.
2. New evidence creates a new `GroundingVersion`.

### 7.2 EntityProposal State Machine

States:

1. `draft`
2. `ready_for_annotation`
3. `annotated`
4. `reviewed`
5. `closed`

Allowed transitions:

1. `draft -> ready_for_annotation`
2. `ready_for_annotation -> annotated`
3. `annotated -> reviewed`
4. `reviewed -> closed`
5. `annotated -> closed`

Rules:

1. Proposal rows are retained as original baseline records.
2. Closing does not delete linked annotations.

### 7.3 AnnotationInstance State Machine

States:

1. `in_progress`
2. `submitted`
3. `reviewed`
4. `superseded`
5. `removed`

Allowed transitions:

1. `in_progress -> submitted`
2. `submitted -> reviewed`
3. `in_progress -> superseded`
4. `submitted -> superseded`
5. `reviewed -> superseded`
6. `in_progress -> removed`
7. `submitted -> removed`

Rules:

1. Superseding creates a newer revision while preserving history.
2. Removal creates a corresponding `RemovalLog` record.

## 8. Search and Grounding Behavior

1. Search uses multi-signal retrieval over text, visual similarity, metadata context, and face-to-name page co-occurrence.
2. Result objects must include:
   1. Best identity hypothesis.
   2. Best available person photo and person name.
   3. Ranked `face_evidence`, `image_evidence`, and `text_evidence`.
   4. Per-signal contribution scores.
   5. Effective `search_profile_id`.
3. Weights are sourced only from saved search profiles.
4. Search never accepts ad hoc per-request weight overrides.

## 9. MVP Scope (Reduced But Annotation-Centered)

### 9.1 MVP Must-Haves

1. Ingestion of prepared artifacts.
2. `POST /search` as the primary search primitive.
3. Search profile CRUD.
4. Master entity, grounding version, and proposal creation and retrieval.
5. Entity proposal, annotation instance, and review instance workflows.
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

## 11. Data Model Reference

The normative relational model is defined in `docs/02-entity-relations.md` and split into three diagrams:

1. Master entity and grounding versions.
2. Entity proposal and evidence acquisition.
3. Annotation, review, and removal log.
