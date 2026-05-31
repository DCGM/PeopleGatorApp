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
6. User roles, audit.
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
    - Search query is itself a `search_cluster`: the query is expressed as a list of signals, zero to many per modality. A name string, a free-text snippet, and a face image each become typed evidence items in the same table used for ingested artifacts, subject to content-hash deduplication so identical signals are never stored twice.
    - The query cluster references those evidence items via `DELTA` entries, exactly like any other cluster. It can be saved, shared, or promoted into an annotation target.
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
    - The `reason` field on DELTA categorises intent (`manual-annotation` vs `automatic-linking`), while `actor_id` records the exact originator. Together they enable per-principal audit, replay, and trust scoring.

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
- `resolver_config`: JSONB with resolver-specific parameters. resolver can be applied on the SOURCE.source string and we can get structured source metadata, this metadata is materialized and can be e.g. faceted.

| `resolver_type` | Example `schema_name` | Example `resolver_config` |
|---|---|---|
| `db-source-table-row` | `user-provided-name` | `{"source_template": "{principal_id}"}` |
| `db-source-table-row` | `user-provided-description` | `{"source_template": "{principal_id}"}` |
| `s3-image` | `image-upload` | `{"bucket_template": "peoplegator-upload", "key_template": "{principal_id}/{file_id}.jpg"}` |
| `http-image` | `wikimedia-image` | `{"base_url_template": "https://commons.wikimedia.org/", "path_template": "wiki/Special:FilePath/{file_name}"}` |
| `fsspec-pagexml` | `kramerius-ocr-public` | `{"path_template": "zip://{page_id}.xml::file:///mnt/matylda1/ihradis/digiknihovna_public/{library}/{document_id}.page_xml.zip"}` |
| `fsspec-image` | `kramerius-image-public` | `{"path_template": "file:///mnt/matylda1/ihradis/digiknihovna_public/{library}/{document_id}.images/{page_id}.jpg"}` |
| `s3-table` | `nkcr-authority` | `{"bucket_template": "peoplegator-ingest", "key_template": "nlcr_aut/nlcr_aut__{text_type}.csv"}` |
| `s3-table` | `wikidata-authority` | `{"bucket_template": "peoplegator-ingest", "key_template": "wikidata/people_of_all_{text_type}.csv"}` |


Resolver then does the following for a SOURCE field where `schema_name` references this `SOURCE_SCHEMA`:
1. Take `SOURCE.metadata` and `SOURCE_SCHEMA.resolver_config`.
2. Interpolate any `{placeholders}` in `resolver_config` with values from `SOURCE.metadata` (e.g. `library`, `page_id`, `nkcr_authority_id`).
3. Construct the final URL or file path according to the `resolver_type` logic. For example, for `s3`, the final S3 key would be constructed by interpolating `key_template` with values from `SOURCE.metadata` and `PRINCIPAL` (e.g. `principal_id`), and the full S3 URI would be `s3://{bucket_template}/{interpolated_key}`.

### 4.2 SOURCE

A specific document, scan, or artifact from which one or more EVIDENCEs were derived. SOURCE normalises provenance — an EVIDENCE belongs to exactly one SOURCE, and the SOURCE belongs to one SOURCE_SCHEMA that knows how to resolve its storage paths.

Fields: `source_id`, `source_schema_name`, `metadata`, `created_by`.
- `source_id`: UUIDv6 primary key.
- `source`: opaque string identifier for the original source, e.g. a filename. Parsable via `source_schema_name`.
- `source_schema_name`: FK → SOURCE_SCHEMA — determines how this original source can be resolved.
- `content_hash` : hash of ingested content for deduplication and staleness detection, e.g. hash of the original image bytes for a scanned document, or hash of the authority record JSON for an imported authority entity.
- `created_by`: FK → PRINCIPAL — the user or service agent that ingested this source.

This is intentionally flexible to accommodate the wide variety of source types and metadata that may be relevant for different use cases. The exact structure of this JSONB is not enforced at the database level but is expected to conform to the requirements of the associated SOURCE_SCHEMA's resolver logic.

### 4.3 METADATA_SCHEMA

Defines the versioned structure of the `metadata` JSONB payload for each evidence type. Every EVIDENCE references one METADATA_SCHEMA, which identifies the contract that `metadata` conforms to and optionally carries a machine-readable JSON Schema for runtime validation. Centralising schema registration here means schema evolution is tracked in the database, not embedded as opaque string constants in application code.

