# A product for PeopleGator API: General overview of basic functionalities

## 1. Introduction
The PeopleGator API is designed to enable effective person-centric search and retrieval across Czech libraries. The central unit is an **information cluster** — a grouping of typed evidence items (name mentions, face detections, authority records, biographical text, photos, etc.). A person **emerges** from the evidence gathered in their information cluster.

We also manage the dataset of clusters and allow users to automatically, semi-automatically, or manually change evidence within clusters. This includes adding and removing evidence items from clusters, merging clusters, and splitting clusters. The API also allows multiple parallel instance branches of the same cluster to be presented so that annotators can independently work on the same person and reviewers can evaluate how people agree on evidence about the same person.

Each evidence item has both a type but also a source metadata. which links it for physical sources as books, urls and other documents. Thus app has a simple interface for source data management and tracking of processing state for each source.

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


### 1.2 Operations defined on top of information clusters and evidence
1. Create a new information cluster, just an identifier with info about its head instance.
2. Add evidence items to an information cluster instance.
3. Remove evidence items from an information cluster instance.
4. Merge two or more information cluster instances into one. Via:
    - Union of all evidence items from the merged clusters.
    - Intersection of all evidence items from the merged clusters.
    - Disambiguated join of all evidence items from the merged clusters (all conflicting evidence is resolved prior to merging).
5. Split an information cluster instance into multiple instances with new cluster identifiers.
6. Next operation to create a edge beween two cluster instances, and to deine instance linieage or branching.

Uppon a instance operation the instance becomes immutable to preserve the history.

Evidence operation are append-only, if once a evidence is added/removed the operation cannot be undone.

Cluster Instance operation are thus separated into two categories:
- **Data transferable** operations: union, intersection, disambiguated join, nex. The result is always a product of members from two or more instances. How is defined by the type of operation.
- **Data non-transferable** operations: split. The members are defined in resulting instances.

### 1.3 So what is the source?
1. Saves information about some abstract form of the data e.g.:
    - a page in a book... `{'library': 'xyz'; 'document': 'abc'; 'page': 123}`
    - a unique wikidata identifier of a person... `{'wikidata': 'Q12345'}`
    - a wikidata name of a person... `{'wikidata': 'Q12345'; 'name': 'John Doe'}`
    - and possibly others...
2. Saves metadata about where the actual source was gathered from e.g.:
    - a url... `{'url': 'https://api.kramerius.mzk.cz/search/iiif/uuid:91493cea-563c-4e9e-96da-284cc7264914/full/max/0/default.jpg'}`
    - a file in the filesystem... `{'file': '/data/images/91493cea-563c-4e9e-96da-284cc7264914.jpg'}`
    - a row from csv table... `{'csv': 'data.csv'; 'row': 123}`
