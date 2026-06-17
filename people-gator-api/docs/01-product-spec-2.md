# A product for PeopleGator API: General overview of basic functionalities

## 1. Introduction
The PeopleGator API is designed to enable effective person-centric search and retrieval across Czech libraries. The central unit is an **information cluster** — a grouping of typed evidence items (name mentions, face detections, authority records, biographical text, photos, etc.). A person **emerges** from the evidence gathered in their information cluster.

We also manage the dataset of clusters and allow users to automatically, semi-automatically, or manually change evidence within clusters. This includes adding and removing evidence items from clusters, merging clusters, and splitting clusters. The API also allows multiple parallel version branches of the same cluster to be presented so that annotators can independently work on the same person and reviewers can evaluate how people agree on evidence about the same person.

Each evidence item has both a type but also a source metadata. which links it to physical sources such as books, urls and other documents. Thus the app has a simple interface for source data management and tracking of processing state for each source.

### 1.1 The API provides an interface for:
1. Search for information clusters based on similarity to query containing any number of the following evidence items:
    - name, fullname, alt-name, nickname
    - description, biography, occupation
    - photo, face similarity
3. Retrieve any additional evidence items that may support the found cluster and are similar to the query. We have evidence of following types:
    - text
       - name
       - alt-name
       - description
       - paragraph
       - line
       - named-entity
    - face-detection


### 1.2 Version Control Model

The API implements **stateless version control** for information clusters. This means:

1. **Versions are immutable snapshots** — once created, a version cannot be modified. It represents a fixed point in the cluster's evolution.
2. **Deltas are stateless modifications** — deltas can be applied on top of any version to propose changes, but they never modify the base version itself.
3. **Commits create new versions** — when deltas are acknowledged via a commit operation, a new immutable version is created with those changes applied.
4. **Parallel branches are supported** — multiple independent delta sets can be applied to the same base version, enabling collaborative annotation and experimentation.

#### Core Principles:
- **Immutability**: Every version is permanent and cannot be altered after creation.
- **Statelessness**: Deltas exist independently and can be applied to any version without locking or mutating the base.
- **Traceability**: All operations preserve complete lineage — which version was the parent, which deltas were applied, and what the result is.
- **Append-only history**: The version graph only grows; no version or delta is ever deleted.

### 1.3 Operations defined on top of information clusters and evidence

#### Version Operations:
1. **Create a new cluster** — initializes a cluster with its first version (point).
2. **Apply deltas to create a new version** — acknowledges proposed changes and creates a new immutable version.
3. **Create parallel branch** — creates an independent delta set from an existing version without committing.

#### Delta Operations (stateless, do not modify base version):
4. **Add evidence items** — propose adding evidence to a version via delta.
5. **Remove evidence items** — propose removing evidence from a version via delta.

#### Multi-Version Operations:
6. **Merge versions** — combine two or more versions into a new version via:
    - Union of all evidence items from merged versions.
    - Intersection of all evidence items from merged versions.
    - Disambiguated join (conflicts resolved prior to merge).
7. **Split a version** — create multiple new clusters from a single version, each with its own head version.
8. **Create next version** — establish lineage by creating a successor version from a single parent.

All operations preserve immutability: the source versions remain unchanged, and results are always new versions.

#### 1.3.1 Example Workflows

**Creating a new cluster with initial version:**
```
1. CREATE CLUSTER C1 → creates cluster with no versions
2. CREATE VERSION V1 (cluster_id=C1, parent=NULL) → initial version
3. CREATE DELTA D1 (version_id=V1, type=add_evidence, evidence_id=E1)
4. CREATE DELTA D2 (version_id=V1, type=add_evidence, evidence_id=E2)
5. COMMIT (base_version_id=V1, delta_ids=[D1, D2]) → creates V2
```

**Parallel branching for collaborative annotation:**
```
1. Start with VERSION V2 from CLUSTER C1
2. Annotator A creates DELTA set DA1, DA2 on V2 (not yet committed)
3. Annotator B creates DELTA set DB1 on V2 (not yet committed)
4. Annotator A commits → creates VERSION V3A
5. Annotator B commits → creates VERSION V3B
6. Both V3A and V3B have V2 as parent but are independent branches
```

**Merging parallel branches:**
```
1. Have VERSION V3A and V3B (both from same cluster C1)
2. Perform UNION operation → creates VERSION V4
3. V4 contains all evidence from both V3A and V3B
4. Update CLUSTER C1 head_version_id to V4
```