Fields: `evidence_type`, `schema_version`, `json_schema`, `description`.

- `evidence_type`: the EVIDENCE type this schema applies to. Can be `face_detection`, `named_entity`, `text_region`, `grounded_name`, `grounded_description`, or `authority_identifier`.
- `schema_version`: version string for the schema, e.g. `v1`, `v2`.
- `json_schema`: optional JSONB — machine-readable JSON Schema (draft-07 compatible) for validating the `metadata` payload at ingest time. Null for built-in schemas whose structure is described in §4.4.2.
- `description`: optional free-text description of the schema's purpose and contents.

### 4.4 EVIDENCE

The unified atomic evidence unit. Every piece of evidence — face detections, name mentions, text regions, photos, and grounded identity claims — is an EVIDENCE.

Required fields: `evidence_id`, `evidence_version_id`, `content_hash`, `source_id`, `source_path`, `metadata_schema_name`, `inferred_metadata`, `revised_metadata`, `producer_id`, `revisor_id`.

- `evidence_id`: stable UUIDv6 identifier for this evidence.
- `evidence_version_id`: monotonically incrementing integer for versioning this evidence.
- `evidence_type`: part of FK, determines the schema of `metadata`.
- `schema_version`: part of FK, determines the version of the schema that `metadata` conforms to. Together pair (`evidence_type`, `schema_version`) FK -> METADATA_SCHEMA.
- `source_id`: FK → SOURCE — the document or artifact this evidence was derived from.
- `producer_id`: nullable FK → MODEL_AGENT — the model agent principal that produced this evidence. Null for manually curated or authority evidence. Must reference a PRINCIPAL with `principal_type = model_agent`.
- `produced_metadata`: JSONB typed evidence payload produced by the model, structured per `metadata_schema`.
- `revisor_id`: nullable FK → PRINCIPAL — the human user that last revised this evidence. Null if never revised.
- `revised_metadata`: JSONB with the same structure as `produced_metadata`, used for storing human revisions.
- `content_hash`: hash of the content if applicable, mainly hash of the metadata.


#### 4.4.1 Shared sub-schemas

These sub-schemas are reused across multiple evidence metadata types.

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

#### 4.4.2 Metadata schemas by evidence type

The `metadata_schema_id` FK links each EVIDENCE to a METADATA_SCHEMA row (see §4.3). Each type below defines the canonical structure of `metadata` JSONB for that evidence type. Adding a new schema version creates a new METADATA_SCHEMA row; old EVIDENCEs remain valid by retaining their original FK.

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


#### `authority_identifier` — schema_version `v1`

An identifier for an authority entity, such as a Wikidata QID or an NKCR ID. The entity is captured by `EVIDENCE.source_id` as above.

| Field | Type | Required | Description |
|---|---|---|---|
| `identifier` | string | yes | The authority identifier, e.g. `Q42` for Wikidata or `NKCR12345` for NKCR |
| `authority_type` | string | yes | The type of authority, e.g. `wikidata` or `nkcr` |

### 4.5 CLUSTER

Stable identity for a cluster across its version history.

Fields: `cluster_id`, `cluster_role`, `head_version_id`, `head_constraints`.


`cluster_role` values:

| Role | Created by |
|---|---|
| `mutable_cluster` |  A cluster that is proposed automatically or by an annotator |
| `review_cluster` |  A cluster that is under review by a human annotator |
| `grounded_cluster` | Reviewer promotion of a `review_cluster` |
| `authority_cluster` | Authority sync (Wikidata, NKCR import) |
| `automatic_cluster` | Automatically generated cluster without human intervention |
| `search_cluster` | Product of user initiated search can be commited or empheral |

Possible `head_constraints` values:
| Constraint | Description |
|---|---|
| `locked` | Materialized view display only first version of the cluster. |
| `main` | Materialized views are locked to only the last `stage` operation chain of the cluster. |
| `any` | Materialized views can display any versions of the cluster. |

`CLUSTER.cluster_role` is a denormalized cache of the `cluster_role` from the version pointed to by `head_version_id`. It must be updated atomically in the same transaction as any `head_version_id` change. `VERSION.cluster_role` is the source of truth.

`head_version_id` update rules — updated atomically whenever a new version becomes the logical head of this cluster's main chain:
- On `empty`: set to the initial `version_id`.
- On `stage`: set to the new `target_version_id` with current head being the `source_version_id`.
- On `union` or `intersection` where this cluster is the target and the current head is one of the source versions: set to `target_version_id`.
- On `branch`: `head_version_id` is **not** updated — it stays on the main-chain version the branch diverged from.

