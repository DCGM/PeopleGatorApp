# People Gator Product Specification

## 1. Purpose

People Gator API is an backend for person-centric retrieval an person cluster annotation in historical document scans.

Main workflow:
1. Search returns ranked information clusters — groupings of face detections, name mentions, and authority evidence that speak to the same person.
2. User selects a cluster that seems promising, and creates and can start annotating it.
3. User can add or remove any member from the cluster, which first creates a new version branched and then createss change delta.
4. User can merge with other clusters, or split current cluster into multiple clusters.
5. User can search similar looking units (faces, names, authority evidence, paragraphs..) to find additional evidence and add to the cluster.
6. Commited cluster deltas are presented to reviewers.
7. Reviewer create single master record update from all annotation branches, that were created by annotators.
8. Reviewed clusters are promoted to grounded clusters.


Optional assigned tasks workflow:
1. An admin assigns select clusters for annotation by annotators.
2. Annotators work on their assigned clusters, which are visible in a dashboard.
3. Annotator can modify instance, create search clusters and add new evidence to the cluster.
4. They can merge with other clusters, or split current cluster into multiple clusters.
5. New clusters and review clusters are assigned to reviewers.
6. Reviewers create single master record update from all annotation branches, that were created by annotators.


## 2. Product Scope

### 2.1 In Scope

1. Search over prepared historical scan artifacts.
2. Person-centric retrieval (face, image, relevant page, relevant line, relevant region, named entity span).
3. Person cluster retrieval, creation, extension, merging, and versioning.
4. Grounding to locally imported authority sources (Wikidata, NKCR).
5. Annotation workflows, inter-annotator agreement tracking, and reviewer adjudication.
6. Authorization via OIDC scopes delegated to the identity provider. Audit trail via actor-stamped VERSION and DELTA records.
7. Data export.
8. New data ingest and indexing pipelines to keep up with new scans, new model versions, and new authority data dumps.

### 2.2 Out of Scope

1. Model training.
2. Data gathering and artifact preparation (OCR, face detection, NER, embedding generation).
3. Model inference (face detection, OCR, embeddings, NER), will use only API calls.
4. Live external authority queries at search time, everything is pre-ingested and indexed.
5. Downstream applications of the data (exhibition interfaces, research interfaces, etc.)


## 3. Design Principles

1. Cluster-first: search returns, annotation targets, and grounding outputs are all information clusters.
    - Search query is itself a set of typed signals (a name string, a free-text snippet, a face image). These signals are typed evidence items subject to content-hash deduplication. An ephemeral search query lives in the application cache and is never written to the relational DB unless the user explicitly saves it.
    - A **saved search** is the persisted form of a query. When a user saves a search, the application creates a CLUSTER with `cluster_role = saved_search` and an initial VERSION, with DELTA entries carrying the signal weights — one DELTA per evidence signal. No separate table exists; a saved search is a cluster type. It is promoted into an annotation target by creating a new VERSION with `cluster_role = mutable_cluster`.
    - Any person evidence that is grouped together is in a cluster.
    - Search results are polymorphic: results can be similarity-ranked clusters, individual evidence items of any modality, or both in the same response. Facet counts are returned inline with every response.
    - A system-default `SEARCH_PROFILE` is used when the caller does not specify one explicitly.
2. Typed canonical evidence: every atomic evidence item preserves typed metadata, and lineage information.
    - Typed metadata enables modality-specific search signals and faceting. 
    - Lineage tells about the source of data.
3. Explainable ranking: every cluster result includes per-modality signal contributions, extensive info enables per member analysis.
4. Human-in-the-loop user workflows: search
    - Search results are ranked clusters with per-modality signal contributions.
    - Search query itself is a weighted cluster of signals (face similarity, name similarity, authority link strength, etc.).
    - Per-modality weights and preferred embedding model per modality are defined by a `SEARCH_PROFILE` (see §6). Profiles are reusable, shareable, and customizable across users.
5. Human-in-the-loop user workflows: annotation
    - An annotation instance of a cluster gets created to be assigned to an annotator. It pins to a specific cluster version at assignment time.
    - Annotator can add or remove cluster members, which modifies the branched-off version.
    - Annotator can modify other clusters, upon which the cluster automatically branches off a new version, but the annotation instance remains pinned to the original version.
    - Annotator can submit the annotation instance.
    - Annotator can create a new `mutable_cluster` from scratch if they believe no existing cluster matches.
6. Human-in-the-loop user workflows: review
    - Branched-off versions from annotation are visible to reviewers.
    - Reviewer can choose what changes from the proposed cluster to accept, which creates a new version with those changes.
    - Reviewer decisions trigger new cluster version creation. Annotation instances are pinned to the original version, then become immutable.
    - Reviewer can promote a `review_cluster` to `grounded_cluster` if they believe the cluster is well supported, which creates a new version with that role.
7. Separation of concerns: this service ingests and reasons over artifacts; inference remains external.
    - This service does not perform OCR, face detection, NER, embedding generation, or authority linking. It only ingests the outputs of those processes as typed evidence.
    - This service does not train or serve any models. It only stores the model version used to generate each evidence item and uses that for staleness detection.
    - This service does not perform live authority lookups. It only ingests authority evidence from periodic syncs and links them to clusters, via exposed APIs for data access.
8. Identity-first accountability: every state change carries a traceable actor.
    - Every VERSION and every DELTA records a `actor_id` referencing a PRINCIPAL — either a human user or a named service agent.
    - Human users are identified via external OIDC authentication (e.g. Keycloak, Auth0). Their stable identity is the `(sub, iss)` claim pair from the ID token.
    - Service agents are autonomous processes identified by a conventional slug such as `system:kramerius-ingest` or `agent:face-detector-v2`. Slugs encode the agent category and name.
    - `actor_id` records the exact originator of every state change, enabling per-principal audit and replay.
9. Authorization via OIDC scopes: access control is delegated to the identity provider, not managed in the application database.
    - The IdP issues tokens carrying scopes that map directly to workflow roles: `people-gator:annotate`, `people-gator:review`, `people-gator:verify`, `people-gator:ingest`, `people-gator:admin`.
    - Each API route declares the required scope(s). The FastAPI dependency layer validates the token scope before the handler runs. No RBAC table is maintained in this service.
    - Coarse scope enforcement (annotator vs reviewer vs admin) is handled at route level. Fine-grained resource enforcement (can this annotator write to this cluster?) is handled via TASK assignment — an annotator may only write DELTAs against a version referenced by a TASK assigned to them.

## 4. Data Model

### 4.0 IDs

