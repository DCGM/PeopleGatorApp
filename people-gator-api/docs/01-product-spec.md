# People Gator Product Specification

## 1. Purpose

People Gator API is an backend for person-centric retrieval an person cluster annotation in historical document scans.

Main workflow:
1. Search returns ranked information clusters — groupings of face detections, name mentions, and authority records that speak to the same person.
2. Annotators confirm, extend, or reject proposed clusters.
3. Annotator can search similar looking units (faces, names, authority records, paragraphs..) to find additional evidence and add to the cluster.
4. Annotators can merge clusters they believe to be the same person, or can create new clusters if they believe no existing cluster matches.
5. Commited annotations are presented to reviewers.
6. Reviewer create single master record update from all annotation branches, that were sent to annotators.
7. Reviewed clusters are promoted to grounded clusters.

## 2. Product Scope

### 2.1 In Scope

1. Search over prepared historical scan artifacts.
2. Person-centric retrieval (face, image, page, line, region, named entity span).
3. Person cluster retrieval, creation, extension, merging, and versioning.
4. Grounding to locally imported authority sources (Wikidata, NKCR).
5. Annotation workflows, inter-annotator agreement tracking, and reviewer adjudication.
6. User roles, audit, and export.

### 2.2 Out of Scope

1. Model training.
2. Data gathering and artifact preparation (OCR, face detection, NER, embedding generation).
3. Model inference (face detection, OCR, embeddings, NER), will use only API calls.
4. Live external authority queries at search time, everything is pre-ingested and indexed.
5. Downstream applications of the data (exhibition interfaces, research interfaces, etc.)

## 3. Geographic and Historical Focus

Authority filtering defaults to: Czechoslovakia, Czechia, Slovakia, Hungary, Austria, Austria-Hungary, Germany, Poland. Configurable without schema changes.

## 4. Design Principles

1. Cluster-first: search returns, annotation targets, and grounding outputs are all information clusters.
    - Search query is defined as a set of weighted signals (face similarity, name similarity, authority link strength, etc.), meaning it itself is a **information cluster**.
    - Any person evidence that is grouped together in a cluster.
    - Search can return similarity-ranked clusters.
    - Search can return individual records, their cluster lineage is optional.
2. Typed canonical records: every atomic evidence item preserves typed metadata, and lineage information.
    - Typed metadata enables modality-specific search signals and faceting. 
    - Lineage tells about the source of data.
3. Explainable ranking: every cluster result includes per-modality signal contributions, extensive info enables per member analysis.
4. Human-in-the-loop user workflows: search
    - Search results are ranked clusters with per-modality signal contributions.
    - Search query itself is a weighted cluster of signals (face similarity, name similarity, authority link strength, etc.).
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
    - This service does not perform OCR, face detection, NER, embedding generation, or authority linking. It only ingests the outputs of those processes as typed records.
    - This service does not train or serve any models. It only stores the model version used to generate each record and uses that for staleness detection.
    - This service does not perform live authority lookups. It only ingests authority records from periodic syncs and links them to clusters, via exposed APIs for data access.
8. Identity-first accountability: every state change carries a traceable actor.
    - Every COMMIT and every ACTION records a `actor_id` referencing a PRINCIPAL — either a human user or a named service agent.
    - Human users are identified via external OIDC authentication (e.g. Keycloak, Auth0). Their stable identity is the `(sub, iss)` claim pair from the ID token.
    - Service agents are autonomous processes identified by a conventional slug such as `system:kramerius-ingest` or `agent:face-detector-v2`. Slugs encode the agent category and name.
    - The `reason` field on ACTION categorises intent (`manual-annotation` vs `automatic-linking`), while `actor_id` records the exact originator. Together they enable per-principal audit, replay, and trust scoring.

## 5. Data Model

### 5.0 IDs

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

### 5.1 SOURCE_SCHEMA