### 4.6 VERSION

One immutable snapshot of cluster membership state. Created by copy-on-write on any membership change.

Fields: `version_id`, `cluster_id`, `cluster_role`, `actor_id`.

- `actor_id`: FK to PRINCIPAL — the user or service agent that created this version.

### 4.7 OPERATION
Represents a directed edge between versions of the same cluster, or between versions of independent logical clusters.

Fields: `source_cluster_id`, `source_version_id`, `target_cluster_id`, `target_version_id`, `operation_type`.
The operation_type field can contain following values:
| Operation Type | Description | Enforced Constraints |
|---|---|---|
| `empty` | The initial version of a cluster, it has no prior versions, declared cluster as empty. | `source_cluster_id=cluster_id`, `target_cluster_id=cluster_id`, `source_version_id=NULL`, `target_version_id=version_id`. No prior operation entry exists for the `cluster_id`. |
| `stage` | A new version is created by advancing the previous version. | `source_cluster_id == target_cluster_id` |
| `branch` | A new parallel version is created from a source version. | `source_cluster_id == target_cluster_id` |
| `union` | Two or more parallel versions or clusters are merged into one via union, all materialized members from all sources will be in the final version. | single `target_version_id`, `target_cluster_id`, multiple `source_version_id` rows and `source_cluster_id` values |
| `intersection` | Two or more parallel versions or clusters are merged into one, keeping only common members. | single `target_version_id`, `target_cluster_id`, multiple `source_version_id` rows and `source_cluster_id` values |
| `split` | One cluster is split into two or more clusters. | single `source_version_id`, multiple `target_version_id` rows |

### 4.8 DELTA

Associates an EVIDENCE applied as a delta to specific CLUSTER VERSION, representing the addition or removal of that evidence from the cluster in that version. This is the core table for determining cluster membership at any given version.

Fields: `delta_id`, `cluster_id`, `version_id`, `evidence_id`, `evidence_version_id`, `delta_type` (`add` or `remove`), `weight`, `actor_id`.

Explanation of fields:
- `cluster_id`: Denormalized from `VERSION` for query performance — `version_id` alone uniquely identifies a cluster version, but `cluster_id` enables efficient indexed queries such as `WHERE cluster_id = $1`. Must always match the `cluster_id` of the referenced `version_id`.
- `delta_type`: Indicates whether the evidence is being added to or removed from the `version_id` `cluster_id` state.
- `weight`: A numerical value representing the strength of the association between the evidence and the cluster in this commit, which can be used for ranking and confidence scoring.
- `actor_id`: FK to PRINCIPAL — the user, service agent, or model agent that authored this specific evidence addition or removal.

Here enforced constraints for the DELTA:
1. `evidence_id` and `evidence_version_id` must exist in the EVIDENCE table
2. The `cluster_id` must exist in the CLUSTER table.
3. The `version_id` must exist in the VERSION table for the specified `cluster_id`.
4. There is no entry in the OPERATION table for the `cluster_id` and `version_id` as `source_cluster_id` and `source_version_id`. No derived versions have been created.
5. For an `add` delta, the specified `evidence_id` and `evidence_version_id` must exist in the EVIDENCE table, and the `version_id` must exist in the VERSION table for the specified `cluster_id`.


#### 4.8.1 Algorithm to resolve membership for a given `cluster_id` and `version_id`:
1. Start with an empty set of member evidence.
2. From `OPERATION`, start with the specified `cluster_id` and `version_id`, and perform a full DAG walk backwards through all ancestor operation entries to the root version, collecting all `(cluster_id, version_id)` pairs. Follow ALL ancestor paths — including those via `union`, `intersection`, and `split` entries that cross cluster boundaries. Do not prune at the first path to root.
3. For each collected `cluster_id` and `version_id`, query the DELTA table for all deltas associated with that version.
4. Sort the collected deltas globally by their `delta_id` ascending. Because `delta_id` is a UUIDv6, this is equivalent to creation-time order across all ancestor versions.
5. Sequentially apply each delta to the set of member evidence, adding or removing evidence based on the `delta_type` and updating the `weight` and `reason` accordingly.
6. After processing all deltas, the resulting set of member evidence represents the cluster membership for the specified `cluster_id` and `version_id`.