All identifiers are exclusively represented as **UUID v6**. 
Meaning it already contains a time component and is k-sortable, which is useful for efficient versioning and lineage tracking. 
The UUIDv6 has the following 128bit structure:
- `time_high` (bits 0-31)
- `time_mid` (bits 32-47)
- `ver` (bits 48-51)
- `time_low` (bits 52-63)
- `var` (bits 64-65)
- `clock_seq` (bits 66-79)
- `node` (bits 80-127)

Sorting by UUIDv6 is effectively sorting by creation time as the top 64bits (minus the version bits) represent the timestamp.
The timestamp is a Gregorian Epoch timestamp.

#### Generation strategy

UUIDs are generated by `new_uuid6()` in `db/models/base.py` using the `uuid6` library. Two process-scoped values are initialised once at startup and reused for the lifetime of the process:

- **`node`** — a random 48-bit value, fixed per process via `@lru_cache`. Replaces the MAC-address node of the original UUIDv1 spec, ensuring uniqueness across distributed instances without coordination or hardware dependency.
- **`clock_seq`** — a 14-bit counter, also fixed per process via `@lru_cache`. It is seeded from a random UUIDv6 draw and then incremented monotonically (`mod 0x4000`) on each call. This prevents collisions when multiple UUIDs are generated within the same timestamp tick.

Both values are stable for the process lifetime, so clock sequence roll-over and node identity are consistent within a single deployment instance.

### 4.1 SOURCE_SCHEMA

Defines how to resolve the storage and access paths for a family of sources. Every SOURCE references one SOURCE_SCHEMA, which tells the system how to construct local file paths, remote URLs, or IIIF endpoints from a source's provider identifier. Centralising this logic here means both the local archive copy and the remote canonical URL are derived from the same SOURCE record — there is no duplication on EVIDENCE itself.

Fields: `schema_name`, `resolver_type`, `resolver_config`.

- `schema_name`: human-readable label, e.g. `image-upload`, `kramerius-iiif`, `wikimedia-image`, `nkcr-authority`. Must be globally unique.
- `resolver_type`: one of `db-source-table-row`, `s3-image`, `http-image`, `fsspec-image`, `fsspec-pagexml`, `s3-table`.
- `resolver_config`: typed nested JSONB whose structure is discriminated by `resolver_type`. Each `resolver_type` defines an explicit schema (enforced by a Pydantic discriminated union at registration time) specifying exactly which template keys are permitted and what format their values must take. No arbitrary keys are allowed — the model rejects any `resolver_config` that contains keys not in the allow-list for that `resolver_type`. A GIN index is defined on `resolver_config` to support containment queries for config-based faceting and admin lookups.

**GIN index trade-off**: SOURCE_SCHEMA is a low-write, high-read table (schemas are registered once at deployment). GIN write amplification is negligible here. For high-volume write tables (e.g. DERIVED_EVIDENCE), partial GIN indexes scoped to specific `evidence_type` values are used instead to bound the index maintenance cost (see §4.4.1).

Per-resolver-type `resolver_config` schemas and allowed placeholder keys:

| `resolver_type` | Allowed placeholder keys | Example `resolver_config` |
|---|---|---|
| `db-source-table-row` | `principal_id` | `{"source_template": "{principal_id}"}` |
| `s3-image` | `principal_id`, `file_id` | `{"bucket_template": "peoplegator-upload", "key_template": "{principal_id}/{file_id}.jpg"}` |
| `http-image` | `file_name` | `{"base_url_template": "https://commons.wikimedia.org/", "path_template": "wiki/Special:FilePath/{file_name}"}` |
| `fsspec-pagexml` | `page_id`, `library`, `document_id` | `{"path_template": "zip://{page_id}.xml::file:///mnt/data/{library}/{document_id}.page_xml.zip"}` |
| `fsspec-image` | `library`, `document_id`, `page_id` | `{"path_template": "file:///mnt/data/{library}/{document_id}.images/{page_id}.jpg"}` |
| `s3-table` | `text_type` | `{"bucket_template": "peoplegator-ingest", "key_template": "nlcr_aut/nlcr_aut__{text_type}.csv"}` |

Placeholder values sourced from `SOURCE.metadata` are validated against a per-key format rule before interpolation (e.g. `principal_id` must be a valid UUIDv6 string, `file_id` must be alphanumeric). Interpolation is performed only after validation passes. This closes the path-traversal and SSRF vectors that would otherwise exist for `s3-image` and `http-image` resolver types.

Resolver then does the following for a SOURCE where `schema_name` references this `SOURCE_SCHEMA`:
1. Look up the `resolver_config` for the `schema_name` and validate its structure against the `resolver_type` schema.
2. Take `SOURCE.metadata` and extract values for each allowed placeholder key. Validate each value against its per-key format rule.
3. Interpolate the validated placeholder values into the `resolver_config` templates.
4. Construct the final URL or file path according to the `resolver_type` logic.

### 4.2 SOURCE

A specific document, scan, or artifact from which one or more EVIDENCEs were derived. SOURCE normalises provenance — an EVIDENCE belongs to exactly one SOURCE, and the SOURCE belongs to one SOURCE_SCHEMA that knows how to resolve its storage paths.

Fields: `source_id`, `source`, `source_schema_name`, `provider`, `metadata`, `content_hash`, `created_by`.
- `source_id`: UUIDv6 primary key.
- `source`: opaque string identifier for the original source, e.g. a filename. Parsable via `source_schema_name`.
- `source_schema_name`: FK → SOURCE_SCHEMA — determines how this original source can be resolved.
- `provider`: enum string — coarse provenance identifier. One of `kramerius`, `nkcr`, `wikimedia`, `local`. Set at ingest time by the SERVICE_AGENT creating the source record. Used for vector store faceting (see §5.2.2).
- `content_hash`: hash of ingested content for deduplication and staleness detection, e.g. hash of the original image bytes for a scanned document, or hash of the authority record JSON for an imported authority entity.
- `created_by`: FK → `SERVICE_AGENT.principal_id` or `USER.principal_id` — the service agent or user that ingested this source.

This is intentionally flexible to accommodate the wide variety of source types and metadata that may be relevant for different use cases. The exact structure of this JSONB is not enforced at the database level but is expected to conform to the requirements of the associated SOURCE_SCHEMA's resolver logic.

### 4.3 METADATA_SCHEMA

Defines the versioned structure of the `metadata` JSONB payload for each evidence type. Every EVIDENCE references one METADATA_SCHEMA, which identifies the contract that `metadata` conforms to and optionally carries a machine-readable JSON Schema for runtime validation. Centralising schema registration here means schema evolution is tracked in the database, not embedded as opaque string constants in application code.

Fields: `evidence_type`, `schema_version`, `json_schema`, `description`.