Defines how to resolve the storage and access paths for a family of sources. Every SOURCE references one SOURCE_SCHEMA, which tells the system how to construct local file paths, remote URLs, or IIIF endpoints from a source's provider identifier. Centralising this logic here means both the local archive copy and the remote canonical URL are derived from the same SOURCE record — there is no duplication on RECORD itself.

Fields: `schema_name`, `resolver_type`, `resolver_config`.

- `schema_name`: human-readable label, e.g. `s3-upload`, `kramerius5-iiif`, `wikimedia-image`, `nkcr-authority`. Must be globally unique.
- `resolver_type`: one of `this-table`,  `local-filesystem`, `s3`, `iiif`, `http`, `sparql`.
- `resolver_config`: JSONB with resolver-specific parameters, interpolated with values from `SOURCE.provider_id` and optionally `RECORD.source_path`.

| `resolver_type` | Example `schema_name` | Example `resolver_config` |
|---|---|---|
| `this-table` | `principal-defined-name` | `{"name": "{text}"}` |
| `this-table` | `principal-defined-description` | `{"description": "{text}"}` |
| `s3` | `s3-upload` | `{"bucket_template": "peoplegator-upload", "key_template": "{principal_id}/{file_id}.jpg"}` |
| `http` | `kramerius5-iiif` | `{"base_url_template": "https://api.kramerius.{library}.cz/", "manifest_template": "search/iiif/uuid:{page_id}/full/max/0/default.jpg"}` |
| `http` | `wikimedia-image` | `{"base_url_template": "https://commons.wikimedia.org/", "path_template": "wiki/Special:FilePath/{file_name}"}` |
| `http` | `wikidata-entity` | `{"base_url_template": "https://www.wikidata.org/", "path_template": "wiki/{wikidata_id}"}` |
| `http` | `nkcr-authority` | `{"base_url_template": "https://aleph.nkp.cz/", "path_template": "F/?func=find-b&local_base=AUT&find_code=WRD&request={nkcr_authority_id}"}` |


Resolver then does the following for a SOURCE field where `schema_name` references this `SOURCE_SCHEMA`:
1. Take `SOURCE.metadata` and `SOURCE_SCHEMA.resolver_config`.
2. Interpolate any `{placeholders}` in `resolver_config` with values from `SOURCE.metadata` (e.g. `library`, `page_id`, `nkcr_authority_id`).
3. Construct the final URL or file path according to the `resolver_type` logic. For example, for `s3`, the final S3 key would be constructed by interpolating `key_template` with values from `SOURCE.metadata` and `PRINCIPAL` (e.g. `principal_id`), and the full S3 URI would be `s3://{bucket_template}/{interpolated_key}`.

### 5.2 SOURCE

A specific document, scan, or artifact from which one or more RECORDs were derived. SOURCE normalises provenance — a RECORD belongs to exactly one SOURCE, and the SOURCE belongs to one SOURCE_SCHEMA that knows how to resolve its storage paths.

Fields: `source_id`, `source_schema_id`, `metadata`, `created_by`.
- `source_id`: UUIDv6 primary key.
- `source_schema_id`: FK → SOURCE_SCHEMA — determines how this original source can be resolved.
- `created_by`: FK → PRINCIPAL — the user or service agent that ingested this source.
- `metadata`: JSONB with source-level descriptive information — document title, publication date, page number within a multi-page document, detected language, collection name, etc.

This is intentionally flexible to accommodate the wide variety of source types and metadata that may be relevant for different use cases. The exact structure of this JSONB is not enforced at the database level but is expected to conform to the requirements of the associated SOURCE_SCHEMA's resolver logic.

### 5.3 METADATA_SCHEMA

Defines the versioned structure of the `metadata` JSONB payload for each record type. Every RECORD references one METADATA_SCHEMA, which identifies the contract that `metadata` conforms to and optionally carries a machine-readable JSON Schema for runtime validation. Centralising schema registration here means schema evolution is tracked in the database, not embedded as opaque string constants in application code.

Fields: `schema_id`, `schema_name`, `record_type`, `version`, `json_schema`, `description`.