### 1.4 So what is the source?
1. Saves information about some abstract form of the data e.g.:
    - a page in a book... `{'library': 'xyz'; 'document': 'abc'; 'page': 123}`
    - a unique wikidata identifier of a person... `{'wikidata': 'Q12345'}`
    - a wikidata name of a person... `{'wikidata': 'Q12345'; 'name': 'John Doe'}`
    - and possibly others...
2. Saves metadata about where the actual source was gathered from e.g.:
    - a url... `{'url': 'https://api.kramerius.mzk.cz/search/iiif/uuid:91493cea-563c-4e9e-96da-284cc7264914/full/max/0/default.jpg'}`
    - a file in the filesystem... `{'file': '/data/images/91493cea-563c-4e9e-96da-284cc7264914.jpg'}`
    - a row from csv table... `{'csv': 'data.csv'; 'row': 123}`
3. Now both the physical and abstract source have to have a schema that defines a mapping that will give a mapping


## 2. Core Data Architecture

### 2.0 IDs
IDs are globally unique identifiers that increment in chronological order and are timestamp driven.
We use UUIDv6 as the base with a exact definition of number in the sequence and node identifier.

- `clk_seq_hi_res` (8 bits): High 8bits of per node incrementing 16bit sequence counter, reset on different timestamp.
- `clk_seq_low` (8 bits): Low 8bits of per node incrementing 16bit sequence counter, reset on different timestamp.
- `node` (48 bits): Unique node identifier, a random value initialized at node startup.