- `evidence_type`: the EVIDENCE type this schema applies to. Can be `face_detection`, `named_entity`, `text_region`, `grounded_name`, `grounded_description`, or `authority_identifier`.
- `schema_version`: version string for the schema, e.g. `v1`, `v2`.
- `json_schema`: optional JSONB — machine-readable JSON Schema (draft-07 compatible) for validating the `metadata` payload at ingest time. Null for built-in schemas whose structure is described in §4.4.2.
- `description`: optional free-text description of the schema's purpose and contents.

### 4.4 EVIDENCE

Evidence is split into a **base table** and two **specialised child tables** that cover the two structurally distinct evidence families. All DELTA and MEMBERSHIP FKs reference the base `EVIDENCE` table so membership queries never need to know which family an item belongs to.

#### 4.4.0 EVIDENCE (base)

Shared identity and provenance fields. Every DERIVED_EVIDENCE and AUTHORITY_EVIDENCE row has a corresponding EVIDENCE row with the same `evidence_id`.

Required fields: `evidence_id`, `evidence_version_id`, `evidence_type`, `schema_version`, `source_id`, `source_path`, `content_hash`.

- `evidence_id`: stable UUIDv6 identifier for this evidence item across all versions.
- `evidence_version_id`: UUIDv6, incremented on each revision. A new `evidence_version_id` is created only when a human user revises the evidence metadata (see §4.4.3). Re-running inference over the same source produces a new EVIDENCE row entirely, not a new version of an existing one.
- `evidence_type`: discriminator — one of `face_detection`, `named_entity`, `text_region` (→ DERIVED_EVIDENCE) or `grounded_name`, `grounded_description`, `authority_identifier` (→ AUTHORITY_EVIDENCE).
- `schema_version`: together with `evidence_type`, forms the FK → METADATA_SCHEMA.
- `source_id`: FK → SOURCE — the document or artifact this evidence was derived from.
- `source_path`: string — sub-path or key within the SOURCE identifying the specific artifact (e.g. a page ID within a document zip, or a crop region URI). Null when the evidence covers the entire source document. Opaque to the DB; interpreted by the SOURCE_SCHEMA resolver.
- `content_hash`: hash of the evidence payload for deduplication and staleness detection.

A **partial GIN index** is defined per `evidence_type` on the child table's `produced_metadata` column to support modality-specific JSONB field access and faceting without a full table scan.

#### 4.4.1 DERIVED_EVIDENCE

Extends EVIDENCE for ML-model-produced detections: `face_detection`, `named_entity`, and `text_region`.

Additional fields: `producer_id`, `produced_metadata`, `revisor_id`, `revised_metadata`.

- `producer_id`: non-null FK → `MODEL_AGENT.principal_id` — the model that produced this detection. Because MODEL_AGENT is a proper subtype table (see §4.12.3), this FK is DB-enforced at the table level; no CHECK constraint or trigger required.
- `produced_metadata`: JSONB — typed detection payload structured per the METADATA_SCHEMA. Partial GIN index per `evidence_type`.
- `revisor_id`: nullable FK → `USER.principal_id` — the human who last revised the metadata. Null if never revised. DB-enforced at the table level.
- `revised_metadata`: nullable JSONB — human correction of `produced_metadata`. Same schema. When present, supersedes `produced_metadata` for display; `produced_metadata` is always retained for audit.

#### 4.4.2 AUTHORITY_EVIDENCE

Extends EVIDENCE for authority-sourced records: `grounded_name`, `grounded_description`, and `authority_identifier`. These are ingested from periodic authority syncs run by a SERVICE_AGENT, not produced by an ML model.

Additional fields: `producer_id`, `metadata`.

- `producer_id`: non-null FK → `SERVICE_AGENT.principal_id` — the ingestion pipeline that produced this record. DB-enforced at the table level.
- `metadata`: JSONB — typed authority payload structured per the METADATA_SCHEMA. Partial GIN index per `evidence_type`. No `revised_metadata` — authority evidence is replaced wholesale on re-sync by creating a new EVIDENCE version.


#### 4.4.3 EVIDENCE versioning

A new `evidence_version_id` is created only when a human user revises metadata (sets `revised_metadata` on DERIVED_EVIDENCE, or re-syncs an AUTHORITY_EVIDENCE row). Running inference again over the same source produces a **new EVIDENCE row** with a new `evidence_id` — it does not increment the version of the existing row. This keeps the lineage of model-produced detections independent from human corrections.

DELTA rows pin to a specific `(evidence_id, evidence_version_id)`. They are immutable — they continue to reference the pinned version even when newer versions of that evidence exist. MEMBERSHIP reflects whichever version was pinned when the delta was written.

#### 4.4.4 Shared sub-schemas

These sub-schemas are reused across both DERIVED_EVIDENCE and AUTHORITY_EVIDENCE metadata payloads.

**Point** — a single spatial coordinate on an image, normalised to [0, 1] relative to image dimensions:
| Field | Type | Description |
|---|---|---|
| `x` | float [0,1] | Normalised x coordinate |
| `y` | float [0,1] | Normalised y coordinate |

**Rectangle** — spatial extent of a detection on an image, coordinates normalised to [0, 1] relative to image dimensions:
| Field | Type | Description |
|---|---|---|
| `min` | **Point** | Top-left corner of the rectangle |
| `max` | **Point** | Bottom-right corner of the rectangle |

**Polygon** — a closed shape defined by an ordered list of vertices, normalised to [0, 1] relative to image dimensions:
| Field | Type | Description |
|---|---|---|
| `vertices` | list[**Point**] | Ordered list of vertices defining the polygon |

**PolyLine** — a series of connected line segments, defined by an ordered list of points:
| Field | Type | Description |
|---|---|---|
| `points` | list[**Point**] | Ordered list of points defining the polyline |

**TextSpan** — a contiguous span of text within a larger body, defined by character offsets:
| Field | Type | Description |
|---|---|---|
| `start` | int | Starting character offset (inclusive) |
| `end` | int | Ending character offset (exclusive) |

**Image** — a information about image that is associated with an evidence, mainly defining image format and dimensions.
| Field | Type | Description |
|---|---|---|
| `image_format` | string | `jpeg`, `png`, `tiff` |
| `width_px` | int | Image width in pixels |
| `height_px` | int | Image height in pixels |

**Keypoint** — a single spatially localised facial or structural landmark:
| Field | Type | Description |
|---|---|---|
| `point` | **Point** | Normalised coordinate of the keypoint |
| `label` | string | Semantic label, e.g. `left_eye`, `right_eye`, `nose_tip`, `left_mouth`, `right_mouth` |

**BoundingBox** — a rectangular detection area, defined by top-left and bottom-right coordinates normalised to [0, 1] relative to the source image dimensions:
| Field | Type | Description |
|---|---|---|
| `box` | **Rectangle** | Normalised bounding box coordinates |
| `label` | string | Semantic label for the detected region, e.g. `face`, `paragraph`, `named_entity_span` |