- `schema_name`: the canonical versioned identifier, e.g. `face-detection/v1`, `named-entity/v1`, `text-region/v1`. Must be globally unique.
- `record_type`: the RECORD type this schema applies to (see §5.4). One registered schema per `(record_type, version)` pair is enforced.
- `version`: schema version string, e.g. `v1`, `v2`. Incrementing the version produces a new METADATA_SCHEMA row while leaving the old one intact, so old RECORDs referencing the previous version remain valid.
- `json_schema`: optional JSONB — machine-readable JSON Schema (draft-07 compatible) for validating the `metadata` payload at ingest time. Null for built-in schemas whose structure is described in §5.4.2.
- `description`: optional free-text description of the schema's purpose and contents.

### 5.4 RECORD

The unified atomic evidence unit. Every piece of evidence — face detections, name mentions, text regions, photos, and grounded identity claims — is a RECORD.

Required fields: `record_id`, `record_version_id`, `record_type`, `content_hash`, `source_id`, `source_path`, `metadata_schema_id`, `metadata`, `embedding_id`.

- `source_id`: FK → SOURCE — the document or artifact this record was derived from.
- `source_path`: JSONB — within-source coordinates that identify exactly where in the source this record originates, e.g. `{"page": 3, "region_index": 7}` or `{"line_id": "abc", "face_index": 2}`. Combined with SOURCE_SCHEMA.resolver_config this fully resolves the physical storage location without duplicating paths on the record.
- `embedding_id`: nullable string — top-level reference to this record's embedding vector in the external vector store (Qdrant, Weaviate, Milvus, etc.). Stored at the top level because it is a first-class join key for similarity search, not an opaque metadata detail. Records that are the *root* of an embedding (i.e. the crop or text span that was directly encoded) carry a non-null `embedding_id`.
- `metadata_schema_id`: FK → METADATA_SCHEMA — identifies the versioned contract that `metadata` conforms to (see §5.4.2).
- `metadata`: JSONB typed evidence payload, structured per `metadata_schema`.
- `content_hash`: hash of the content that defines the record's identity for deduplication and staleness detection (e.g. for a face detection: hash of the image crop pixels and the embedding vector).

The `record_version_id` with `record_id` forms a unique identifier for each version. When a record is updated (e.g. a face detection is refined with a new bounding box), a new RECORD row is created with the same `record_id` but a later `record_version_id`, preserving the full version history.

Record types: `face_detection`, `named_entity`, `text_region`, `image_region`, `grounded_name`, `grounded_description`.

The `model_version` is stored inside `metadata` for records generated by inference, enabling staleness detection when a new model version is released.

#### 5.4.1 Shared sub-schemas

These sub-schemas are reused across multiple record metadata types.

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

**Image** — a information about image that is associated with a record, mainly defining image format and dimensions.
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

#### 5.4.2 Metadata schemas by record type

The `metadata_schema_id` FK links each RECORD to a METADATA_SCHEMA row (see §5.3). Each type below defines the canonical structure of `metadata` JSONB for that record type. Adding a new schema version creates a new METADATA_SCHEMA row; old RECORDs remain valid by retaining their original FK.

##### `face_detection` — schema `face-detection/v1`

| Field | Type | Required | Description |
|---|---|---|---|
| `bounding_box` | BoundingBox | yes | Detection area on the source image |
| `keypoints` | list[Keypoint] | no | Facial landmarks when available from the detector |
| `image` | Image | yes | Image format and dimensions for this detection |
| `confidence` | float [0,1] | yes | Model confidence score for this detection |
| `model_version` | string | yes | Model identifier that produced this detection |

The top-level `embedding_id` on RECORD links this detection's face crop to its vector in the embedding store.

##### `named_entity` — schema `named-entity/v1`

| Field | Type | Required | Description |
|---|---|---|---|
| `span` | PhysicalTextSpan | yes | Detected text span with layout information |
| `confidence` | float [0,1] | yes | Model confidence score for this detection |
| `model_version` | string | yes | Model identifier that produced this detection |