### 2.1 Information Cluster `CLUSTER`
| Field Name | Type | Description |
|------------|------|-------------|
| `cluster_id` | UUID | Unique global time driven identifier. See [UUIDv6](#20-ids) for details. |
| `head_version_id` | UUID or NULL | Identifier of the head (latest committed) [VERSION](#22-information-cluster-version-version) of the cluster or NULL if cluster has no versions yet. |
| `principal_id` | UUID | [UUIDv6](#20-ids) of the [PRINCIPAL](#28-principal-principal) who created the cluster. |

Constraints:
- `head_version_id` must be a version that belongs to the cluster.

Indices:
- `cluster_id`
- `head_version_id`
- `principal_id`

### 2.2 Information Cluster Version `VERSION`
> A version is an immutable snapshot of a cluster at a point in time. It cannot be modified after creation.

| Field Name | Type | Description |
|------------|------|-------------|
| `version_id` | UUID | Unique [UUIDv6](#20-ids) time driven identifier.|
| `cluster_id` | UUID | [UUIDv6](#20-ids) of the [CLUSTER](#21-information-cluster-cluster) this version belongs to.|
| `principal_id` | UUID | [UUIDv6](#20-ids) of the [PRINCIPAL](#27-principal-principal) who created this version (via commit). |
| `parent_version_id` | UUID or NULL | [UUIDv6](#20-ids) of the parent [VERSION](#22-information-cluster-version-version) this version was derived from, or NULL for initial versions. |
| `operation_type` | enum or NULL | Type of operation that created this version: `apply`, `union`, `intersection`, `disambiguated_join`, `split`, `parallel`, or NULL for initial versions. |

Indices:
- `version_id`
- `cluster_id`
- `parent_version_id`
- `principal_id`

### 2.3 Cluster Delta `DELTA`
> Deltas are stateless modifications that propose changes to a version. They do not modify the base version and can be applied to any version.

| Field Name | Type | Description |
|------------|------|-------------|
| `delta_id` | UUID | Unique [UUIDv6](#20-ids) time driven identifier.|
| `version_id` | UUID | [UUIDv6](#20-ids) of the [VERSION](#22-information-cluster-version-version) this delta is applied on top of.|
| `type` | enum | Either `add_evidence` or `remove_evidence`. |
| `evidence_id` | UUID | [UUIDv6](#20-ids) of the [EVIDENCE](#24-evidence-item-evidence) item being added or removed. |
| `weight` | float | A weight associated with the delta, indicating the strength of the evidence being added or removed. |
| `principal_id` | UUID | [UUIDv6](#20-ids) of the [PRINCIPAL](#27-principal-principal) who created this delta. |

Constraints: 
- Unique constraint on (`version_id`, `type`, `evidence_id`) — the same evidence cannot be added/removed multiple times via deltas to the same version.

Indices:
- `delta_id`
- `version_id`
- `evidence_id`
- `principal_id`

### 2.4 Evidence Item `EVIDENCE`
> Evidence is any detection, ner etc. It can be modified, but existing records are imutable. Thus a new version has to be created.

| Field Name | Type | Description |
|------------|------|-------------|
| `version_id` | UUID | [UUIDv6](#20-ids) time driven identifier created every time a new version is created. |
| `evidence_id` | UUID | [UUIDv6](#20-ids) time driven unique identifier for this evidence item. |
| `source_id` | UUID | [UUIDv6](#20-ids) of the [SOURCE](#26-source-source) this evidence item is derived from.|
| `type` | string | Type of the evidence item (e.g., name mention, face detection, physically located named entity, authority record, etc.). |
| `initial_data` | JSON | Everything about the evidence item, including its content and any additional metadata. |
| `initiator_id` | UUID | [UUIDv6](#20-ids) of the [MODEL_AGENT](#313-model-agent-model-agent) responsible for the original data in this evidence item. |
| `modified_data` | JSON or NULL | Revised data for the evidence item, if any. |
| `modifier_id` | UUID or NULL | [UUIDv6](#20-ids) of the [PRINCIPAL](#27-principal-principal) responsible for the revised data in this evidence item. |
| `deleted` | boolean or NULL | Whether this evidence item has been marked as deleted. |
| `deletor_id` | UUID or NULL | [UUIDv6](#20-ids) of the [PRINCIPAL](#27-principal-principal) responsible for marking this evidence item as deleted. |

Indices:
- `version_id`
- `evidence_id`
- `source_id`
- `initial_data` GIN index for efficient search based on content and metadata of the evidence item.
- `initiator_id`
- `modified_data` GIN index for efficient search based on revised content and metadata of the evidence item.
- `modifier_id`
- `deletor_id`

### 2.5 Cluster Version Commit `COMMIT`
> A commit acknowledges deltas applied to a base version and creates a new immutable version. This is the only way to create new versions from deltas.

| Field Name | Type | Description |
|------------|------|-------------|
| `commit_id` | UUID | Unique [UUIDv6](#20-ids) time driven identifier.|
| `result_version_id` | UUID | [UUIDv6](#20-ids) of the new [VERSION](#22-information-cluster-version-version) created by this commit. |
| `base_version_id` | UUID | [UUIDv6](#20-ids) of the base [VERSION](#22-information-cluster-version-version) that deltas were applied to. |
| `principal_id` | UUID | [UUIDv6](#20-ids) of the [PRINCIPAL](#27-principal-principal) who executed this commit. |
| `delta_ids` | JSON | List of [UUIDv6](#20-ids) of all [DELTA](#23-cluster-delta-delta) records acknowledged by this commit. |

Constraints:
- `result_version_id` must be unique and must reference a valid VERSION.
- `base_version_id` cannot equal `result_version_id` (a version cannot be its own parent).
- All `delta_ids` must reference deltas that have `version_id` equal to `base_version_id`.

Indices:
- `commit_id`
- `result_version_id`
- `base_version_id`
- `principal_id`

### 2.6 Version Lineage Operation `VERSION_OPERATION`
> Tracks how versions are related through multi-version operations (union, intersection, split, etc.).

| Field Name | Type | Description |
|------------|------|-------------|
| `operation_id` | UUID | Unique [UUIDv6](#20-ids) time driven identifier.|
| `result_version_id` | UUID | [UUIDv6](#20-ids) of the [VERSION](#22-information-cluster-version-version) resulting from this operation. |
| `operand_version_id` | UUID | [UUIDv6](#20-ids) of the [VERSION](#22-information-cluster-version-version) this operation is applied to. |
| `type` | enum | One of: `union`, `intersection`, `disambiguated_join`, `split`, `parallel`. |

Constraints:
- Unique constraint on (`result_version_id`, `operand_version_id`, `type`).
- `result_version_id` cannot appear as `operand_version_id` in any other operation (ensures DAG structure).
- For `union`, `intersection`, `disambiguated_join`: `operand_version_id` must be different for same `type` and `result_version_id`.
- For `split`: `result_version_id` must be different for same `type` and `operand_version_id`. The resulting version has different `cluster_id` than operand (creates new cluster).
- For `parallel`: creates independent branch from same cluster. Result has same `cluster_id` as operand.

Indices:
- `operation_id`
- `result_version_id`
- `operand_version_id`
- `type`

#### 2.6.1 Thorough description of operation `split`
The `split` operation creates new clusters from an existing version. The process:
1. Start with [VERSION](#22-information-cluster-version-version) `A` from cluster `X`.
2. Create new clusters `B1`, `B2`, ..., `Bn` (each with new `cluster_id`).
3. For each new cluster, create an initial version with `parent_version_id` = `A.version_id` and `operation_type` = `split`.
4. Create deltas for each new version according to split logic (which evidence goes to which cluster).
5. Commit the deltas to create fixed versions for each new cluster.
6. Record [VERSION_OPERATION](#26-version-lineage-operation-version_operation) with `type` = `split`, `operand_version_id` = `A`, and `result_version_id` = each new version.


### 2.7 Source `SOURCE`
| Field Name | Type | Description |
|------------|------|-------------|
| `source_id` | UUID | Unique [UUIDv6](#20-ids) time driven identifier.|
| `abstract_type` | string | Type of the source (e.g., book, authority, wikidata_entity, etc.). |
| `abstract_source` | JSON | Metadata about the abstract source (e.g., a page in a book, a unique Wikidata identifier, etc.). |
| `gathered_type` | string | Type of method used to gather the source (e.g., manual annotation, automated extraction, etc.). |
| `gathered_source` | JSON | Metadata about where the actual source was gathered from (e.g., a URL, a file in the filesystem, etc.). |
| `principal_id` | UUID | [UUIDv6](#20-ids) of the [PRINCIPAL](#27-principal-principal) responsible for gathering this source. |

Constraints:
- `source_id` is unique across all sources.

Indices:
- `source_id`

### 2.8 Principal `PRINCIPAL`
> I.e. anything that modifies anything else in the system.

| Field Name | Type | Description |
|------------|------|-------------|
| `principal_id` | UUID | Unique [UUIDv6](#20-ids) time driven identifier.|
| `type` | string | Type of the principal (e.g., user, service_agent, model_agent, etc.). |
| `role` | string | Role of the principal (e.g., annotator, reviewer, processor, administrator, etc.). |

## 3. Extended Data Architecture

### 3.1 Concrete Types of Principal as Tables
> To define exact type syntax for all types of principals.

#### 3.1.1 User `USER`
> Simple OIDC based user.

| Field Name | Type | Description |
|------------|------|-------------|
| `principal_id` | UUID | Exact as in [PRINCIPAL](#27-principal-principal).|
| `oidc_id` | string | OpenID Connect identifier of the user. |


#### 3.1.2 Service Agent `SERVICE_AGENT`
> Anything that automatically works with the database.

| Field Name | Type | Description |
|------------|------|-------------|
| `principal_id` | UUID | Exact as in [PRINCIPAL](#27-principal-principal).|
| `name` | string | Name of the service agent. |
| `git` | string | URL of the service agent's code repository. |
| `branch` | string | Branch of the service agent's codebase. |
| `commit` | string | Commit hash of the service agent's codebase. |


#### 3.1.3 Model Agent `MODEL_AGENT`
> The definition mainly says, ok this model can process this modality/modalities of evidence or sources.

| Field Name | Type | Description |
|------------|------|-------------|
| `principal_id` | UUID | Exact as in [PRINCIPAL](#27-principal-principal).|
| `source` | enum | Either of the following targets: `evidence`, `source`. |
| `source_type` | enum | Joined enum of evidence and source types defines what type of sources this model can process eg `book_page`, `wikidata_entity`, etc. |
| `target` | enum | Either of the following targets: `evidence`, `embedding`. |
| `slug` | string | Unique slug of the model agent. |
| `registry_type` | string | Name of the model used by the agent. |
| `registry_url` | string | URL of the model registry. |
| `registry_version` | string | Version of the model used by the agent. |

Constraints:
- `source`, `target` (i.e., the same model agent cannot process both evidence and sources, or produce both evidence and embeddings).
- `source_type` must be consistent with the defined types of sources and evidence items in the system (e.g., if `source` is `source`, then `source_type` must be one of the defined source types such as `book_page`, `wikidata_entity`, etc.; if `source` is `evidence`, then `source_type` must be one of the defined evidence types such as `name_mention`, `face_detection`, etc.).

### 3.2 Source Processing to Create Evidence `SOURCE_PROCESSING`

| Field Name | Type | Description |
|------------|------|-------------|
| `processing_id` | UUID | Unique [UUIDv6](#20-ids) time driven identifier.|
| `source_id` | UUID | [UUIDv6](#20-ids) of the [SOURCE](#26-source-source) this processing applies to. |
| `principal_id` | UUID | [UUIDv6](#20-ids) of the [PRINCIPAL](#27-principal-principal) responsible for this processing. |
| `state` | enum | Either of the following states: `pending`, `processing`, `completed`, `failed`. |
| `evidence_id` | UUID or NULL | [UUIDv6](#20-ids) of the [EVIDENCE](#23-evidence-item-evidence) item that is derived from this source. |

Unique constraint: `source_id`, `principal_id` (i.e., the same source cannot be processed multiple times by the same principal).

### 3.4 Membership of Evidence Items in Cluster Versions `MEMBERSHIP`
> Materialized view of which evidence items belong to which cluster version. This is computed from commits and deltas, but stored for efficient querying.

| Field Name | Type | Description |
|------------|------|-------------|
| `version_id` | UUID | [UUIDv6](#20-ids) of the [VERSION](#22-information-cluster-version-version) this membership applies to. |
| `evidence_id` | UUID | [UUIDv6](#20-ids) of the [EVIDENCE](#24-evidence-item-evidence) item that is a member of the version. |
| `weight` | float | A weight associated with the membership, indicating the strength of the evidence's association with the version. This can be used to influence the scoring of clusters during search and retrieval. |

Constraints:
- Unique constraint on (`version_id`, `evidence_id`) — same evidence cannot appear multiple times in same version.

Indices:
- `version_id`
- `evidence_id`

> **Note**: Membership is derived from the commit history. When a commit is created, it applies all referenced deltas to the base version's membership to produce the new version's membership. This table provides a materialized view for efficient querying.

## 4. Vector Search Architecture
The general principles defined in this section can be applied to any kind of vector documesnt store db, that is able to have multiple vector indicies for same document, mainly to handle different.

### 4.1 What to store and how?
The major challenge is that we have evidence and we can embed it. Now what should be stored in the vector database? The decision is mainly guided by few principles:
1. Can database handle only vectors? 
2. Can there be more vectors per record?
3. Can DB store additional data?

The answers then guide the design of structures stored in the db. In general we want to make as little as possible roundtrips to vector db and relational db. Thus our ideal db such as [weaviate](https://weaviate.io/) or [qdrant](https://qdrant.tech/) allow us to store both multiple vectors and metadata.

Multiple vectors allow multi-versioned storage of processed vectors.

Medatada allow efficient faceting and grouping of results.

### 4.2 Storage Document Structure
Each evidence items is stored as a document in the vector database with the following structure:

| Field Name | Type | Description |
|------------|------|-------------|
| `evidence_id` | UUID | [UUIDv6](#20-ids) of the [EVIDENCE](#24-evidence-item-evidence) item this document represents. |
| `version_id` | list[UUID] | List of [UUIDv6](#20-ids) of the [VERSION](#22-information-cluster-version-version) this evidence item is a member of. |
| `type` | string | Type of the evidence item (e.g., name mention, face detection, physically located named entity, authority record, etc.). |
| `initial_data` | JSON | Metadata from `initial_data` of [EVIDENCE](#24-evidence-item-evidence) item. |
| `modified_data` | JSON or NULL | Metadata from `modified_data` of [EVIDENCE](#24-evidence-item-evidence) item, if any. |
| `abstract_source` | JSON | Metadata `abstract_source` from relevant [SOURCE](#27-source-source) items. |

Each evidence item then has zero or more named vectors that in the names point to [MODEL_AGENT](#313-model-agent-model-agent)s `slug` that created the vector. Dimensionality of vector is diven by the model used.


Additionally if vector db allows efficient filtering of related items, the materialized membership of evidence items can be stored as `cluster_id` and list of `evidence_id` of all items in the cluster.

## 4.3 Search and Retrieval
The search and retrieval is a bit more complicated. Because we have these issues to solve:
1. We have multiple source query vectors, see [1.1 The API provides an interface for](#11-the-api-provides-an-interface-for) for reference. Meaning:
    - We have to fuse per-modality results from vector db.
2. We want to retrieve scored information clusters, which are also **filtered** [1.1 The API provides an interface for](#11-the-api-provides-an-interface-for) for reference. Meaning:
    - We have to aggregate evidence item scores into cluster scores.
3. After the two previous problems are solved. The single modality search becomes trivial. 


### 4.3.1 General Search and Retrieval Procedure
0. Initialize collector for clusters and query pointers e.g. `clusters = {}` and `last_evidences = {}`.
1. The query is processed by relevant [MODEL_AGENT](#313-model-agent-model-agent)s to create one or more query vectors. Or if applicable the query is gathered from database document of specific [EVIDENCE](#24-evidence-item-evidence).
2. Each `query_vector` is associated with its `type` and unique `evidence_id` (either created or retrieved).
3. For each `query_vector` and `type` of query vector and unique query `evidence_id` do:
    1. If the vector db does support it. A query is enriched with user-specified filters that filter any metadata.
    2. The vector db is queried to retrive top-k most similar evidence of the same `type`.
    3. Evidence items and their IDs are retrieved from the vector db.
    5. Last `evidence_id` is saved as a pointer for pagination e.g. `last_evidences[evidence_id] = evidence_id`.
    6. The main db is queried to retrieve `cluster_id` if evidence is in the head [VERSION](#22-information-cluster-version-version) of any [CLUSTER](#21-information-cluster-cluster), also `weight` of association is retrieved.
    7. Only evidence that is a member of the cluster version is kept, the rest is filtered out.
    8. For each `evidence_id`, `query_vector` and `cluster_id` of retrieved evidence item the following is done:
        1. Create mapping of modalities for `cluster_id` if this list does not exist e.g. `clusters[cluster_id] = {}`.
        2. Create a mapping `cluster_id` under key of `type` for evidences if it does not exist e.g. `clusters[cluster_id][type] = {}`.
        3. Create a list of evidence items in the clusters-modality-evidence mapping if it does not exist e.g. `clusters[cluster_id][type][query.evidence_id] = []`.
        3. Add retrieved `evidence_id` to the list of evidence items of `type` for `cluster_id` e.g. `clusters[cluster_id][type][query.evidence_id].append({'evidence_id': evidence_id, 'score': score, 'weight': weight})`.
4. Check size of `clusters` mapping and if it is larger than `k`. If not repeat step 3 with pointer starting from `last_evidences`.
5. Optionally enrich clusters with similarities of other evidence items associated with the head version of the cluster.
6. For each cluster and modality, apply fusion strategy to get single score for the modality for the cluster.
7. For each cluster, apply fusion strategy to get single score for the cluster.
8. Sort clusters by their score and return top-k.

### 4.3.2 Fusion Strategies
I mean we have defined what we get from the pure db search so here are a just to remind here is pydantic model of what we get from the db search:

```python
class RetrievedEvidenceItem(BaseModel):
    evidence_id: UUID
    score: float
    weight: float

class ClusterModalityEvidence(BaseModel):
    query_evidence_id: UUID
    evidence_items: List[RetrievedEvidenceItem]

class ClusterEvidence(BaseModel):
    cluster_id: UUID
    modalities: dict[str, dict[UUID, ClusterModalityEvidence]]
```

The fusion strategies can be defined as follows:
1. **Max**: The score of the cluster for a modality is the maximum similarity score among all evidence items of that modality in the cluster.
2. **Average**: The score of the cluster for a modality is the average similarity score among all evidence items of that modality in the cluster.
3. **Weighted Average**: The score of the cluster for a modality is the weighted average similarity score among all evidence items of that modality in the cluster, where weights can be defined based on the relevance of the evidence items or other criteria.
4. **Reciprocal Rank Fusion**: The score of the cluster for a modality is calculated based on the ranks of the evidence items in the retrieved list, giving higher weight to items that are ranked higher.
5. **CombSUM**: The score of the cluster for a modality is the sum of the similarity scores of all evidence items of that modality in the cluster.
6. **CombMNZ**: The score of the cluster for a modality is the sum of the similarity scores of all evidence items of that modality in the cluster multiplied by the number of evidence items of that modality in the cluster.
7. **Borda Count**: The score of the cluster for a modality is calculated based on the ranks of the evidence items, where each item contributes a score based on its rank (e.g., if there are N items, the top-ranked item contributes N points, the second-ranked item contributes N-1 points, etc.).

### 4.3.3 User choice of fusion strategy
The user can specify the desired fusion strategy for each modality and for the overall cluster scoring as part of the search query parameters.

The so called `SEARCH_PROFILES` are then save to the db.

The following schema is there but fall more into userspace:

| Field Name | Type | Description |
|------------|------|-------------|
| `profile_id` | UUID | Unique [UUIDv6](#20-ids) time driven identifier.|
| `principal_id` | UUID | [UUIDv6](#20-ids) of the [PRINCIPAL](#27-principal-principal) who created this search profile. |
| `strategy` | enum | Either of the following strategies: `max`, `average`, `weighted_average`, `reciprocal_rank_fusion`, `comb_sum`, `comb_mnz`, `borda_count`. |
| `configuration` | JSON | Configuration for the fusion strategy, such as weights for the weighted average strategy. |

Indices:
- `profile_id`
- `principal_id`