**PhysicalTextSpan** — a text span with physical layout information, defined by character offsets and an optional baseline for layout context:
| Field | Type | Description |
|---|---|---|
| `span` | **TextSpan** | Character offsets of the text span within the source text |
| `baseline` | list[**Point**] | Optional baseline points for layout context, normalised to [0, 1] relative to the source image dimensions |
| `text` | string | OCR'd text content |
| `normalized_text` | string | Normalised form of the text |
| `label` | string | Semantic label for the text span, e.g. `person_name` |

**PhysicalTextRegion** — a text region with physical layout information, defined by a bounding box and an optional baseline for layout context:
| Field | Type | Description |
|---|---|---|
| `area` | **Polygon** | Normalised bounding box coordinates of the text region |
| `baseline` | list[**Point**] | Optional baseline points for layout context, normalised to [0, 1] relative to the source image dimensions |
| `text` | string | OCR'd text content |
| `normalized_text` | string | Normalised form of the text |
| `label` | string | Semantic label for the text region, e.g. `paragraph` |

#### 4.4.5 Metadata schemas by evidence type

The `(evidence_type, schema_version)` FK links each EVIDENCE to a METADATA_SCHEMA row (see §4.3). Each type below defines the canonical structure of the JSONB payload for that evidence type. Adding a new schema version creates a new METADATA_SCHEMA row; old EVIDENCE rows remain valid by retaining their original FK.

##### `face_detection` — schema_version `v1`

| Field | Type | Required | Description |
|---|---|---|---|
| `bounding_box` | BoundingBox | yes | Detection area on the source image |
| `keypoints` | list[Keypoint] | no | Facial landmarks when available from the detector |
| `image` | Image | yes | Image format and dimensions for this detection |
| `confidence` | float [0,1] | yes | Model confidence score for this detection |

The `producer_id` links the detection to the specific MODEL_AGENT principal that produced it, enabling staleness detection when models are updated.

##### `named_entity` — schema_version `v1`

| Field | Type | Required | Description |
|---|---|---|---|
| `span` | PhysicalTextSpan | yes | Detected text span with layout information |
| `confidence` | float [0,1] | yes | Model confidence score for this detection |

The `producer_id` links the detection to the specific MODEL_AGENT principal that produced it, enabling staleness detection when models are updated.

##### `text_region` — schema_version `v1`

| Field | Type | Required | Description |
|---|---|---|---|
| `area` | PhysicalTextRegion | yes | Detected text region with layout information |
| `confidence` | float [0,1] | yes | Model confidence score for this detection |

The `producer_id` links the detection to the specific MODEL_AGENT principal that produced it, enabling staleness detection when models are updated.

##### `grounded_name` — schema_version `v1`

A name form belonging to an authority entity. The entity itself is captured by `EVIDENCE.source_id`, which references the authority SOURCE — there is no explicit authority FK inside the metadata.

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes | Name form as recorded in the authority source |
| `type` | string | yes | `preferred` or `alias` — role of this name form in the authority |
| `language` | string (BCP 47) | no | Language of the name form, if applicable |

##### `grounded_description` — schema_version `v1`

A textual description belonging to an authority entity. The entity is captured by `EVIDENCE.source_id` as above.

| Field | Type | Required | Description |
|---|---|---|---|
| `description` | string | yes | Description text as recorded in the authority source |
| `language` | string (BCP 47) | no | Language of the description, if applicable |


##### `authority_identifier` — schema_version `v1`

An identifier for an authority entity, such as a Wikidata QID or an NKCR ID. The entity is captured by `EVIDENCE.source_id` as above.

| Field | Type | Required | Description |
|---|---|---|---|
| `identifier` | string | yes | The authority identifier, e.g. `Q42` for Wikidata or `NKCR12345` for NKCR |
| `authority_type` | string | yes | The type of authority, e.g. `wikidata` or `nkcr` |

### 4.5 CLUSTER

Stable identity for a cluster across its version history.

Fields: `cluster_id`, `head_version_id`.

`cluster_role` is not stored on CLUSTER. It is computed on read from `VERSION.cluster_role` via `head_version_id`. This eliminates the dual-write invariant that previously required application-level enforcement.

`cluster_role` values (defined on VERSION, readable via head join):

| Role | Created by |
|---|---|
| `saved_search` | A persisted search query saved by a user; promotes to `mutable_cluster` via a new VERSION |
| `mutable_cluster` | A cluster that is proposed automatically or by an annotator |
| `review_cluster` | A cluster that is under review by a human annotator |
| `grounded_cluster` | Reviewer promotion of a `review_cluster` |
| `authority_cluster` | Authority sync (Wikidata, NKCR import) |
| `automatic_cluster` | Automatically generated cluster without human intervention |

`head_version_id` points to the current logical head of the cluster's main chain. It is updated atomically in the same transaction as the operation that advances it. Rules for when `head_version_id` is updated:

| Operation | Head update rule |
|---|---|
| `empty` | Set to the initial `target_version_id`. |
| `stage` | Advance to `target_version_id` (current head must be the `source_version_id`). |
| `union` or `intersection` (this cluster is the target) | Set to `target_version_id`. Current head must be one of the `source_version_id` values. |
| `branch` | **Not updated.** Head stays on the main-chain version the branch diverged from. |
| `split` (this cluster is a new target) | Set to the `target_version_id` allocated for this new cluster. |

### 4.6 VERSION

One immutable snapshot of cluster membership state. Created by copy-on-write on any membership change.

Fields: `version_id`, `cluster_id`, `cluster_role`, `actor_id`.

- `actor_id`: FK to PRINCIPAL — the user or service agent that created this version.

### 4.7 OPERATION
Represents a directed edge between versions of the same cluster, or between versions of independent logical clusters.

Fields: `operation_id`, `source_cluster_id`, `source_version_id`, `target_cluster_id`, `target_version_id`, `operation_type`.

- `operation_id`: UUIDv6 primary key shared across all rows that belong to the same logical operation. Multi-row operations (`union`, `intersection`, `split`) carry the same `operation_id` on every row. This provides an atomic FK target for audit, rollback, and completeness checks — a logical operation is complete only when all expected rows sharing an `operation_id` are present.

