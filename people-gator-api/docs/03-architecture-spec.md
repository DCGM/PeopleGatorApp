# People Gator Architecture Specification

## 1. Overview

This service is the authoritative backend for:

1. Search orchestration.
2. Grounded entity lifecycle.
3. Annotation and review workflows.
4. Auth, audit, and export.

Inference systems remain external and deliver prepared artifacts.

## 2. Logical Components

### 2.1 Ingestion Gateway

1. Validates incoming JSONL and structured payloads.
2. Stores artifacts and provenance metadata.
3. Enqueues targeted reindex jobs.

### 2.2 Data Registry

1. Canonical source of `library`, `document`, `page` lineage.
2. Tracks artifact type, ingest batch, producer metadata, and model metadata.
3. Exposes reindex planning metadata.

### 2.3 Search Layer

1. Hybrid lexical and vector retrieval.
2. Candidate generation plus reranking.
3. Person-centric evidence assembly for annotation workflows.

### 2.4 Authority Grounding Service

1. Resolves local Wikidata subset candidates.
2. Scores aliases, portraits, and context match.
3. Emits grounding proposals for annotation and review.
4. Stores typed external identifiers using scheme-based notation (`wikidata_qid`, `nkcr_authority_id`, `google_entity_graph_mid`, extensible).
5. Persists grounding evidence records by type: `name_record`, `text_record`, `photo_record`.
6. Requires language-tagged textual fields for names and text evidence.

### 2.5 Identity Resolution Service

1. Builds and updates `EntityProposal` records from search evidence.
2. Uses face, image, text, and page-level face-to-name signals.
3. Maintains explainable confidence breakdowns and proposal-level confidence.

### 2.6 Annotation Service

1. Manages annotation assignment and `AnnotationInstance` lifecycle.
2. Stores annotation revisions as independent rows (no in-place overwrite).
3. Keeps proposal baseline immutable while annotation evolves.

### 2.7 Review Service

1. Manages review assignment for submitted annotation instances.
2. Stores `ReviewInstance` adjudication.
3. Publishes reviewed outcomes to `MasterEntity` and grounding versions.

### 2.8 Auth and Access Control

1. JWT authentication.
2. Role enforcement for `admin`, `annotator`, `reviewer`, `reader`.
3. Audit trail for all mutating actions.

### 2.9 Export Service

1. Starts asynchronous export jobs.
2. Produces reproducible reviewed datasets.

## 3. Storage Architecture

### 3.1 PostgreSQL (Transactional Truth)

1. Users, roles, tasks, decisions, audit log, and exports.
2. Master entities, grounding versions, entity proposals, and evidence links.
3. Annotation instances, review instances, and removal log records.
4. Local Wikidata subset.
5. Artifact and indexing metadata registry.
6. Grounding identifier records and grounding evidence metadata (including language tags, confidence, and source linkage).

### 3.2 Weaviate (Retrieval Index)

1. Vector and hybrid retrieval backend.
2. Collections for page, region, line, image, face, and name retrieval.

### 3.3 Object Storage

1. Raw scans and artifact payloads.
2. Ingest manifests and reproducibility artifacts.
3. Grounding evidence assets (photo crops, text snapshots, and serialized name evidence payloads) with stable local asset paths and content hashes.

### 3.4 Grounding Evidence Storage Contract

For each grounding evidence record, persist:

1. `record_type` in `{name_record, text_record, photo_record}`
2. source context (`provider`, `library`, `document`, `page`, source URI where available)
3. language metadata for textual content (`language_tag`, optional `script`, optional `transliteration`)
4. local storage pointer (`local_asset_path`, storage backend)
5. `content_hash` and ingestion metadata for reproducibility

## 4. Model Metadata and Reindex Strategy

Full multi-version index coexistence is not required for MVP, but model metadata tracking is mandatory.

### 4.1 Required Registry Fields

For each ingested artifact, persist at least:

1. `artifact_id`
2. `artifact_type`
3. `library`, `document`, `page`
4. `model_name`
5. `model_version`
6. `ingested_at`
7. `content_hash`
8. `indexed_at`
9. `index_status` in `{pending, indexed, failed}`
10. `index_target` (which index family needs update)

### 4.2 Incremental Reindex Plan

1. On ingest, compare `content_hash` and `model_version` with latest indexed record for the same source unit.
2. If unchanged, skip reindex.
3. If changed, mark only affected source units as `pending`.
4. Reindex queue processes pending units in batches.
5. Search reads latest successful indexed representation per source unit.

This avoids global recomputation while keeping model provenance available for audits and future migrations.

## 5. Retrieval and Ranking Pipeline

1. Candidate generation:
   1. Textual retrieval from OCR and named entities.
   2. Vector retrieval from faces, images, lines, regions, and names.
   3. Authority lookup from local Wikidata subset.
   4. Page-level face-to-name link candidates.
2. Candidate reranking:
   1. Apply profile-defined weights.
   2. Compute evidence contribution breakdown per signal.
3. Evidence assembly:
   1. Build `face_evidence`, `image_evidence`, `text_evidence` buckets.
   2. Build `EntityProposal` candidates with optional grounding links.
   3. Attach provenance and per-item relevance.

## 6. Regional Grounding Defaults

Authority filtering defaults to:

1. Czechoslovakia
2. Czechia
3. Slovakia
4. Hungary
5. Austria
6. Austria-Hungary
7. Germany
8. Poland

Regional filters are configurable without schema changes.

## 7. Observability and Quality Gates

### 7.1 Required Telemetry

1. Request latency and error rates.
2. Search result interaction signals.
3. Agreement metrics by queue and annotator.
4. Review turnaround time.
5. Grounding acceptance rate.
6. Reindex queue lag and failure rates.

### 7.2 Release Gates

1. API schema compatibility tests.
2. Search and pagination contract tests.
3. Annotation and review workflow integration tests.
4. Export artifact contract tests.

## 8. Implementation Phases

### 8.1 Phase 1 (MVP Foundation)

1. FastAPI skeleton with typed models.
2. PostgreSQL schema for master entities, grounding versions, proposals, and annotation/review revisions.
3. Weaviate retrieval collections.
4. Ingestion gateway plus incremental reindex queue.
5. Search profile management.
6. Single `POST /search` endpoint.

### 8.2 Phase 2 (Annotation and Review Depth)

1. Multi-annotator assignment policies.
2. Agreement metrics and disagreement taxonomy.
3. Reviewer adjudication tooling.

### 8.3 Phase 3 (Operational Maturity)

1. Export hardening.
2. Dashboarding and SLO alerts.
3. Optional graph projection if needed.