##### `text_region` — schema `text-region/v1`

| Field | Type | Required | Description |
|---|---|---|---|
| `area` | PhysicalTextRegion | yes | Detected text region with layout information |
| `confidence` | float [0,1] | yes | Model confidence score for this detection |
| `model_version` | string | yes | Model identifier that produced this detection |


##### `grounded_name` — schema `grounded-name/v1`

A name form belonging to an authority entity. The entity itself is captured by `RECORD.source_id`, which references the authority SOURCE — there is no explicit authority FK inside the metadata.

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes | Name form as recorded in the authority source |
| `type` | string | yes | `preferred` or `alias` — role of this name form in the authority |
| `language` | string (BCP 47) | no | Language of the name form, if applicable |
| `confidence` | float [0,1] | no | Linking confidence when assigned by an automated process; omit for manually curated authority data |

##### `grounded_description` — schema `grounded-description/v1`

A textual description belonging to an authority entity. The entity is captured by `RECORD.source_id` as above.

| Field | Type | Required | Description |
|---|---|---|---|
| `description` | string | yes | Description text as recorded in the authority source |
| `language` | string (BCP 47) | no | Language of the description, if applicable |
| `confidence` | float [0,1] | no | Linking confidence when assigned by an automated process |

### 5.5 CLUSTER

Stable identity for a cluster across its version history.

Fields: `cluster_id`, `cluster_role`, `head_commit_id`, `head_constraints`.


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
| `main` | Materialized views are locked to only the last `next` lineage chain of the cluster. |
| `any` | Materialized views can display any versions of the cluster. |

`CLUSTER.cluster_role` is a denormalized cache of the `cluster_role` from the commit pointed to by `head_commit_id`. It must be updated atomically in the same transaction as any `head_commit_id` change. `COMMIT.cluster_role` is the source of truth.

`head_commit_id` update rules — updated atomically whenever a new commit becomes the logical head of this cluster's main chain:
- On `initial`: set to the initial `commit_id`.
- On `next`: set to the new `target_commit_id` with current head being the `source_commit_id`.
- On `merge` or `cluster-merge` where this cluster is the target and the current head is one of the source commits: set to `target_commit_id`.
- On `branch`: `head_commit_id` is **not** updated — it stays on the main-chain commit the branch diverged from.

### 5.6 COMMIT

One immutable version within a lineage. Created by copy-on-write on any membership change.

Fields: `commit_id`, `cluster_id`, `cluster_role`, `actor_id`.

- `actor_id`: FK to PRINCIPAL — the user or service agent that created this commit version.

### 5.7 LINEAGE
Represents a relations of versions of the same cluster and relations between commits of independent logical clusters e.g. for `next`, `branch`, `pull`, `cluster-merge`, `cluster-split`.

Fields: `source_cluster_id`, `source_commit_id`, `target_cluster_id`, `target_commit_id`, `lineage_type`.
The lineage_type field can contain following values:
| Lineage Type | Description | Enforced Constraints |
|---|---|---|
| `initial` | The initial version of a cluster. | `source_cluster_id` and `source_commit_id` are `NULL`. No prior lineage entry exists for the `cluster_id`. |
| `next` | A new version is created by modifying the previous version. | `source_cluster_id == target_cluster_id` |
| `branch` | A new branch is created from a parent commit. | `source_cluster_id == target_cluster_id` |
| `merge` | Two or more branches within the same cluster are merged into one. | single `target_commit_id`, multiple `source_commit_id` rows; `source_cluster_id == target_cluster_id` |
| `cluster-merge` | Commits from two or more different clusters are merged into a single target cluster. | single `target_commit_id`, multiple `source_commit_id` rows; `source_cluster_id` may differ from `target_cluster_id` |
| `split` | One cluster is split into two or more clusters. | single `source_commit_id`, multiple `target_commit_id` rows |

### 5.8 ACTION

Associates a RECORD with a specific CLUSTER COMMIT, representing the addition or removal of that record from the cluster in that version. This is the core table for determining cluster membership at any given version.