The operation_type field can contain following values:
| Operation Type | Description | Enforced Constraints |
|---|---|---|
| `empty` | The initial version of a cluster, it has no prior versions, declared cluster as empty. | `source_cluster_id=cluster_id`, `target_cluster_id=cluster_id`, `source_version_id=NULL`, `target_version_id=version_id`. No prior operation entry exists for the `cluster_id`. |
| `stage` | A new version is created by advancing the previous version. | `source_cluster_id == target_cluster_id` |
| `branch` | A new parallel version is created from a source version. | `source_cluster_id == target_cluster_id` |
| `union` | Two or more parallel versions or clusters are merged into one. The resulting membership is the **union of all positive (add) deltas** from all source version memberships. Where the same evidence item has an `add` delta in one source and a `remove` delta in another, the `add` wins — the union operation is additive by definition. | single `target_version_id`, `target_cluster_id`, multiple `source_version_id` rows and `source_cluster_id` values, all sharing one `operation_id` |
| `intersection` | Two or more parallel versions or clusters are merged into one, keeping only items present in all source memberships. An evidence item is included in the result only if it has a resolved positive membership in **every** source version. Items that are explicitly removed in all source versions are also removed in the result. | single `target_version_id`, `target_cluster_id`, multiple `source_version_id` rows and `source_cluster_id` values, all sharing one `operation_id` |
| `split` | One cluster is split into two or more clusters. | single `source_version_id`, multiple `target_version_id` rows, all sharing one `operation_id` |

### 4.8 DELTA

Associates an EVIDENCE applied as a delta to a specific CLUSTER VERSION, representing the addition or removal of that evidence from the cluster in that version. This is the core table for determining cluster membership at any given version.

Fields: `delta_id`, `cluster_id`, `version_id`, `evidence_id`, `evidence_version_id`, `delta_type` (`add` or `remove`), `weight`, `actor_id`.

Explanation of fields:
- `cluster_id`: enforced via a composite FK `FOREIGN KEY (version_id, cluster_id) REFERENCES VERSION (version_id, cluster_id)`. VERSION carries a unique index on `(version_id, cluster_id)`. This means the DB enforces that `cluster_id` always matches the cluster of the referenced version — no application-level invariant required.
- `delta_type`: Indicates whether the evidence is being added to or removed from the `version_id` `cluster_id` state.
- `weight`: A numerical value representing the strength of the association between the evidence and the cluster in this commit, which can be used for ranking and confidence scoring.
- `actor_id`: FK to PRINCIPAL — the user, service agent, or model agent that authored this specific evidence addition or removal.

Here enforced constraints for the DELTA:
1. `evidence_id` and `evidence_version_id` must exist in the EVIDENCE table.
2. The composite `(version_id, cluster_id)` FK into VERSION is enforced at DB level.
3. There is no entry in the OPERATION table for the `cluster_id` and `version_id` as `source_cluster_id` and `source_version_id`. No derived versions have been created from this version yet.


#### 4.8.1 Algorithm to resolve membership for a given `cluster_id` and `version_id`:
1. Start with an empty set of member evidence.
2. From `OPERATION`, start with the specified `cluster_id` and `version_id`, and perform a full DAG walk backwards through all ancestor operation entries to the root version, collecting all `(cluster_id, version_id)` pairs. Follow ALL ancestor paths — including those via `union`, `intersection`, and `split` entries that cross cluster boundaries. Do not prune at the first path to root.
3. For each collected `cluster_id` and `version_id`, query the DELTA table for all deltas associated with that version.
4. Sort the collected deltas globally by their `delta_id` ascending. Because `delta_id` is a UUIDv6, this is equivalent to creation-time order across all ancestor versions.
5. Sequentially apply each delta to the set of member evidence, adding or removing evidence based on the `delta_type` and updating the `weight` accordingly.
6. After processing all deltas, the resulting set of member evidence represents the cluster membership for the specified `cluster_id` and `version_id`.

#### 4.8.2 Algorithm to resolve pending (unsealed) changes for a given `cluster_id` and `version_id`:
1. From `DELTA` table, query for any deltas associated with the specified `cluster_id` and `version_id`.
2. Sort the deltas by their `delta_id` ascending to ensure they are processed in the order they were created.
3. Reduce the deltas if same `EVIDENCE` has been added and removed multiple times, keeping only the latest delta for each `EVIDENCE`.
4. The resulting set of deltas represents the pending diff on the current working version for the specified `cluster_id` and `version_id`.

#### 4.8.3 Note on head_version_id

`head_version_id` on CLUSTER always reflects the current main-chain head. There are no `head_constraints` — the semantics are fixed by the operation rules in §4.5. Callers that want to inspect a non-head version (e.g. a branch) reference that `version_id` directly. There is no mode where membership is the union across all leaf versions; that computation must be done explicitly by the caller.


### 4.9 TASK

A unit of work assigned to a PRINCIPAL, directing them to act on a specific cluster version. Tasks are the primary mechanism for driving the annotation and review workflow.

Fields: `task_id`, `cluster_id`, `pinned_version_id`, `head_version_id`, `assignee_id`, `task_role`, `status`, `created_by`, `created_at`, `updated_at`.

- `cluster_id`: FK → CLUSTER — the cluster this task concerns.
- `pinned_version_id`: FK → VERSION — **immutable**. The version that existed when the task was created. Never changes after task creation. Provides the stable traceability anchor for `union` and `intersection` operations that need to know the shared ancestor.
- `head_version_id`: FK → VERSION — the current working head of this task. Starts equal to `pinned_version_id`. Advances each time a new version is created under this task (e.g. the annotator adds or removes evidence, which creates a new VERSION via a `stage` operation). Always points to the local head of the task's branch. If the referenced version becomes sealed (an outgoing OPERATION exists for it), the task must create a new `branch` from that version before writing further DELTAs.
- `assignee_id`: FK → PRINCIPAL — the user assigned to perform the task.
- `created_by`: FK → PRINCIPAL — the user or service agent that created this task.
- `task_role`: specifies what the assignee is expected to do.
- `status`: lifecycle state of the task.

`task_role` values:

| Role | Description |
|---|---|
| `annotate` | Assignee should review and extend or correct the cluster membership |
| `review` | Assignee should adjudicate annotation branches and produce a consolidated version |
| `verify` | Assignee should confirm the cluster grounding against authority records |

#### 4.9.1 Task status state machine

| Status | Description |
|---|---|
| `pending` | Task created, not yet acted on by the assignee |
| `submitted` | Annotator has submitted their working version for review |
| `review` | A reviewer has picked up the submitted task and is adjudicating it |
| `closed` | Task completed or cancelled; no further action expected |

Allowed transitions and authorised actors:

| From | To | Authorised actor | Side effects |
|---|---|---|---|
| `pending` | `submitted` | Task `assignee_id` (requires `people-gator:annotate` scope) | None. `head_version_id` at submission time becomes the version handed to the reviewer. |
| `submitted` | `review` | Any principal with `people-gator:review` scope | None. |
| `review` | `closed` | The principal who moved to `review` (reviewer) | Reviewer may create a new VERSION via `union` or `intersection` of the submitted branch and the cluster main chain before closing. |
| `pending` | `closed` | Task `created_by` or any `people-gator:admin` scope | Cancellation. No version changes required. |
| `submitted` | `pending` | Task `assignee_id` | Annotator retracts submission. `head_version_id` is unchanged. |

