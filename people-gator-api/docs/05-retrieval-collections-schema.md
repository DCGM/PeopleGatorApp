# Retrieval Collections and Index Design

This document specifies the canonical retrieval collections required for People Gator search, abstracted from any particular search engine implementation (Weaviate, Elasticsearch, etc.).

## 1. Design Principles

1. **Minimal duplication**: Collections contain only queryable evidence metadata and computed embeddings. All business logic, user decisions, and audit trails remain in PostgreSQL.
2. **Modality-based collections**: Separate indexes by evidence type to enable targeted retrieval, independent scoring, and model versioning.
3. **Provenance as first-class**: Every document includes complete lineage: `library`, `document`, `page`, `source_uri`, with stable IDs (`evidence_id`) for post-retrieval joins to PostgreSQL.
4. **Language tagging**: Text and name collections include BCP-47 language metadata for retrieval filtering.
5. **Hybrid retrieval support**: All collections support both lexical (BM25/full-text) and vector (embedding) queries.
6. **Model versioning**: Embedding model name and version are stored to support multi-version index coexistence during migrations.
7. **Incremental indexing**: Collections support efficient delta updates without full recomputation.
8. **PostgreSQL is source of truth**: User decisions, annotation revisions, reviews, audit logs, and entity links live in PostgreSQL only.

## 2. Core Collections

### 2.1 Face Collection

**Purpose**: Vector retrieval for face detections with optional metadata filtering.

**When indexed**:
- During ingestion of document photos with face detection results.
- On reindex when face embedding model version changes.

**Document schema** (evidence metadata + computed embeddings only):

```json
{
  "id": "string (uuid)",
  "evidence_id": "string (uuid, FK to EVIDENCE table)",
  "source_provider": "string (e.g., 'kramerius')",
  "source_uri": "string",
  "library": "string",
  "document": "string (uuid)",
  "page": "string (uuid)",
  "face_embedding": "vector (e.g., 512-dim float32)",
  "embedding_model": "string (e.g., 'facenet_512_v2')",
  "embedding_model_version": "string (e.g., '2024-01-15')",
  "content_hash": "string (sha256 of source artifact for reproducibility)"
}
```

**Note**: Bounding box, keypoints, image dimensions, confidence scores, and ingest/index timestamps are stored in PostgreSQL `EVIDENCE` table as metadata JSON. Search indexes retrieve `evidence_id` and join back to PostgreSQL for spatial data and decision-critical fields.

**Queries supported**:
- Vector similarity: "Find faces similar to query embedding"
- Filtered vector: "Find faces in page 5 of document X similar to query"
- Hybrid: "Faces matching keypoint pattern AND spatial proximity"

---

### 2.2 Image Collection

**Purpose**: Vector retrieval for page images and photo regions with optional layout context.

**When indexed**:
- During ingestion of full page scans or photo crops.
- On reindex when image embedding model version changes.

**Document schema** (evidence metadata + computed embeddings only):

```json
{
  "id": "string (uuid)",
  "evidence_id": "string (uuid, FK to EVIDENCE table)",
  "source_provider": "string (e.g., 'kramerius')",
  "source_uri": "string",
  "library": "string",
  "document": "string (uuid)",
  "page": "string (uuid)",
  "image_type": "string (enum: 'full_page', 'region_crop', 'face_crop', 'text_crop')",
  "image_embedding": "vector (e.g., 2048-dim float32 from ResNet50 or similar)",
  "embedding_model": "string (e.g., 'resnet50_imagenet')",
  "embedding_model_version": "string (e.g., '2024-01-15')",
  "content_hash": "string (sha256 for reproducibility)"
}
```

**Note**: Bounding box, image dimensions, mime type, ingest/index timestamps, and embedding quality metrics are in PostgreSQL `EVIDENCE` table as metadata JSON.

**Queries supported**:
- Vector similarity: "Find visually similar images"
- Filtered vector: "Find similar images on specific pages"
- Type-based filtering: "Find all region crops vs. full pages"

---

### 2.3 Name Collection

**Purpose**: Lexical retrieval for person names with language metadata and normalization.

**When indexed**:
- During ingestion of grounding records with name evidence.
- During authority (Wikidata) sync with aliases and canonical names.
- On reindex when normalization rules change.

**Document schema** (searchable name metadata only):

```json
{
  "id": "string (uuid)",
  "record_id": "string (uuid, FK to GROUNDING_NAME or authority record)",
  "record_type": "string (enum: 'grounding_name', 'wikidata_alias', 'nkcr_name')",
  "source_provider": "string (e.g., 'kramerius', 'wikidata')",
  "library": "string (if grounding_name)",
  "document": "string (if grounding_name)",
  "page": "int (if grounding_name)",
  "source_uri": "string",
  "name": "string (original name as written)",
  "language_tag": "string (BCP-47, e.g., 'cs', 'de', 'hu')",
  "content_hash": "string (for reproducibility)"
}
```

**Note**: Language confidence, ingest timestamps, confidence scores, and model versions are stored in PostgreSQL `GROUNDING_NAME` or authority table.

**Queries supported**:
- Full-text search: "Match on normalized_name or name for substring/phrase queries"
- Language-filtered: "Names in Czech only"
- Type-filtered: "Given names vs. family names"
- Hybrid: "Names in a region + fuzzy match"

---

### 2.4 Named Entity and Text Region Collection

**Purpose**: Lexical and optional vector retrieval for detected text spans (named entities, lines, regions).

**When indexed**:
- During ingestion of OCR lines, text regions, and NER-detected spans.
- On reindex when OCR or NER model version changes.

**Document schema** (searchable text metadata only):