Fields: `action_id`, `cluster_id`, `commit_id`, `record_id`, `record_version_id`, `action_type` (`add` or `remove`), `weight`, `reason`, `actor_id`.

Explanation of fields:
- `cluster_id`: Denormalized from `COMMIT` for query performance — `commit_id` alone uniquely identifies a cluster's commit, but `cluster_id` enables efficient indexed queries such as `WHERE cluster_id = $1`. Must always match the `cluster_id` of the referenced `commit_id`.
- `action_type`: Indicates whether the record is being added to or removed after `commit_id` `cluster_id` state.
- `weight`: A numerical value representing the strength of the association between the record and the cluster in this commit, which can be used for ranking and confidence scoring.
- `reason`: Can be `manual-annotation` or `automatic-linking`.
- `actor_id`: FK to PRINCIPAL — the user or service agent that authored this specific record addition or removal.

Here enforced constraints for the ACTION:
1. `record_id` and `record_version_id` must exist in the RECORD table
2. The `cluster_id` must exist in the CLUSTER table.
3. The `commit_id` must exist in the COMMIT table for the specified `cluster_id`.
4. There is no entry in lineage table for the `cluster_id` and `commit_id` as `source_cluster_id` and `source_commit_id`. No derived versions have been created.
5. For an `add` action, the specified `record_id` and `record_version_id` must exist in the RECORD table, and the `commit_id` must exist in the COMMIT table for the specified `cluster_id`.


#### 5.8.1 Algorithm to resolve membership for a given `cluster_id` and `commit_id`:
1. Start with an empty set of member records.
2. From `LINEAGE`, start with the specified `cluster_id` and `commit_id`, and perform a full DAG walk backwards through all ancestor lineage entries to the root commit, collecting all `(cluster_id, commit_id)` pairs. Follow ALL ancestor paths — including those via `cluster-merge` and `cluster-split` entries into different clusters. Do not prune at the first path to root.
3. For each collected `cluster_id` and `commit_id`, query the ACTION table for all actions associated with that commit.
4. Sort the collected actions globally by their `action_id` ascending. Because `action_id` is a UUIDv6, this is equivalent to creation-time order across all ancestor commits.
5. Sequentially apply each action to the set of member records, adding or removing records based on the `action_type` and updating the `weight` and `reason` accordingly.
6. After processing all actions, the resulting set of member records represents the cluster membership for the specified `cluster_id` and `commit_id`.

#### 5.8.2 Algorithm to resolve uncommitted changes for a given `cluster_id` and `commit_id`:
1. From `ACTION` table, query for any actions associated with the specified `cluster_id` and `commit_id`.
2. Sort the actions by their `action_id` ascending to ensure they are processed in the order they were created.
3. Reduce the actions if same `RECORD` has been added and removed multiple times, keeping only the latest action for each `RECORD`.
4. The resulting set of actions represents the uncommitted diff from the last committed state for the specified `cluster_id` and `commit_id`.

#### 5.8.3 Resolve possible head of the cluster:
- Case `locked` in `head_constraints`:
  1. From `LINEAGE`, query for the first commit of the cluster with `cluster_id` and `lineage_type` = `initial`.
  2. The resulting `commit_id` represents the head of the cluster.
- Case `main`:
  1. Filter `LINEAGE` for entries with `cluster_id`.
  2. Sort the filtered lineage by `target_commit_id` ascending.
  3. Set head commit to commit with `lineage_type` = `initial`, it should be first in the sorted list.
  4. Go through the list and update the head commit if any of the following conditions are met:
    - `lineage_type` is `next` and `source_commit_id` equals the current head commit → `target_commit_id` is now the head commit.
    - `lineage_type` is `merge` and `source_commit_id` equals the current head commit → `target_commit_id` is now the head commit.
    - `lineage_type` is `cluster-merge` and `source_cluster_id == cluster_id` and `source_commit_id` equals the current head commit → `target_commit_id` is now the head commit.