No other transitions are permitted.

#### 4.9.2 Version immutability and task writes

A version is **sealed** once it appears as `source_version_id` in any OPERATION row. A sealed version cannot receive new DELTAs. If an external operation (e.g. a merge initiated by a reviewer on a parallel task) seals the version that `head_version_id` points to, the assignee must create a `branch` from that version before writing further DELTAs. The new branch version becomes the new `head_version_id`. The application must detect this condition before any DELTA write and surface it to the user.


### 4.10 MEMBERSHIP
Represents the current materialized state of cluster membership for each cluster, derived from the DELTA table.

Fields: `cluster_id`, `evidence_id`, `evidence_version_id`, `weight`, `as_of_version_id`.

`as_of_version_id` records which version this materialized state was derived from, allowing staleness detection. Its value is `CLUSTER.head_version_id` at the time of the last update.

MEMBERSHIP is updated **asynchronously** after a new VERSION is created (via `stage`, `union`, `intersection`, or `split`). It is not updated in the same transaction as the DELTA write. The update is triggered by a background job enqueued when a new OPERATION row seals a version. For the current working (unsealed) version — the version that has no outgoing OPERATION entry yet — pending deltas are read live from the DELTA table and combined with the MEMBERSHIP rows of the most recently sealed ancestor version. This means:
- Read queries for a sealed version: served from MEMBERSHIP directly.
- Read queries for the current working version: MEMBERSHIP of the sealed parent + live DELTA query for unsealed deltas.

MEMBERSHIP reflects sealed versions only. The background job must complete before a newly-created version is queryable via MEMBERSHIP.

### 4.11 Saved searches as clusters

There is no separate SAVED_SEARCH table. A saved search is represented as a CLUSTER with `cluster_role = saved_search` (see §4.5). When a user saves a search query, the application creates:

1. A CLUSTER row.
2. An initial VERSION with `cluster_role = saved_search` and `actor_id` set to the saving user.
3. One DELTA per evidence signal, carrying `evidence_id`, `evidence_version_id`, `delta_type = add`, and `weight` from the signal weight.

The SEARCH_PROFILE used when saving the query is not stored on the cluster itself — it is associated at query time via the caller's profile selection.

Promotion to an annotation target creates a new VERSION via a `stage` operation with `cluster_role = mutable_cluster`. The original `saved_search` VERSION is retained as the version history root.

### 4.12 PRINCIPAL

Polymorphic supertype table for all actors that can modify the system. Every VERSION and every DELTA carries an `actor_id` FK to `PRINCIPAL.principal_id`, giving a complete, type-agnostic audit trail across users, service agents, and model agents.

Type-safe evidence FKs do **not** point here — they point directly to the appropriate subtype table (`MODEL_AGENT`, `SERVICE_AGENT`, or `USER`), whose PK is the same value as `PRINCIPAL.principal_id`. This is class table inheritance: the subtype rows share the same PK value and are always created together with their PRINCIPAL row. A FK to a subtype table is implicitly type-restricted without any CHECK constraint or trigger.

`principal_type` values:

| Type | FK target for evidence fields | Description |
|---|---|---|
| `user` | `USER.principal_id` | A human authenticated via an external OIDC provider |
| `service_agent` | `SERVICE_AGENT.principal_id` | A named ingestion or automation pipeline |
| `model_agent` | `MODEL_AGENT.principal_id` | A registered ML model agent that produces DERIVED_EVIDENCE |

Fields: `principal_id`, `principal_type`, `display_name`, `is_active`.

`PRINCIPAL.principal_type` is the polymorphic discriminator. Type-specific fields are stored in the joined `USER`, `SERVICE_AGENT`, or `MODEL_AGENT` subtype table. The PRINCIPAL row and its subtype row are always inserted together within the same transaction.

### 4.13 SOURCE_PROCESSING

Tracks the processing state of a MODEL_AGENT being applied to a SOURCE to produce DERIVED_EVIDENCE.

Fields: `source_id`, `producer_id`, `processing_status`, `started_at`, `completed_at`, `error_message`.

- `source_id`: FK → SOURCE (part of composite PK).
- `producer_id`: FK → `MODEL_AGENT.principal_id` (part of composite PK) — DB-enforced to model agents only via the subtype table FK.
- `processing_status`: enum — lifecycle state of this processing job.
- `started_at`: nullable `timestamptz` — set when the job transitions to `in_progress`.
- `completed_at`: nullable `timestamptz` — set when the job reaches `complete` or `failed`.
- `error_message`: nullable text — populated on `failed` with the error detail.

`processing_status` values:

| Value | Description |
|---|---|
| `queued` | Row exists; processing has not yet been triggered |
| `in_progress` | Processing has been triggered and is actively running |
| `complete` | All resulting DERIVED_EVIDENCEs have been ingested successfully |
| `failed` | Processing encountered an error; see `error_message` |

`(source_id, producer_id)` is the composite primary key — one row per pair. A source with no row for a given `producer_id` has never been queued. A source with `processing_status = queued` has been registered but the job has not yet started. This allows idempotent retry logic to distinguish "never queued", "in flight", "done", and "stuck/failed" states.

Evidence-level lineage is available via `DERIVED_EVIDENCE.producer_id`, which carries the FK to the MODEL_AGENT that produced it. Authority evidence lineage is available via `AUTHORITY_EVIDENCE.producer_id`, which carries the FK to the SERVICE_AGENT that ingested it.

#### 4.12.1 USER

A human principal authenticated through an external OpenID Connect (OIDC) identity provider such as Keycloak or Auth0. The user record is created or refreshed on first token verification.

Fields (extends PRINCIPAL): `principal_id`, `external_subject`, `external_issuer`, `email`.

- `external_subject`: the OIDC `sub` claim — stable, provider-scoped user identifier.
- `external_issuer`: the OIDC `iss` claim — identifies the identity provider.
- Together `(external_subject, external_issuer)` forms a globally unique identity key across multiple IdPs.
- `email` is optional; sourced from the OIDC `email` claim when present.

#### 4.12.2 SERVICE_AGENT

A named autonomous process that drives ingestion and synchronisation pipelines but does **not** run ML inference. ML model agents are registered as MODEL_AGENT (§4.12.3) instead. SERVICE_AGENTs are the producers of AUTHORITY_EVIDENCE (see §4.4.2) and are responsible for creating SOURCE records during ingest. They are pre-registered and identified by a unique `agent_slug` following the convention `<category>:<name>`, for example:

| Slug | Category | Description |
|---|---|---|
| `system:kramerius-ingest` | `system` | Kramerius document and page-XML ingestion pipeline |
| `pipeline:authority-sync-wikidata` | `pipeline` | Periodic Wikidata authority record synchronisation |
| `pipeline:authority-sync-nkcr` | `pipeline` | Periodic NKCR authority record synchronisation |
| `system:local-ingest` | `system` | Local file ingest pipeline for manually staged artifacts |