#### 4.8.2 Algorithm to resolve pending (unsealed) changes for a given `cluster_id` and `version_id`:
1. From `DELTA` table, query for any deltas associated with the specified `cluster_id` and `version_id`.
2. Sort the deltas by their `delta_id` ascending to ensure they are processed in the order they were created.
3. Reduce the deltas if same `EVIDENCE` has been added and removed multiple times, keeping only the latest delta for each `EVIDENCE`.
4. The resulting set of deltas represents the pending diff on the current working version for the specified `cluster_id` and `version_id`.

#### 4.8.3 Resolve possible head of the cluster:
- Case `locked` in `head_constraints`:
  1. From `OPERATION`, query for the first version of the cluster with `cluster_id` and `operation_type` = `empty`.
  2. The resulting `version_id` represents the head of the cluster.
- Case `main`:
  1. Filter `OPERATION` for entries with `cluster_id`.
  2. Sort the filtered operations by `target_version_id` ascending.
  3. Set head version to the version with `operation_type` = `empty`, it should be first in the sorted list.
  4. Go through the list and update the head version if any of the following conditions are met:
    - `operation_type` is `stage` and `source_version_id` equals the current head version → `target_version_id` is now the head version.
    - `operation_type` is `union` or `intersection` and `source_cluster_id == cluster_id` and `source_version_id` equals the current head version → `target_version_id` is now the head version.

- Case `any`:
  1. From `OPERATION`, query for all versions of the cluster with `cluster_id` and `operation_type` in (`empty`, `stage`, `branch`, `union`, `intersection`, `split`).
  2. The resulting set of `version_id`s represents all possible heads of the cluster. MEMBERSHIP for a cluster with `any` constraints is the union of memberships across all leaf versions (versions with no outgoing `stage`, `union`, or `intersection` operation).


### 4.9 TASK

A unit of work assigned to a PRINCIPAL, directing them to act on a specific cluster commit. Tasks are the primary mechanism for driving the annotation and review workflow.

Fields: `task_id`, `cluster_id`, `version_id`, `assignee_id`, `task_role`, `status`, `created_by`, `created_at`, `updated_at`.

- `cluster_id`: FK → CLUSTER — the cluster this task concerns.
- `version_id`: FK → VERSION — the specific version the assignee should work from. Pinned at task creation so the assignee always sees a consistent snapshot.
- `assignee_id`: FK → PRINCIPAL — the user assigned to perform the task.
- `created_by`: FK → PRINCIPAL — the user or service agent that created this task.
- `task_role`: specifies what the assignee is expected to do with the cluster commit.
- `status`: lifecycle state of the task.

`task_role` values:

| Role | Description |
|---|---|
| `annotate` | Assignee should review and extend or correct the cluster membership |
| `review` | Assignee should adjudicate annotation branches and produce a consolidated version |
| `verify` | Assignee should confirm the cluster grounding against authority records |

`status` values:

| Status | Description |
|---|---|
| `pending` | Task created, not yet accepted by the assignee |
| `submitted` | Assignee has submitted their changes for the next workflow stage |
| `closed` | Task completed or cancelled; no further action expected |


### 4.10 MEMBERSHIP
Represents the current materialized state of cluster membership for each cluster, derived from the DELTA table.

Fields: `cluster_id`, `evidence_id`, `evidence_version_id`, `weight`, `reason`, `as_of_version_id`.

`as_of_version_id` records which version this materialized state was derived from, allowing staleness detection. Its value is `CLUSTER.head_version_id` at the time of the last update.

The view is updated in real-time as new DELTAs are added, ensuring that it always reflects the latest state of cluster membership. This allows for efficient querying of current cluster members without needing to replay the full version operation history and deltas each time. Updates to MEMBERSHIP must be applied in the same transaction as the DELTA write that triggered them. MEMBERSHIP reflects the sealed state only — pending deltas (those on a version that has no outgoing operation entry yet) are applied to MEMBERSHIP as they are written, since the working version is the live head.

### 4.11 PRINCIPAL

Unified identity record for any actor that can modify the system. Every VERSION and every DELTA carries an `actor_id` FK to this table, giving a complete audit trail of who changed what. Every EVIDENCE carries a `producer_id` FK to this table, identifying the model that generated the evidence.

`principal_type` values:

| Type | Description |
|---|---|
| `user` | A human authenticated via an external OIDC provider |
| `service_agent` | A named autonomous process (ingestion pipeline, non-ML automation, etc.) |
| `model_agent` | A registered ML model agent capable of producing EVIDENCE and acting autonomously |