```json
{
  "id": "string (uuid)",
  "evidence_id": "string (uuid, FK to EVIDENCE table)",
  "source_provider": "string (e.g., 'ocr_engine', 'ner_model')",
  "source_uri": "string",
  "library": "string",
  "document": "string (uuid)",
  "page": "string (uuid)",
  "text_type": "string (enum: 'ocr_line', 'ocr_region', 'named_entity', 'text_region')",
  "ner_label": "string (if text_type is named_entity, e.g., 'PERSON', 'ORG')",
  "text": "string (original text as extracted or detected)",
  "language_tag": "string (BCP-47, e.g., 'cs', 'de')",
  "text_embedding": "vector (optional, e.g., 384-dim from multilingual-e5-small)",
  "embedding_model": "string (optional, e.g., 'multilingual-e5-small')",
  "embedding_model_version": "string (optional)",
  "content_hash": "string (for reproducibility)"
}
```

**Note**: Bounding box, page dimensions, OCR confidence, NER confidence, language confidence are in PostgreSQL `EVIDENCE` table as metadata JSON.

**Queries supported**:
- Full-text search: "Match text containing 'Jan Novak'"
- Language-filtered: "Text in Czech documents only"
- NER-filtered: "Person entities only"
- Vector similarity: "Semantically similar text passages"
- Hybrid: "Full-text + vector similarity with normalization"

---

## 3. Collection Relationships and Joins

Retrieval happens in two phases:

### 3.1 Candidate Generation (Search Layer)

1. **Face Collection**: Query with face embedding.
2. **Image Collection**: Query with image embedding.
3. **Name Collection**: Full-text query on person name.
4. **Text Region Collection**: Full-text + optional vector query on OCR/NER.

Each modality returns top-K candidates with their `evidence_id`, `source_uri`, and `page` coordinates.

## 4. Indexing and Incremental Reindex Strategy

## 5. Search Engine Implementation Notes

### 5.1 Weaviate

- Collections map to Weaviate classes.
- Vector fields use Weaviate's native vector type and distance metric (cosine for embeddings).
- BM25 is available via `where` filters and full-text search operators.
- Hybrid queries combine both modalities.

---

## 6. Query Patterns and Aggregation

### 6.1 Common Query Patterns

1. **Multi-modal search**: Execute queries on face, image, name, and text collections in parallel. Merge results by evidence.
2. **Filtered search**: Add filters on `library`, `document`, `page`, `language_tag`, `ner_label` before or after vector retrieval.
3. **Reranking**: Retrieve top-50 candidates from each modality; rerank by search profile weights in the application layer.

### 6.2 Result Aggregation

Results from multiple collections must be:

1. Deduplicated by `evidence_id`.
2. Grouped into evidence buckets (face, image, text).
3. Scored per signal (face similarity, image similarity, text relevance, etc.).
4. Reranked by search profile weights.

---

## 7. Data Ownership: What Lives Where

### 7.1 Search Indexes (Weaviate, Elasticsearch, etc.)

**Duplicate only**:
- `evidence_id`, `record_id` (stable foreign keys)
- `library`, `document`, `page`, `source_uri`, `source_provider` (provenance)
- `text`, `language_tag` (for full-text search)
- `face_embedding`, `image_embedding`, `text_embedding` (computed vectors)
- `embedding_model`, `embedding_model_version`, `content_hash` (model reproducibility)
- `name`, `aliases`, `display_name` (for name search)
- `ner_label`, `name_type`, `image_type` (for type-based filtering)

**Do NOT duplicate**:
- User IDs, annotator IDs, reviewer IDs
- Confidence scores (OCR confidence, NER confidence, embedding quality, language confidence)
- Spatial data (bounding box, keypoints, image dimensions, pixel coordinates)
- Business logic state (grounding state: proposed/accepted/rejected, annotation status)
- Audit trails (created_at, updated_at, asserted_at, asserted_by)
- Time-series data (ingest timestamps, index timestamps)
- Descriptions, portraits, mime types, refresh tokens, etc.

### 7.2 PostgreSQL (Source of Truth)

**Keep in PostgreSQL ONLY**:
- All business entities: `MASTER_ENTITY`, `GROUNDING_VERSION`, `ENTITY_PROPOSAL`, `ANNOTATION_INSTANCE`, `REVIEW_INSTANCE`
- All user and auth data: `USER`, `ROLE`, `USER_ROLE`, `AUTH_IDENTITY`
- All audit and decision data: `ACTION_LOG`, removal logs, review decisions
- Metadata: `EVIDENCE`, `GROUNDING_IDENTIFIER`, `GROUNDING_NAME`, `GROUNDING_PHOTO`, `GROUNDING_TEXT`
- Quality metrics: confidence scores, OCR/NER/embedding quality, language confidence
- Timestamps: ingested_at, indexed_at, reviewed_at, updated_at
- External references: portrait URLs, descriptions, authority sync metadata

### 7.3 Object Storage

- Raw scans and artifact payloads
- Ingest manifests and reproducibility artifacts
- Grounding evidence assets (photo crops, text snapshots) with stable local asset paths and content hashes

---

## 8. MVP Scope

For Phase 1, implement:

1. **Face Collection**: Embeddings, keypoints, bounding box, provenance. No confidence or audit timestamps.
2. **Image Collection**: Embeddings, image type, bounding box, provenance. No mime type or timestamps.
3. **Name Collection**: Original + normalized name, language tag, type. No confidence or ingest metadata.
4. **Text Region Collection**: Original + normalized text, language tag, NER label. No OCR confidence or timestamps.
5. **Authority Collection**: Display name, aliases, scheme, value, region/year filters. No description or sync timestamps.