Fields (extends PRINCIPAL): `principal_id`, `agent_slug`, `description`.

- `agent_slug`: unique human-readable identifier, format `<category>:<name>`.
- `description`: optional free-text description of the agent's purpose.

#### 4.12.3 MODEL_AGENT

A registered ML model agent principal. The distinction from a static model artifact is intentional: the underlying model weights are immutable, but a MODEL_AGENT is the registered actor that operates the model — it has identity, can be assigned accountability, and can autonomously produce EVIDENCE or author VERSION and DELTA records. Every model that produces EVIDENCE must be pre-registered as a MODEL_AGENT. Because MODEL_AGENT extends PRINCIPAL, it can appear as the `producer_id` on EVIDENCE records and as the `actor_id` on VERSION or DELTA records.

Fields (extends PRINCIPAL): `principal_id`, `evidence_type`, `role`, `model_slug`, `model_version`, `registry_source`, `registry_uri`, `is_active`.

- `evidence_type`: the EVIDENCE type this agent produces, e.g. `face_detection`, `named_entity`.

- `role`: the vector slot role prefix, e.g. `face`, `text`, `layout` — determines the vector slot name prefix in the vector store (see §5.2.3).
- `model_slug`: unique human-readable identifier used as the suffix in the vector slot name (`<role>:<model_slug>`), e.g. `arcface-r100-v2`. Must be globally unique within a `(evidence_type, role)` pair.
- `model_version`: semantic version string identifying the underlying model artifact, used for staleness detection.
- `registry_source`: the model registry that hosts this model artifact, e.g. `mlflow`, `huggingface`, `local`.
- `registry_uri`: the fully-qualified URI identifying this specific model version in its registry. Together with `registry_source` forms the canonical lineage reference stored on every vector document that carries this agent's slot.
- `is_active`: whether this agent is currently used for encoding newly ingested evidence. Multiple agents for the same `evidence_type` may be active simultaneously during a rollout.

Agents that are no longer active are retained for querying existing documents that carry their vector slot — they are never deleted as long as any EVIDENCE records reference them.

---

## 5. Vector Data Model

The vector store is a document store. Each document is in a strict **1:1 relationship with one EVIDENCE version** — one document per `(evidence_id, evidence_version_id)` pair. Because an EVIDENCE has exactly one `evidence_type`, each document represents a single modality. Multiple vectors can exist within the same document, but only as the result of running different embedding models or pipelines over the same content — not because the document spans multiple modalities.

### 5.1 Design Goals

1. **One document per EVIDENCE version** — `(evidence_id, evidence_version_id)` is the document key. No document aggregates evidence across multiple EVIDENCEs.
2. **Single modality per document** — the `evidence_type` of the EVIDENCE fully determines the modality of every vector in the document. Cross-modal queries join across documents at query time.
3. **Multiple vectors for the same modality** — a document may carry several named vector slots for its modality, each produced by a different embedding model or pipeline version. This allows parallel staleness-aware retrieval and A/B comparison of models without rewriting history.
4. **Derived faceting metadata** — faceting attributes are derived from the EVIDENCE's SOURCE and SOURCE_SCHEMA at ingest time and stored inline on the document. This allows the vector DB to evaluate filters without a round-trip to the relational store.
5. **Modality-specific searchable fields** — some evidence types store additional normalised text fields (e.g. `normalized_text` on `named_entity`) to enable full-text search directly in the vector DB alongside vector similarity.
6. **Relational anchor** — every document carries `evidence_id` and `evidence_version_id` as the stable FK pair back to the EVIDENCE table. The vector store is always a derived projection; the relational model is the source of truth.

### 5.2 Document Schema

#### 5.2.1 Identity and relational anchor

| Field | Type | Description |
|---|---|---|
| `evidence_id` | UUID v6 | FK → EVIDENCE.evidence_id — stable identifier across versions |
| `evidence_version_id` | UUID v6 | FK → EVIDENCE.evidence_version_id — together forms the unique document key |
| `evidence_type` | string | `face_detection` \| `named_entity` \| `text_region` \| `grounded_name` \| `grounded_description` \| `authority_identifier` — determines the modality and which vector slots and metadata fields are populated |

#### 5.2.2 Faceting metadata (derived from SOURCE and SOURCE_SCHEMA)

These fields are resolved at ingest time by applying the SOURCE_SCHEMA resolver logic to the EVIDENCE's SOURCE and `source_path`. Stored inline on the document for filter efficiency.

| Field | Type | Description |
|---|---|---|
| `source_id` | UUID v6 | FK → SOURCE — enables per-document-source filtering |
| `provider` | string | SOURCE.provider enum value — one of `kramerius`, `nkcr`, `wikimedia`, `local` — coarse provenance facet |
| `cluster_ids` | list[UUID v6] | Current cluster memberships — denormalised from MEMBERSHIP; updated on membership change |
| `language` | string (BCP 47) | Language of the textual content; null for non-textual evidence types |

#### 5.2.3 Named vector slots

Each slot is a dense float vector produced by a specific embedding model. Multiple slots may be present on the same document if the same content has been encoded by more than one model or pipeline. Each slot name encodes both the modality role and the model identifier, following the convention `<role>:<model_slug>`.

The `<role>` prefix is fixed per `evidence_type`:

| `evidence_type` | Role prefix | Meaning |
|---|---|---|
| `face_detection` | `face` | Embedding of the detected face crop |
| `named_entity` | `text` | Semantic embedding of the entity text span |
| `text_region` | `text` | Semantic embedding of the text region content |
| `text_region` | `layout` | Embedding encoding spatial/layout structure of the region |
| `grounded_name` | `text` | Semantic embedding of the name string |
| `grounded_description` | `text` | Semantic embedding of the description text |

Example slot names: `face:arcface-r100-v2`, `text:multilingual-e5-large-v1`, `layout:lilt-base-v1`.

Adding a new model produces new slot names on newly ingested documents. Old documents retain their original slots and are not backfilled unless an explicit re-embedding job is run.

#### 5.2.4 Modality-specific metadata fields

These fields are populated only for the applicable `evidence_type`s. They enable filtering and full-text search directly in the vector DB.

| Field | Type | Applicable `evidence_type`(s) | Description |
|---|---|---|---|
| `confidence` | float [0,1] | all | Detection or linking confidence from the originating model |
| `normalized_text` | string | `named_entity`, `grounded_name`, `grounded_description` | Normalised form of the text — enables full-text search alongside vector similarity |
| `name_type` | string | `grounded_name` | `preferred` or `alias` — allows filtering to preferred name forms only |
| `polygon` | object | `face_detection`, `named_entity` | Serialised `BoundingBox` — cached for search result thumbnail rendering without a relational join |
| `keypoints` | object | `face_detection` | Serialised list of `Keypoint`s — cached for search result thumbnail rendering without a relational join |
| `baseline` | object | `text_region`, `named_entity` | Serialised list of `Point`s representing the text baseline — cached for search result rendering without a relational join |
| `source` | object | all | Parsed source metadata — enables filtering and faceting |