- Case `any`:
  1. From `LINEAGE`, query for all commits of the cluster with `cluster_id` and `lineage_type` in (`initial`, `next`, `branch`, `merge`, `cluster-merge`, `cluster-split`).
  2. The resulting set of `commit_id`s represents all possible heads of the cluster. MEMBERSHIP for a cluster with `any` constraints is the union of memberships across all leaf commits (commits with no outgoing `next` or `merge` entry).


### 5.9 TASK

A unit of work assigned to a PRINCIPAL, directing them to act on a specific cluster commit. Tasks are the primary mechanism for driving the annotation and review workflow.

Fields: `task_id`, `cluster_id`, `commit_id`, `assignee_id`, `task_role`, `status`, `created_by`, `created_at`, `updated_at`.

- `cluster_id`: FK → CLUSTER — the cluster this task concerns.
- `commit_id`: FK → COMMIT — the specific commit version the assignee should work from. Pinned at task creation so the assignee always sees a consistent snapshot.
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


### 5.10 MEMBERSHIP
Represents the current materialized state of cluster membership for each cluster, derived from the ACTION table.

Fields: `cluster_id`, `record_id`, `record_version_id`, `weight`, `reason`, `as_of_commit_id`.

`as_of_commit_id` records which commit this materialized state was derived from, allowing staleness detection. Its value is `CLUSTER.head_commit_id` at the time of the last update.

The view is updated in real-time as new ACTIONs are added, ensuring that it always reflects the latest state of cluster membership. This allows for efficient querying of current cluster members without needing to compute the full lineage of commits and actions each time. Updates to MEMBERSHIP must be applied in the same transaction as the ACTION write that triggered them. MEMBERSHIP reflects the committed state only — uncommitted actions (those on a commit that has no outgoing lineage entry yet) are applied to MEMBERSHIP as they are written, since the working commit is the live head.

### 5.11 PRINCIPAL

Unified identity record for any actor that can modify the system. Every COMMIT and every ACTION carries an `actor_id` FK to this table, giving a complete audit trail of who changed what.

`principal_type` values:

| Type | Description |
|---|---|
| `user` | A human authenticated via an external OIDC provider |
| `service_agent` | A named autonomous process (ingestion pipeline, ML agent, etc.) |

Fields: `principal_id`, `principal_type`, `display_name`, `is_active`.

`PRINCIPAL.principal_type` is the polymorphic discriminator. Type-specific fields are stored in the joined `USER` or `SERVICE_AGENT` table.

#### 5.11.1 USER

A human principal authenticated through an external OpenID Connect (OIDC) identity provider such as Keycloak or Auth0. The user record is created or refreshed on first token verification.

Fields (extends PRINCIPAL): `principal_id`, `external_subject`, `external_issuer`, `email`.

- `external_subject`: the OIDC `sub` claim — stable, provider-scoped user identifier.
- `external_issuer`: the OIDC `iss` claim — identifies the identity provider.
- Together `(external_subject, external_issuer)` forms a globally unique identity key across multiple IdPs.
- `email` is optional; sourced from the OIDC `email` claim when present.

#### 5.11.2 SERVICE_AGENT

An autonomous process principal. Agents are pre-registered and identified by a unique `agent_slug` following the convention `<category>:<name>`, for example:

| Slug | Category | Description |
|---|---|---|
| `system:kramerius-ingest` | `system` | Kramerius document ingestion pipeline |
| `agent:face-detector-v2` | `agent` | Face detection ML model, version 2 |
| `agent:ner-extraction` | `agent` | Named-entity recognition pipeline |
| `pipeline:authority-sync` | `pipeline` | Periodic authority record synchronisation |

Fields (extends PRINCIPAL): `principal_id`, `agent_slug`, `agent_version`, `description`.

- `agent_slug`: unique human-readable identifier, format `<category>:<name>`.
- `agent_version`: optional semantic version string tied to the model or code version that produced the records (enables staleness detection).
- `description`: optional free-text description of the agent's purpose.