Fields: `principal_id`, `principal_type`, `display_name`, `is_active`.

`PRINCIPAL.principal_type` is the polymorphic discriminator. Type-specific fields are stored in the joined `USER`, `SERVICE_AGENT`, or `MODEL_AGENT` table.

### 4.12 SOURCE_PROCESSING

Flags whether a MODEL_AGENT principal has been applied to a SOURCE to get EVIDENCEs.

Fields: `source_id`, `producer_id`, `is_processed`.

- `source_id`: FK → SOURCE (part of composite PK).
- `producer_id`: FK → PRINCIPAL where `principal_type = model_agent` (part of composite PK).
- `is_processed`: boolean — `true` once all resulting EVIDENCEs have been ingested; `false` while pending or in-flight.

`(source_id, producer_id)` is the composite primary key — one row per pair. To find sources not yet processed by a given model, query for rows where `is_processed = false` or for sources with no row at all for that `producer_id`.

Evidence-level lineage is available via `EVIDENCE.producer_id`, which carries the FK to the model principal that produced it (null for manually curated or authority evidence).

#### 4.11.3 MODEL_AGENT

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

#### 4.11.1 USER

A human principal authenticated through an external OpenID Connect (OIDC) identity provider such as Keycloak or Auth0. The user record is created or refreshed on first token verification.

Fields (extends PRINCIPAL): `principal_id`, `external_subject`, `external_issuer`, `email`.

- `external_subject`: the OIDC `sub` claim — stable, provider-scoped user identifier.
- `external_issuer`: the OIDC `iss` claim — identifies the identity provider.
- Together `(external_subject, external_issuer)` forms a globally unique identity key across multiple IdPs.
- `email` is optional; sourced from the OIDC `email` claim when present.

#### 4.11.2 SERVICE_AGENT

An autonomous process principal. Agents are pre-registered and identified by a unique `agent_slug` following the convention `<category>:<name>`, for example:

| Slug | Category | Description |
|---|---|---|
| `system:kramerius-ingest` | `system` | Kramerius document ingestion pipeline |
| `agent:face-detector-v2` | `agent` | Face detection ML model, version 2 |
| `agent:ner-extraction` | `agent` | Named-entity recognition pipeline |
| `pipeline:authority-sync` | `pipeline` | Periodic authority record synchronisation |

Fields (extends PRINCIPAL): `principal_id`, `agent_slug`, `description`.

- `agent_slug`: unique human-readable identifier, format `<category>:<name>`.
- `description`: optional free-text description of the agent's purpose.

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
| `evidence_type` | string | `face_detection` \| `named_entity` \| `text_region` \| `image_region` \| `grounded_name` \| `grounded_description` — determines the modality and which vector slots and metadata fields are populated |

#### 5.2.2 Faceting metadata (derived from SOURCE and SOURCE_SCHEMA)

These fields are resolved at ingest time by applying the SOURCE_SCHEMA resolver logic to the EVIDENCE's SOURCE and `source_path`. Stored inline on the document for filter efficiency.

| Field | Type | Description |
|---|---|---|
| `source_id` | UUID v6 | FK → SOURCE — enables per-document-source filtering |
| `provider` | string | SOURCE.provider value, e.g. `kramerius`, `nkcr`, `local-ingest` — coarse provenance facet |
| `cluster_ids` | list[UUID v6] | Current cluster memberships — denormalised from MEMBERSHIP; updated on membership change |
| `language` | string (BCP 47) | Language of the textual content; null for non-textual evidence types |

#### 5.2.3 Named vector slots

Each slot is a dense float vector produced by a specific embedding model. Multiple slots may be present on the same document if the same content has been encoded by more than one model or pipeline. Each slot name encodes both the modality role and the model identifier, following the convention `<role>:<model_slug>`.

The `<role>` prefix is fixed per `evidence_type`:

| `evidence_type` | Role prefix | Meaning |
|---|---|---|
| `face_detection` | `face` | Embedding of the detected face crop |
| `image_region` | `image` | Embedding of an image patch |
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

See §4.11.3. MODEL_AGENT is a subclass of PRINCIPAL (`principal_type = model_agent`) and is the authoritative registry for all ML model agents that produce EVIDENCE or encode vectors. The fields `evidence_type`, `role`, `model_slug`, `model_version`, `registry_source`, `registry_uri`, and `is_active` are defined there.

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

