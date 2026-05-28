# People Gator Product Specification

## 1. Purpose

People Gator API is an backend for person-centric retrieval an person cluster annotation in historical document scans.

Main workflow:
1. Search returns ranked information clusters — groupings of face detections, name mentions, and authority records that speak to the same person.
2. Annotators confirm, extend, or reject proposed clusters.
3. Annotator can search similar looking units (faces, names, authority records, paragraphs..) to find additional evidence and add to the cluster.
5. Annotators can merge clusters they believe to be the same person, or can create new clusters if they believe no existing cluster matches.
4. Reviewed clusters are promoted to grounded clusters and linked to master entity records.

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
  - Search query is defined as a set of weighted signals (face similarity, name similarity, authority link strength, etc.), meaning it itself is a information cluster.
  - Any person evidence that is grouped together in a cluster.
  - Search can return similarity-ranked clusters.
  - Search can return individual records, their cluster lineage is optional.
2. Typed canonical records: every atomic evidence item preserves typed metadata, and lineage information.
  - Typed metadata enables modality-specific search signals and faceting. 
  - Lineage tells about the source of data. It is critical for provenance, trust, and interpretability.
3. Explainable ranking: every cluster result includes per-modality signal contributions, extensive info enables per member analysis.
4. Human-in-the-loop user workflows: search
4. Human-in-the-loop user workflows: annotation
  - A annotation instance of cluster gets created to be assigned to an annotator. It pins to a specific cluster version at assignment time.
  - Annotator can add, remove, cluster members, which modifies the branched off version.
  - Annotator can modify other clusters uppon which the cluster automatically branches off a new version, but the annotation instance remains pinned to the original version.
  - Annotator can submit the annotation instance.
  - Annotator can create a new proposed cluster from scratch if they believe no existing cluster matches.
4. Human-in-the-loop user workflows: review
  - Branched off versions from annotation are visible to reviewers.
  - Reviewer can chhose what changes from the proposed cluster to accept, which creates a new version with those changes.
  - Reviewer decisions trigger new cluster version creation. Annotation instances are pinned to the original version, then become immutable.
  - Reviewer can change `proposed_cluster` role to `grounded_cluster` if they believe the proposed cluster is well supported, which creates a new version with that role.
5. Separation of concerns: this service ingests and reasons over artifacts; inference remains external.
  - This service does not perform OCR, face detection, NER, embedding generation, or authority linking. It only ingests the outputs of those processes as typed records.
  - This service does not train or serve any models. It only stores the model version used to generate each record and uses that for staleness detection.
  - This service does not perform live authority lookups. It only ingests authority records from periodic syncs and links them to clusters, via exposed APIs for data access.

## 5. Canonical Types

### 5.1 RECORD

The unified atomic evidence unit. Every piece of evidence — face detections, name mentions, text regions, photos, and authority data — is a RECORD.

Required fields: `record_id`, `timestamp`, `record_type`, `content_hash`, `source_provider`, `source_schema`, `source`, `metadata_schema`, `metadata`, `storage_location`.


The `timestamp` with `record_id` forms a unique identifier for each version of a record. When a record is updated (e.g., a face detection is refined with a new bounding box), a new RECORD row is created with the same `record_id` but a later `timestamp`, preserving the full version history.

Record types include: `face_detection`, `named_entity`, `text`, `grounded_name`, `alternative_grounded_name`, `description`, `authority_record`, etc. 

The `metadata` field is a JSON blob with schema defined by `metadata_schema` that preserves typed information about the record (e.g., for a face detection, bounding box coordinates, detection confidence, and embedding vector reference, each has some class that defines this schema).

The `source` field is a JSON blob defined by `source_schema` that preserves provenance information about the record (e.g., for a face detection, the source might be `page_id`, `line_id`, and `face_index` on that line, which allows us to link back to the original scan and display in context).

The `content_hash` is a hash of the content that defines the record's identity for deduplication and staleness detection. For a face detection, this might be a hash of the image crop pixels and the embedding vector.

The `model_version` is stored in the `metadata` for records generated by inference, enabling staleness detection when a new model version is released.

### 5.2 LOGICAL_CLUSTER

Stable identity for a cluster across its version history.

Fields: `cluster_id`, `cluster_role`, `created_at`.

`cluster_role` values:

| Role | Created by |
|---|---|
| `authority_cluster` | Authority sync (Wikidata, NKCR import) |
| `proposed_cluster` |  A cluster that is proposed automatically or by an annotator |
| `grounded_cluster` | Reviewer promotion of a `proposed_cluster` |
| `derived_cluster` | Product of split | 
| `search_cluster` | Product of user initiated search |


### 5.3 CLUSTER_VERSION

One immutable version within a lineage. Created by copy-on-write on any membership change.

Fields: `cluster_id`, `cluster_role`, `parent_timestamp`, `branch_id`, `timestamp`,  `writable`, `created_by`.

The `cluster_role` is inherited from the lineage's `initial_cluster_role` but can be changed by reviewers (e.g., a `proposed_cluster` can become a `grounded_cluster` upon review).

The `parent_timestamp` points to the previous version in the lineage, enabling reconstruction of the full version history.

The `branch_id` allows us to track divergent versions that arise from concurrent edits (e.g., two annotators editing the same cluster at the same time), enabling merge workflows and conflict resolution. The main branch is `0`, and divergent branches get incrementing positive integers.

The `timestamp` is the creation time of this version, used for ordering and staleness detection.

Conditions to work with cluster versions:
- Get current `cluster_role`:
    - Sort by `timestamp` descending, 
    - Get the first `cluster_role`
    - If none found, default to lineage's `initial_cluster_role`.

### 5.4 CLUSTER_ITEM

Associates a RECORD with a specific CLUSTER version using delta semantics.

Links: `cluster_id`, `parent_timestamp`, `branch_id` from CLUSTER, to `record_id`, `timestamp` from RECORD.

Fields: `cluster_id`, `parent_timestamp`, `branch_id`, `timestamp`, `action_type` (add/remove), `record_id`, `record_timestamp`, `created_by`.


Cluster item can be added or removed from a branched off version without affecting the parent version.

Any changes with timestamp above latest cluster branch timestamp are uncommited changes. Upon submission new cluster version is created with head timestamp equal to the latest uncommited change timestamp.

Condition to get state of current branch:
- Parent cluster items:
    - `cluster_id` matches
    - `branch_id` `==` `0`
    - `timestamp` is `<=` the `parent_timestamp`
- Changes commited to the branch:
    - `cluster_id` matches
    - `branch_id` matches
    - `CLUSTER_ITEM.timestamp` is `<` the `CLUSTER_COMMIT.timestamp`
- Uncommited changes:
    - `cluster_id` matches
    - `branch_id` matches
    - `CLUSTER_ITEM.timestamp` is `>` the `CLUSTER_COMMIT.timestamp`
- Finally postprocess:
    - Sort by `timestamp` ascending.
    - From first to last, apply add/remove actions to get the final cluster state.

### 5.5 ACTION

Immutable log of all user actions for changes to clusters and records.
Fields: `action_id`, `timestamp`, `user_id`, `action_type`, `action_details`.