3. Now both the physical-abstract source have to have a schema that defines a mapping that will give a mapping


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
| `head_instance_id` | UUID or NULL | Identifier of the head instance of the cluster or none if cluster is irrelevant. |
| `principal_id` | UUID | [UUIDv6](#20-ids) of the [PRINCIPAL](#27-principal-principal) who created the cluster. |

Constraints:
- `head_instance_id` must be an instance that belongs to the cluster.

Indices:
- `cluster_id`
- `head_instance_id`
- `principal_id`

### 2.2 Information Cluster Instance `INSTANCE`
| Field Name | Type | Description |
|------------|------|-------------|
| `instance_id` | UUID | Unique [UUIDv6](#20-ids) time driven identifier.|
| `cluster_id` | UUID | [UUIDv6](#20-ids) of the [CLUSTER](#21-information-cluster-cluster) this instance belongs to.|
| `principal_id` | UUID | [UUIDv6](#20-ids) of the [PRINCIPAL](#27-principal-principal) who created the cluster instance. |

Indices:
- `instance_id`
- `cluster_id`
- `principal_id`

### 2.3 Evidence Item `EVIDENCE`
| Field Name | Type | Description |
|------------|------|-------------|
| `evidence_id` | UUID | [UUIDv6](#20-ids) time driven identifier if this exact evidence item. |
| `source_id` | UUID | [UUIDv6](#20-ids) of the [SOURCE](#26-source-source) this evidence item is derived from.|
| `type` | string | Type of the evidence item (e.g., name mention, face detection, physically located named entity, authority record, etc.). |
| `initial_data` | JSON | Everything about the evidence item, including its content and any additional metadata. |
| `initiator_id` | UUID | [UUIDv6](#20-ids) of the [MODEL_AGENT](#313-model-agent-model-agent) responsible for the original data in this evidence item. |
| `modified_data` | JSON or NULL | Revised data for the evidence item, if any. |
| `modifier_id` | UUID or NULL | [UUIDv6](#20-ids) of the [PRINCIPAL](#27-principal-principal) responsible for the revised data in this evidence item. |
| `deleted` | boolean or NULL | Whether this evidence item has been marked as deleted. |
| `deletor_id` | UUID or NULL | [UUIDv6](#20-ids) of the [PRINCIPAL](#27-principal-principal) responsible for marking this evidence item as deleted. |

Indices:
- `evidence_id`
- `source_id`
- `initial_data` GIN index for efficient search based on content and metadata of the evidence item.
- `initiator_id`
- `modified_data` GIN index for efficient search based on revised content and metadata of the evidence item.
- `modifier_id`
- `deletor_id`

### 2.4 Cluster Instance Modification `MODIFICATION`
| Field Name | Type | Description |
|------------|------|-------------|
| `type` | enum | Eighter of the following operations: `add_evidence` or `remove_evidence`. |
| `evidence_id` | UUID | [UUIDv6](#20-ids) of the [EVIDENCE](#23-evidence-item-evidence) item being added or removed. |
| `weight` | float | A weight associated with the modification, indicating the strength of the evidence being added or removed. This can be used to influence the scoring of clusters during search and retrieval. |
| `instance_id` | UUID | [UUIDv6](#20-ids) of the [INSTANCE](#22-information-cluster-instance-instance) this modification applies to.|
| `principal_id` | UUID | [UUIDv6](#20-ids) of the [PRINCIPAL](#27-principal-principal) responsible for this modification. |

Constraints: 
- `type`, `evidence_id`, `instance_id` (i.e., the same evidence item cannot be added or removed multiple times from the same instance).
- `instance_id` cannot be present as `operand_id` in any [OPERATION](#25-operation-on-top-of-cluster-instances-operation).

Indices:
- `evidence_id`
- `instance_id`
- `principal_id`

### 2.5 Operation on top of Cluster Instances `OPERATION`
| Field Name | Type | Description |
|------------|------|-------------|
| `result_id` | UUID | [UUIDv6](#20-ids) of the [INSTANCE](#22-information-cluster-instance-instance) resulting from this operation. |
| `operand_id` | UUID | [UUIDv6](#20-ids) of the [INSTANCE](#22-information-cluster-instance-instance) this operation is applied to. |
| `type` | enum | Eighter of the following operations: `union`, `intersection`, `disambiguated_join`, `split`, `next`. |

Constraints
- entire row is always unique (i.e., the same operation cannot be applied multiple times to the same operand instance with the same result instance).
- `result_id` is not present as `operand_id` in any different [OPERATION](#25-operation-on-top-of-cluster-instances-operation) (i.e., the operation result in directed acyclic graph).
- `type`, `result_id` (i.e., .e.g., the same instance cannot be the result of multiple different operations).
- For different `types` of operations:
    - `union`, `intersection`, `disambiguated_join`: `operand_id` is always different for same `type` and `result_id`.
    - `split`: `result_id` is different for same `type` and `operand_id` (i.e., the same instance can be split into multiple different instances). `operand_id` has different `cluster_id` than `result_id` (i.e., the resulting instance belongs to a different cluster than the operand instance).
    - `next`: `operand_id` is always same but `result_id` is different for same `type` (i.e., the same instance can have multiple different next instances). `operand_id` has same `cluster_id` as `result_id` (i.e., the resulting instance belongs to the same cluster as the operand instance).

Indices:
- `result_id`
- `operand_id`
- `type`

### 2.6 Source `SOURCE`
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

### 2.7 Principal `PRINCIPAL`
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
| `source` | enum | Eighter of the following targets: `evidence`, `source`. |
| `source_type` | enum | Joined enum of evidence and source types defines what type of sources this model can process eg `book_page`, `wikidata_entity`, etc. |
| `target` | enum | Eighter of the following targets: `evidence`, `embedding`. |
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
| `state` | enum | Eighter of the following states: `pending`, `processing`, `completed`, `failed`. |
| `evidence_id` | UUID or NULL | [UUIDv6](#20-ids) of the [EVIDENCE](#23-evidence-item-evidence) item that is derived from this source. |

Unique constraint: `source_id`, `principal_id` (i.e., the same source cannot be processed multiple times by the same principal).

### 3.3 Membership of all evidence items in cluster instances `MEMBERSHIP`
> To make the current state of all cluster instances materialized.

| Field Name | Type | Description |
|------------|------|-------------|
| `instance_id` | UUID | [UUIDv6](#20-ids) of the [INSTANCE](#22-information-cluster-instance-instance) this membership applies to. |
| `evidence_id` | UUID | [UUIDv6](#20-ids) of the [EVIDENCE](#23-evidence-item-evidence) item that is a member of the instance. |
| `weight` | float | A weight associated with the membership, indicating the strength of the evidence's association with the instance. This can be used to influence the scoring of clusters during search and retrieval. |

## 4. Vector Search Architecture
The general principles defined in this section can be applied to any kind of vector documesnt store db, that is able to have multiple vector indicies for same document, mainly to handle different.

### 4.1 What to store and how?
The major challange is that we have evidence and we can embed it. Now what should be stored in the vector database? The decision is mainly guided by few principles:
1. Can database handle only vectors? 
2. Can there be more vectors per record?
3. Can DB store additional data?

The answers then guide the design of structures stored in the db. In general we want to make as little as possible roundtrips to vector db and relational db. Thus our ideal db such as [weaviate](https://weaviate.io/) or [qdrant](https://qdrant.tech/) allow us to store both multiple vectors and metadata.

Multiple vectors allow multi-versioned sotrage of processed vectors.

Medatada allow efficient faceting and grouping of results.

### 4.2 Storage Document Structure
Each evidence items is stored as a document in the vector database with the following structure:

| Field Name | Type | Description |
|------------|------|-------------|
| `evidence_id` | UUID | [UUIDv6](#20-ids) of the [EVIDENCE](#23-evidence-item-evidence) item this document represents. |
| `instance_id` | list[UUID] | | List of [UUIDv6](#20-ids) of the [INSTANCE](#22-information-cluster-instance-instance) this evidence item is a member of. |
| `type` | string | Type of the evidence item (e.g., name mention, face detection, physically located named entity, authority record, etc.). |
| `initial_data` | JSON | Metadata from `initial_data` of [EVIDENCE](#23-evidence-item-evidence) item. |
| `modified_data` | JSON or NULL | Metadata from `modified_data` of [EVIDENCE](#23-evidence-item-evidence) item, if any. |
| `abstract_source` | JSON | Metadata `abstract_source` from relevant [SOURCE](#26-source-source) items. |

Each evidence item then has zero or more named vectors that in the names point to [MODEL_AGENT](#313-model-agent-model-agent)s `slug` that created the vector. Dimensionality of vector is diven by the model used.


Additionaly if vector db allows efficiet fintering of related idem, the materialized membership of evidence items can be stored as `cluster_id` and list of `evidence_id` of all items in the cluster.

## 4.3 Search and Retrieval
The search and retrieval is a bit more complicated. Because we have these issues to solve:
1. We have multiple source query vectors, see [1.1 The API provides an interface for](#11-the-api-provides-an-interface-for) for reference. Meaning:
    - We have to fuse per-modality results from vector db.
2. We want to retireve scored information clusters, which are also **filtered** [1.1 The API provides an interface for](#11-the-api-provides-an-interface-for) for reference. Meaning:
    - We have to aggregate evidence item scores into cluster scores.
3. After the two previous problms are solve. The single modality search becomes trivial. 


### 4.3.1 General Search and Retrieval Procedure
0. Initialize collector for clusters and query pointers e.g. `clusters = {}` and `last_evidences = {}`.
1. The query is processed by relevant [MODEL_AGENT](#313-model-agent-model-agent)s to create one or more query vectors. Or if applicable the query is gathered from database documetn of specific [EVIDENCE](#23-evidence-item-evidence).
2. Each `query_vector` is associated with its `type` and unique `evidence_id` (either created or retrieved).
3. For each `query_vector` and `type` of query vector and unique query `evidence_id` do:
    1. If the vector db does support it. A query is enriched with user-specified filters that filter any metadata.
    2. The vector db is queried to retrive top-k most similar evidence of the same `type`.
    3. Evidence items and their IDs are retrieved from the vector db.
    5. Last `evidence_id` is saved as a pointer for pagination e.g. `last_evidences[evidence_id] = evidence_id`.
    6. The main db is queried to retrieve `cluster_id` if evidence is in `head_instance_id` of any [CLUSTER](#21-information-cluster-cluster), also `weight` of association is retrieved.
    7. Only evidence that is a member of the cluster instance is kept, the rest is filtered out.
    8. For each `evidence_id`, `query_vector` and `cluster_id` of retrieved evidence item the following is done:
        1. Create mapping of modalities for `cluster_id` if this list does not exist e.g. `clusters[cluster_id] = {}`.
        2. Create a mapping `cluster_id` under key of `type` for evidences if it does not exist e.g. `clusters[cluster_id][type] = {}`.
        3. Create a list of evidence items int the clusters-moadlity-evidence mapping if it does not exist e.g. `clusters[cluster_id][type][query.evidence_id] = []`.
        3. Add retrieved `evidence_id` to the list of evidence items of `type` for `cluster_id` e.g. `clusters[cluster_id][type][query.evidence_id].append({'evidence_id': evidence_id, 'score': score, 'weight': weight})`.
4. Chech size of `clusters` mapping and if it is larger than `k`. If not repeat step 3 with pointer starting from `last_evidences`.
5. Optionally enrich clusters with similarities of other evidence items associated with the head instance of the cluster.
6. Foe each cluster and moalyty, apply fusion strategy to get single score for the modality for the cluster.
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
| `strategy` | enum | Eighter of the following strategies: `max`, `average`, `weighted_average`, `reciprocal_rank_fusion`, `comb_sum`, `comb_mnz`, `borda_count`. |
| `configuration` | JSON | Configuration for the fusion strategy, such as weights for the weighted average strategy. |

Indices:
- `profile_id`
- `principal_id`