### 5.3 Query Patterns

| Pattern | Vector slot prefix | Filters applied |
|---|---|---|
| Face similarity search | `face:*` | `evidence_type = face_detection` |
| Name similarity search | `text:*` | `evidence_type IN (named_entity, grounded_name)` |
| Preferred name search only | `text:*` | `evidence_type = grounded_name`, `name_type = preferred` |
| Full-text name search | — (keyword on `normalized_text`) | `evidence_type IN (named_entity, grounded_name)` |
| Description similarity | `text:*` | `evidence_type = grounded_description` |
| Within-cluster face search | `face:*` | `evidence_type = face_detection`, `cluster_ids contains <id>` |
| Source-scoped search | any | `source_id = <id>` |
| Provider-scoped search | any | `provider = <provider>` |
| Specific model retrieval | `face:arcface-r100-v2` | `evidence_type = face_detection` |
| Language-scoped name search | `text:*` | `evidence_type = grounded_name`, `language = <bcp47>` |

### 5.4 Lifecycle

- **On EVIDENCE ingest**: a new document is created in the vector store keyed on `(evidence_id, evidence_version_id)`. Faceting metadata is resolved from SOURCE and SOURCE_SCHEMA at this point. `cluster_ids` is initially empty.
- **On MEMBERSHIP change**: `cluster_ids` on all affected documents is updated. Eventual consistency is acceptable — vector queries are not the membership source of truth.
- **On EVIDENCE new version**: a new document is created for the new `evidence_version_id`. The old document is retained unless explicitly purged by a maintenance job.
- **On re-embedding**: new named vector slots (e.g. from a new model) are added to existing documents without replacing or removing old slots.
- **On EVIDENCE deletion**: all documents for that `evidence_id` are removed from the vector store.

---

## 6. Search Configuration

Search scoring is driven by per-modality weighted signals. Each modality corresponds to an `evidence_type` and an embedding model slot in the vector store. The structures in this section live outside the versioned cluster data model — they are user-space configuration that governs how retrieval is performed, not what was annotated or by whom.

### 6.1 MODEL_AGENT

See §4.12.3. MODEL_AGENT is a subclass of PRINCIPAL (`principal_type = model_agent`) and is the authoritative registry for all ML model agents that produce EVIDENCE or encode vectors. The fields `evidence_type`, `role`, `model_slug`, `model_version`, `registry_source`, `registry_uri`, and `is_active` are defined there.

For search configuration, a MODEL_AGENT row is referenced by `SEARCH_PROFILE_MODALITY` (see §6.3) to select which active model slot to use per modality during retrieval.

`registry_uri` format by `registry_source`:

| `registry_source` | Example `registry_uri` |
|---|---|
| `mlflow` | `models:/face-detector/3` (registered model name + version number) |
| `huggingface` | `DCGM/arcface-r100-v2@sha256:abc123` (repo + commit/tag) |
| `local` | `/models/face-detector-v2/` (filesystem path) |

### 6.2 SEARCH_PROFILE

A named, reusable search configuration. Its modality weights and model selections are stored in the join table `SEARCH_PROFILE_MODALITY` (see §6.3).

Fields: `profile_id`, `profile_name`, `description`, `owner_id`, `is_public`, `is_system`.

- `owner_id`: FK → PRINCIPAL — the user who created this profile. Null for system profiles.
- `is_public`: if true, the profile is visible and cloneable by all authenticated users.
- `is_system`: system-provided profiles are read-only defaults provisioned at deployment. They cannot be modified or deleted.

### 6.3 SEARCH_PROFILE_MODALITY

Join table that configures one modality's participation in a specific `SEARCH_PROFILE`. Each row represents one `(profile, evidence_type)` pair and carries a direct FK to the pinned `MODEL_AGENT`, if any.

Fields: `profile_id`, `evidence_type`, `model_id`, `weight`, `enabled`, `min_confidence`.

Constraints:
- `UNIQUE (profile_id, evidence_type)` — only one row per modality per profile.
- `profile_id`: FK → SEARCH_PROFILE.
- `model_id`: nullable FK → MODEL_AGENT — if null, the highest-priority active `MODEL_AGENT` for the `evidence_type` is resolved at query time. If set, the query is pinned to that specific agent's vector slot.
- `weight`: float [0, ∞) — relative contribution of this modality to the combined retrieval score. Weights across all enabled modalities are normalised to sum to 1.0 at query time.
- `enabled`: bool — whether this modality participates in the search. Allows toggling a modality off without deleting the row.
- `min_confidence`: nullable float [0, 1] — evidence of this type below this detection confidence are excluded from candidates before scoring.

#### 6.3.1 Example profiles

| Profile name | Description | Enabled modalities |
|---|---|---|
| `face-only` | Pure face similarity search | `evidence_type=face_detection` |
| `name-only` | Pure text name similarity search | `evidence_type=named_entity`, `evidence_type=grounded_name` |
| `balanced` | Equal-weight face and name signals | `evidence_type=face_detection weight=1.0`, `evidence_type=named_entity weight=1.0`, `evidence_type=grounded_name weight=1.0` |
| `authority-grounded` | Weighted towards authority name and description matches | `evidence_type=grounded_name weight=1.0`, `evidence_type=grounded_description weight=0.5`, `evidence_type=named_entity weight=0.5` |

### 6.4 Profile sharing and lifecycle

- **System profiles** (`is_system = true`) are provisioned at deployment time and serve as stable, read-only defaults. Their `SEARCH_PROFILE` row and all associated `SEARCH_PROFILE_MODALITY` rows cannot be modified or deleted.
- **User profiles** are created by any authenticated principal. A user may mark any of their own profiles as their personal default for search sessions.
- **Cloning**: any profile can be cloned. Cloning creates a new `SEARCH_PROFILE` row and copies all associated `SEARCH_PROFILE_MODALITY` rows to the new `profile_id`, owned by the requesting user. The clone is fully independent — there is no link back to the source profile, and subsequent changes to either do not affect the other. This is the only mechanism for deriving a customised variant of an existing profile.
- **Model retirement**: when a `MODEL_AGENT` is marked `is_active = false`, existing `SEARCH_PROFILE_MODALITY` rows that FK to it are detected via a simple indexed join on `model_id`. A warning is surfaced at query time to encourage migration to a newer agent. The FK prevents the `MODEL_AGENT` row from being deleted while any profile still references it.

