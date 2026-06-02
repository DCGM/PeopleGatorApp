# People Gator API — Functional Specification

## Overview

This document defines the functional REST API surface of the People Gator API, aligned to the data model and workflows in `01-product-spec.md`. It covers five areas in order of typical user workflow:

1. **Search** — querying across modalities, managing search profiles, faceted browsing, and retrieving similar clusters.
2. **Cluster Lifecycle** — the cluster VERSION / DELTA / OPERATION graph, MEMBERSHIP materialisation, and TASK-gated annotation and review workflows.
3. **Data Import** — ingesting sources, derived evidence, and authority evidence.
4. **Principals** — registering and querying users, service agents, and model agents.
5. **Export** — cluster state snapshots and inter-annotator agreement reports.

All identifiers are UUIDv6. All responses are JSON. Error bodies always carry a `code` (machine-readable slug) and a `message` (human-readable explanation).

---

## Authentication and Scopes

Every request must carry a bearer token issued by the configured OIDC provider. The token is validated against the JWKS endpoint on every request. The `principal_id` is resolved from the token's `(sub, iss)` claim pair and a USER row is upserted on first use.

Read-only browse endpoints (`GET /api/v1/search`, `POST /api/v1/search`, `GET /api/v1/search/facets`, `POST /api/v1/search/facets`, `GET /api/v1/clusters`, `GET /api/v1/clusters/{cluster_id}`, `GET /api/v1/clusters/{cluster_id}/membership`, `GET /api/v1/clusters/{cluster_id}/similar`, `GET /api/v1/clusters/{cluster_id}/versions`, `GET /api/v1/clusters/{cluster_id}/versions/{version_id}`) also accept unauthenticated requests, treating them as if they carry the `people-gator:browse` scope.

OIDC scopes map directly to workflow roles. Each endpoint documents the minimum scope required.

| Scope | Role |
|---|---|
| `people-gator:browse` | Anonymous or authenticated read-only access — search and cluster browsing only, no write operations |
| `people-gator:annotate` | Human annotator — search, branch, write DELTAs, manage own saved searches |
| `people-gator:review` | Reviewer — adjudicate annotation branches, run union/intersection/conflict_free_join operations, promote to `grounded_cluster` |
| `people-gator:verify` | Verifier — confirm grounding against authority records |
| `people-gator:ingest` | Ingest pipeline or service agent — register sources and evidence |
| `people-gator:admin` | Administrator — manage principals, source schemas, system profiles, assign tasks, bulk export |

Scopes are additive. An admin has all capabilities. Coarse enforcement is at route level via the FastAPI dependency layer; fine-grained TASK-based enforcement is applied in service logic.

---

## HEAD Requests and Response Headers

All `GET` endpoints implicitly support `HEAD` (RFC 9110 §9.3.2). Starlette handles this automatically — no separate route is needed. The server runs the full `GET` handler and strips the body before sending the response. The same scope rules apply to `HEAD` as to `GET`.

`ETag`, `Last-Modified`, and `Cache-Control` semantics differ by resource category:

### Immutable resources

Sealed resources that never change after creation. Strong ETag equal to the resource ID. `Last-Modified` is derived from the UUIDv6 timestamp embedded in the ID. `Cache-Control: public, max-age=31536000, immutable`.

| Endpoint | ETag source |
|---|---|
| `GET /api/v1/clusters/{cluster_id}/versions/{version_id}` | `version_id` |
| `GET /api/v1/evidence/{evidence_id}/versions/{evidence_version_id}` | `evidence_version_id` |

### Mutable single resources

Strong ETag derived from the resource's most recent change indicator. `Cache-Control: private, no-cache`. `Last-Modified` derived from the UUIDv6 timestamp in the ETag source where possible.

| Endpoint | ETag source |
|---|---|
| `GET /api/v1/search-profiles/{profile_id}` | BLAKE3 of serialised modality config |
| `GET /api/v1/clusters/{cluster_id}` | `head_version_id` |
| `GET /api/v1/clusters/{cluster_id}/membership` | `head_version_id` (or requested `version_id` if `?version_id=` is supplied) |
| `GET /api/v1/clusters/{cluster_id}/versions/{version_id}/pending` | last `delta_id` written to the version |
| `GET /api/v1/tasks/{task_id}` | `head_version_id` of the task's cluster |
| `GET /api/v1/sources/{source_id}` | `content_hash` (BLAKE3, already computed at ingest) |
| `GET /api/v1/sources/{source_id}/processing` | BLAKE3 of serialised processing status rows |
| `GET /api/v1/evidence/{evidence_id}` | latest `evidence_version_id` |
| `GET /api/v1/principals/{principal_id}` | BLAKE3 of mutable principal fields |
| `GET /api/v1/principals/me` | BLAKE3 of mutable principal fields |

### Collection (list) endpoints

Weak ETag (`W/"<last_id>"`) where `<last_id>` is the UUIDv6 ID of the most recently created item visible to the caller — the embedded timestamp gives ordering without an extra column. `Last-Modified` derived from that ID's timestamp. `X-Total-Count` carries the total count before pagination. `Cache-Control: private, no-cache`.

Polling clients can use `If-None-Match` with the weak ETag to detect new items without fetching a full body.

| Endpoint | Weak ETag source |
|---|---|
| `GET /api/v1/search-profiles` | last `profile_id` |
| `GET /api/v1/clusters` | last `cluster_id` |
| `GET /api/v1/clusters/{cluster_id}/versions` | last `version_id` |
| `GET /api/v1/clusters/{cluster_id}/versions/{version_id}/deltas` | last `delta_id` |
| `GET /api/v1/tasks` | last `task_id` |
| `GET /api/v1/source-schemas` | last schema name (alphabetical) |
| `GET /api/v1/sources` | last `source_id` |
| `GET /api/v1/evidence` | last `evidence_id` |
| `GET /api/v1/principals` | last `principal_id` |

### Ephemeral query endpoints

Results depend on query parameters and the live vector index state. No `ETag` or `Last-Modified` is emitted. `Cache-Control: no-store`. `HEAD` is still implicitly supported but provides no caching benefit.

| Endpoint |
|---|
| `GET /api/v1/search` |
| `POST /api/v1/search` |
| `GET /api/v1/clusters/{cluster_id}/similar` |
| `GET /api/v1/search/facets` |
| `POST /api/v1/search/facets` |

---

## 1. Search

### 1.1 Concepts

**Saved Search** — a search query can be persisted as a CLUSTER with `cluster_role = saved_search`. The query signals (name strings, face images, free-text snippets) are stored as EVIDENCE items subject to BLAKE3 content-hash deduplication, and referenced via DELTA entries on the initial VERSION of the cluster. An unsaved (ephemeral) query lives only in the application cache for the duration of the request. Saved-search clusters are mutable: the user can add or remove signal DELTAs, stage new VERSIONs, and update the pinned SEARCH_PROFILE — every change is audited via the VERSION/DELTA history. A saved-search cluster is promoted to an annotation target by staging a new VERSION with `cluster_role = automatic_cluster`.

**Search Profile** — a named, reusable configuration that controls which modalities (`evidence_type` values) participate in a search and how much each contributes. A profile stores per-modality weights and optional model pins via `SEARCH_PROFILE_MODALITY` rows. Profiles are owned by a user, can be marked public, or can be system-provisioned read-only defaults. When no `profile_id` is supplied to a search endpoint the system-default profile is used automatically.

**Modality** — one evidence channel, identified by its `evidence_type`. Current modalities: `face_detection`, `named_entity`, `text_region`, `grounded_name`, `grounded_description`, `authority_identifier`. Each maps to one or more named vector slots in the vector store.

**Polymorphic results** — a search can return clusters (the default), individual evidence items of any modality, or both in the same response. `result_types` in the request controls what is returned.

**Facets** — structured filter dimensions returned alongside every search response under the `facets` key. Facets show result distribution so clients can offer drill-down filtering without an extra round-trip.

---

### 1.2 Search Profiles

> **Required scope**: any authenticated user (no additional scope beyond token validity).

Search profiles define per-modality weights and model pins. They are independent of any particular query and are reused across many searches.

#### List profiles

```
GET  /api/v1/search-profiles
HEAD /api/v1/search-profiles
```

Returns all profiles visible to the calling user: their own profiles plus all public and system profiles.

| Parameter | Type | Description |
|---|---|---|
| `include_system` | bool | Include read-only system profiles. Default `true`. |
| `include_public` | bool | Include profiles owned by other users but marked public. Default `true`. |

---

#### Get a profile

```
GET  /api/v1/search-profiles/{profile_id}
HEAD /api/v1/search-profiles/{profile_id}
```

Returns full profile detail including `SEARCH_PROFILE_MODALITY` rows.

---

#### Create a profile

```
POST /api/v1/search-profiles
```

```json
{
  "profile_name": "face-heavy",
  "description": "Weights face similarity at 80 %.",
  "is_public": false,
  "modalities": [
    {
      "evidence_type": "face_detection",
      "weight": 0.8,
      "model_id": null,
      "enabled": true,
      "min_confidence": 0.6
    },
    {
      "evidence_type": "named_entity",
      "weight": 0.2,
      "model_id": null,
      "enabled": true,
      "min_confidence": null
    }
  ]
}
```

- `model_id` is an optional FK to `MODEL_AGENT.principal_id`. When null the highest-priority active MODEL_AGENT for the `evidence_type` is resolved at query time.
- `weight` values are normalised to sum to 1.0 across all enabled modalities at query time; they do not need to sum to 1.0 here.
- `min_confidence`: evidence below this detection confidence is excluded from ANN candidates before scoring. Null means no threshold.

Returns `201 Created` with the full profile and server-assigned `profile_id`.

---

#### Update a profile

```
PATCH /api/v1/search-profiles/{profile_id}
```

Partial update of `profile_name`, `description`, `is_public`, or `modalities` rows. System profiles (`is_system = true`) return `403 Forbidden`.

---

#### Delete a profile

```
DELETE /api/v1/search-profiles/{profile_id}
```

Deletes an owned, non-system profile. Returns `204 No Content`.

---

#### Clone a profile

```
POST /api/v1/search-profiles/{profile_id}/clone
```

Creates an independent copy of any visible profile owned by the requesting user. All `SEARCH_PROFILE_MODALITY` rows are copied to the new profile. No link to the source profile is retained.

Request body (optional): `{ "profile_name": "my-fork" }`.

Returns `201 Created` with the new profile.

---

### 1.3 Search Query Model

Both the GET and POST search endpoints share the same logical query model. A query is a set of typed evidence signals the caller wants to find matches for:

| Query field | Meaning |
|---|---|
| `names` | One or more name strings. Each is encoded and stored/deduped as a `named_entity` EVIDENCE item and contributes a signal in the `text` vector space. |
| `texts` | One or more free-text snippets. Each is encoded and stored/deduped as a `text_region` EVIDENCE item and contributes a signal in the `text` vector space. |
| `evidence_ids` | One or more UUIDs of existing EVIDENCE items already in the database. Modality is inferred from the evidence's `evidence_type`. Multiple items of the same modality are combined (averaged) in that modality's vector space. |
| `reference_cluster_id` | Use an existing cluster as the full query. Expands to the cluster's current head-version MEMBERSHIP items, weighted by their `weight` values. Mutually exclusive with the fields above. |

All fields are optional and composable.

`profile_id` is optional on all search endpoints. Omit to use the system-default profile.

---

#### Simple search (GET)

> **Required scope**: `people-gator:browse` (unauthenticated requests accepted)

```
GET  /api/v1/search
HEAD /api/v1/search
```

| Parameter | Type | Description |
|---|---|---|
| `name` | string (repeatable) | Name string(s). |
| `text` | string (repeatable) | Free-text snippet(s). |
| `evidence_id` | UUID (repeatable) | Existing evidence ID(s). |
| `reference_cluster_id` | UUID | Use cluster as query. Mutually exclusive with the above. |
| `profile_id` | UUID | Override profile. Optional. |
| `result_type` | string (repeatable) | `cluster`, `face_detection`, `named_entity`, `text_region`, `grounded_name`, `grounded_description`, `authority_identifier` |
| `cluster_role` | string (repeatable) | Filter clusters by role. Only applied when `result_type=cluster`. |
| `provider` | string (repeatable) | Filter by SOURCE.provider (`kramerius`, `nkcr`, `wikimedia`, `local`). |
| `has_face` | bool | Filter to clusters with at least one `face_detection` member. |
| `has_authority_link` | bool | Filter to clusters with at least one `authority_identifier` member. |
| `language` | string (BCP 47, repeatable) | Filter textual evidence by language. |
| `limit` | int | Default 20, max 200. |
| `after_id` | UUID | Keyset cursor — pass the last result's ID from the previous page. |

Example:
```
GET /api/v1/search?name=Antonín+Dvořák&name=Dvořáček&evidence_id=<uuid>&result_type=cluster&result_type=face_detection
```

Response: same structure as `POST /api/v1/search`.

---

#### Composite search (POST)

> **Required scope**: `people-gator:browse` (unauthenticated requests accepted)

```
POST /api/v1/search
```

```json
{
  "query": {
    "names": ["Antonín Dvořák", "Dvořáček"],
    "texts": ["skladatel narozen Nelahozeves"],
    "evidence_ids": ["<uuid-face-evidence>", "<uuid-name-evidence>"],
    "reference_cluster_id": null
  },
  "profile_id": null,
  "result_types": ["cluster", "face_detection"],
  "filters": {
    "cluster_roles": ["grounded_cluster", "automatic_cluster"],
    "provider": ["kramerius", "nkcr"],
    "has_face": true,
    "has_authority_link": false,
    "languages": ["cs", "sk"]
  },
  "limit": 20,
  "after_id": null,
  "save": false
}
```

- `save` — when `true`, the query cluster is persisted as a `saved_search` CLUSTER and its `cluster_id` is returned in `search_cluster_id`. When `false` (default) the query is ephemeral.

Response:

```json
{
  "total": 142,
  "limit": 20,
  "next_after_id": "<uuid>",
  "results": [
    {
      "result_type": "cluster",
      "cluster_id": "<uuid>",
      "head_version_id": "<uuid>",
      "cluster_role": "grounded_cluster",
      "score": 0.87,
      "signal_contributions": {
        "named_entity":  { "raw_score": 0.91, "normalised_score": 0.88, "weight": 0.4, "top_evidence_id": "<uuid>" },
        "face_detection": { "raw_score": 0.83, "normalised_score": 0.79, "weight": 0.6, "top_evidence_id": "<uuid>" }
      },
      "members": {
        "face_detection": { "total": 3 },
        "named_entity":   { "total": 5 },
        "authority_identifier": { "total": 1 }
      }
    },
    {
      "result_type": "face_detection",
      "evidence_id": "<uuid>",
      "evidence_version_id": "<uuid>",
      "source_id": "<uuid>",
      "score": 0.83,
      "signal_contributions": {
        "face_detection": { "raw_score": 0.83, "normalised_score": 0.79, "weight": 1.0, "top_evidence_id": "<uuid>" }
      },
      "cluster_memberships": { "total": 2 }
    }
  ],
  "facets": {
    "cluster_roles": { "grounded_cluster": 34, "automatic_cluster": 108 },
    "provider": { "kramerius": 72, "nkcr": 60 },
    "result_types": { "cluster": 120, "face_detection": 22 },
    "evidence_types": { "face_detection": 80, "named_entity": 120 },
    "has_face": { "true": 98, "false": 44 },
    "has_authority_link": { "true": 34, "false": 108 }
  },
  "query": {
    "names": ["Antonín Dvořák", "Dvořáček"],
    "texts": ["skladatel narozen Nelahozeves"],
    "evidence_ids": ["<uuid-face-evidence>", "<uuid-name-evidence>"],
    "reference_cluster_id": null
  },
  "filters": {
    "cluster_roles": ["grounded_cluster", "automatic_cluster"],
    "provider": ["kramerius", "nkcr"],
    "has_face": true,
    "has_authority_link": false,
    "languages": ["cs", "sk"]
  },
  "profile_id": "<uuid-of-resolved-profile>",
  "search_cluster_id": null
}
```

`signal_contributions` is present on every result item. Each key is an `evidence_type`. Fields:
- `raw_score` — highest cosine similarity from the ANN retrieval pass for this modality.
- `normalised_score` — min-max normalised score within this modality across the candidate set.
- `weight` — effective weight applied from `SEARCH_PROFILE_MODALITY`.
- `top_evidence_id` — the evidence item that produced the highest score; null if no items were retrieved.

---

#### Find clusters similar to a given cluster

> **Required scope**: `people-gator:browse` (unauthenticated requests accepted)

```
GET  /api/v1/clusters/{cluster_id}/similar
HEAD /api/v1/clusters/{cluster_id}/similar
```

Equivalent to `POST /api/v1/search` with `query.reference_cluster_id` set to this cluster. The source cluster is excluded from results.

| Parameter | Type | Description |
|---|---|---|
| `profile_id` | UUID | Override profile. Optional. |
| `result_types` | string | Comma-separated. Allowed values: `cluster`, `face_detection`, `named_entity`, `text_region`, `grounded_name`, `grounded_description`, `authority_identifier`. Default `cluster`. |
| `cluster_role` | string (repeatable) | Filter clusters by role. Optional. |
| `provider` | string (repeatable) | Filter by SOURCE.provider (`kramerius`, `nkcr`, `wikimedia`, `local`). |
| `has_face` | bool | Filter to clusters with at least one `face_detection` member. |
| `has_authority_link` | bool | Filter to clusters with at least one `authority_identifier` member. |
| `language` | string (BCP 47, repeatable) | Filter textual evidence by language. |
| `limit` | int | Default 10. |

Response:

```json
{
  "total": 12,
  "limit": 10,
  "next_after_id": "<uuid>",
  "results": [
    {
      "result_type": "cluster",
      "cluster_id": "<uuid>",
      "head_version_id": "<uuid>",
      "cluster_role": "grounded_cluster",
      "score": 0.91,
      "signal_contributions": {
        "face_detection": { "raw_score": 0.93, "normalised_score": 0.91, "weight": 0.6, "top_evidence_id": "<uuid>" },
        "named_entity":   { "raw_score": 0.88, "normalised_score": 0.85, "weight": 0.4, "top_evidence_id": "<uuid>" }
      },
      "members": {
        "face_detection": { "total": 2 },
        "named_entity":   { "total": 4 },
        "authority_identifier": { "total": 1 }
      }
    }
  ],
  "facets": {
    "cluster_roles": { "grounded_cluster": 8, "automatic_cluster": 4 },
    "provider": { "kramerius": 10, "nkcr": 2 },
    "result_types": { "cluster": 12 },
    "evidence_types": { "face_detection": 20, "named_entity": 32 },
    "has_face": { "true": 10, "false": 2 },
    "has_authority_link": { "true": 5, "false": 7 }
  },
  "query": {
    "names": null,
    "texts": null,
    "evidence_ids": null,
    "reference_cluster_id": "<uuid-of-source-cluster>"
  },
  "filters": {
    "cluster_roles": [],
    "provider": [],
    "has_face": null,
    "has_authority_link": null,
    "languages": []
  },
  "profile_id": "<uuid-of-resolved-profile>",
  "search_cluster_id": null
}
```

---

### 1.4 Facets

Facet counts are returned inline in every search response. For populating filter controls before submitting a full query, a facets-only endpoint is available:

> **Required scope**: `people-gator:browse` (unauthenticated requests accepted)

```
GET  /api/v1/search/facets
HEAD /api/v1/search/facets
POST /api/v1/search/facets
```

Accepts the same query parameters and body as the corresponding search endpoints. Returns only the `facets` object — no ranked results are computed.

```json
{
  "cluster_roles": { "grounded_cluster": 34, "automatic_cluster": 108 },
  "provider": { "kramerius": 72, "nkcr": 60 },
  "has_face": { "true": 98, "false": 44 },
  "has_authority_link": { "true": 34, "false": 108 }
}
```

---

## 2. Cluster Lifecycle

### 2.1 Concepts

**CLUSTER** — a stable identity for a group of EVIDENCE items across all version history. The cluster's current `cluster_role` is read from `VERSION.cluster_role` via `head_version_id`; it is not stored directly on the CLUSTER row.

**VERSION** — an immutable snapshot of cluster membership state, identified by `version_id`. Created via OPERATION. Fields: `version_id`, `cluster_id`, `cluster_role`, `actor_id`, `search_profile_id`. The `version_id` is a UUIDv6 whose embedded timestamp serves as creation time; there is no separate `created_at` column.

**OPERATION** — a directed edge (or set of edges for multi-source operations) connecting VERSIONs. Recording an OPERATION row **seals** the `source_version_id` — no further DELTAs may be written to a sealed version. Operation types: `empty`, `stage`, `branch`, `union`, `intersection`, `split`, `conflict_free_join`.

**DELTA** — an `add` or `remove` entry associating a specific `(evidence_id, evidence_version_id)` pair with a `(cluster_id, version_id)`. Weight encodes the strength of the association. DELTAs may only be written to an unsealed (working) version.

**MEMBERSHIP** — the materialised resolved membership for a sealed VERSION. Derived by replaying the OPERATION DAG and applying DELTAs in `delta_id` order. For the current working (unsealed) version, membership is the most recently sealed ancestor's MEMBERSHIP combined with live DELTAs from the DELTA table.

**Cluster roles** (`cluster_role` on VERSION):

| Role | Description |
|---|---|
| `saved_search` | A persisted search query saved by a user |
| `automatic_cluster` | Automatically generated or promoted from a saved search |
| `manual_cluster` | Manually created or extended cluster by an annotator |
| `authority_cluster` | Created by a SERVICE_AGENT from an authority sync (Wikidata, NKCR) |
| `grounded_cluster` | Reviewer-promoted cluster with high-confidence identity grounding |

---

### 2.2 Clusters

#### List clusters

> **Required scope**: `people-gator:browse` (unauthenticated requests accepted)

```
GET  /api/v1/clusters
HEAD /api/v1/clusters
```

| Parameter | Type | Description |
|---|---|---|
| `cluster_role` | string (repeatable) | Filter by role. |
| `limit` | int | Default 50. |
| `after_id` | UUID | Keyset cursor. |

---

#### Get a cluster

> **Required scope**: `people-gator:browse` (unauthenticated requests accepted)

```
GET  /api/v1/clusters/{cluster_id}
HEAD /api/v1/clusters/{cluster_id}
```

Returns cluster identity fields and the current head version's `cluster_role`, `actor_id`, and `search_profile_id`.

`HEAD` is implicitly supported on every `GET` endpoint (RFC 9110 §9.3.2): the server returns the same response headers as `GET` but with no body. Starlette/FastAPI handles this automatically — no separate route is needed. For this endpoint the useful headers are:

| Response header | Value | Purpose |
|---|---|---|
| `ETag` | `"<head_version_id>"` (quoted) | Cache validation; changes atomically on every head update |
| `Last-Modified` | RFC 7231 date derived from the UUIDv6 timestamp in `head_version_id` | HTTP cache and conditional-request support |
| `X-Cluster-Role` | current `cluster_role` string | Lets a client know the cluster type before fetching the body |

A `404 Not Found` response (with no body) indicates the cluster does not exist, making `HEAD` suitable for lightweight existence checks.

Clients can use the standard HTTP conditional-request headers for efficient re-validation:
- `If-None-Match: "<head_version_id>"` → `304 Not Modified` if the head has not changed.
- `If-Modified-Since: <timestamp>` → `304 Not Modified` if the cluster has not been updated since that time.

---

#### Discover allowed operations on a cluster

> **Required scope**: none (unauthenticated requests return capabilities for an anonymous caller; authenticated requests reflect the caller's actual scope and the cluster's current state)

```
OPTIONS /api/v1/clusters/{cluster_id}
```

Returns the HTTP methods and semantic workflow operations the calling principal may exercise on this cluster right now. The server evaluates both the caller's scope and the cluster's current state (working vs. sealed version, current `cluster_role`) to determine what is actually permitted.

Response `200 OK`:

```json
{
  "cluster_id": "<uuid>",
  "allowed_methods": ["GET", "OPTIONS", "PATCH"],
  "allowed_operations": [
    {
      "operation": "branch",
      "method": "POST",
      "url": "/api/v1/clusters/<uuid>/versions/<version_id>/branch",
      "requires_scope": "people-gator:annotate",
      "available": false,
      "unavailable_reason": "insufficient_scope"
    },
    {
      "operation": "delta_add",
      "method": "POST",
      "url": "/api/v1/clusters/<uuid>/versions/<version_id>/deltas",
      "requires_scope": "people-gator:annotate",
      "available": false,
      "unavailable_reason": "insufficient_scope"
    },
    {
      "operation": "stage",
      "method": "POST",
      "url": "/api/v1/clusters/<uuid>/versions/<version_id>/stage",
      "requires_scope": "people-gator:annotate",
      "available": false,
      "unavailable_reason": "insufficient_scope"
    },
    {
      "operation": "update_head",
      "method": "PATCH",
      "url": "/api/v1/clusters/<uuid>",
      "requires_scope": "people-gator:review",
      "available": true,
      "unavailable_reason": null
    },
    {
      "operation": "union",
      "method": "POST",
      "url": "/api/v1/clusters/<uuid>/versions/<version_id>/union",
      "requires_scope": "people-gator:review",
      "available": true,
      "unavailable_reason": null
    },
    {
      "operation": "intersection",
      "method": "POST",
      "url": "/api/v1/clusters/<uuid>/versions/<version_id>/intersection",
      "requires_scope": "people-gator:review",
      "available": true,
      "unavailable_reason": null
    },
    {
      "operation": "verify",
      "method": "POST",
      "url": "/api/v1/clusters/<uuid>/verify",
      "requires_scope": "people-gator:verify",
      "available": false,
      "unavailable_reason": "cluster_role_ineligible"
    }
  ]
}
```

`available` is `true` if the operation can be invoked right now. When `false`, `unavailable_reason` is one of:

| Reason | Meaning |
|---|---|
| `insufficient_scope` | Caller's token does not carry the required scope |
| `version_sealed` | The working version is already sealed; a branch is needed first |
| `version_not_found` | No unsealed (working) version exists on this cluster |
| `cluster_role_ineligible` | The operation is not valid for the cluster's current `cluster_role` (e.g., `verify` requires `grounded_cluster`) |
| `unauthenticated` | No token was supplied and the operation requires authentication |

The `url` field always contains the concrete URL (with real IDs) of the target endpoint for that operation, resolved against the cluster's current head version.

---

#### Create a cluster (manual)

> **Required scope**: `people-gator:annotate`

```
POST /api/v1/clusters
```

Creates a new CLUSTER, writes an `empty` OPERATION, and returns the initial VERSION. The initial `cluster_role` must be `manual_cluster` or `saved_search`. Service agents use the ingest evidence endpoints to create `authority_cluster` entries via the standard `empty` → DELTA → `stage` workflow.

```json
{
  "cluster_role": "manual_cluster"
}
```

Returns `201 Created`:

```json
{
  "cluster_id": "<uuid>",
  "head_version_id": "<uuid>",
  "cluster_role": "manual_cluster"
}
```

---

#### Update cluster head (reviewer)

> **Required scope**: `people-gator:review`

```
PATCH /api/v1/clusters/{cluster_id}
```

Allows a reviewer to explicitly advance `head_version_id` after a `union`, `intersection`, or `conflict_free_join` operation. Uses optimistic CAS: the update is conditioned on `expected_head_version_id` matching the current head. Returns `409 Conflict` if they diverge.

```json
{
  "head_version_id": "<uuid-of-new-head>",
  "expected_head_version_id": "<uuid-of-current-head>"
}
```

Returns `200 OK` with the updated cluster summary.

---

#### Get resolved membership

> **Required scope**: `people-gator:browse` (unauthenticated requests accepted)

```
GET  /api/v1/clusters/{cluster_id}/membership
HEAD /api/v1/clusters/{cluster_id}/membership
```

Returns the materialised MEMBERSHIP as of the current head version. Each member item includes `evidence_id`, `evidence_version_id`, `evidence_type`, `weight`, and `as_of_version_id`.

| Parameter | Type | Description |
|---|---|---|
| `version_id` | UUID | Override head — resolve membership for any historical version. Optional. |

---

#### Get pending DELTAs (working version)

> **Required scope**: `people-gator:annotate`

```
GET  /api/v1/clusters/{cluster_id}/versions/{version_id}/pending
HEAD /api/v1/clusters/{cluster_id}/versions/{version_id}/pending
```

Returns the unreduced DELTAs on the given working (unsealed) version — the diff not yet committed into a downstream version. Returns `409 Conflict` if the version is already sealed.

---

### 2.3 Versions

#### List versions for a cluster

> **Required scope**: `people-gator:browse` (unauthenticated requests accepted)

```
GET  /api/v1/clusters/{cluster_id}/versions
HEAD /api/v1/clusters/{cluster_id}/versions
```

Returns all versions in ascending `version_id` (creation-time) order with their `cluster_role`, `actor_id`, and the operation type that created them.

---

#### Get a version

> **Required scope**: `people-gator:browse` (unauthenticated requests accepted)

```
GET  /api/v1/clusters/{cluster_id}/versions/{version_id}
HEAD /api/v1/clusters/{cluster_id}/versions/{version_id}
```

Returns full version detail: `cluster_role`, `actor_id`, `search_profile_id`, incoming operation, and outgoing operations (if sealed).

---

### 2.4 DELTAs

DELTAs are the write surface for cluster membership. They may only be written to a working (unsealed) version.

#### Write a DELTA

> **Required scope**: `people-gator:annotate`

```
POST /api/v1/clusters/{cluster_id}/versions/{version_id}/deltas
```

```json
{
  "evidence_id": "<uuid>",
  "evidence_version_id": "<uuid>",
  "delta_type": "add",
  "weight": 0.9
}
```

- `delta_type`: `add` or `remove`.
- `weight`: float — strength of the association. Required for `add`; ignored for `remove`.
- Returns `409 Conflict` with code `version_sealed` if the version already has an outgoing OPERATION.

Returns `201 Created` with the new `delta_id`.

---

#### List DELTAs on a version

> **Required scope**: `people-gator:annotate`

```
GET  /api/v1/clusters/{cluster_id}/versions/{version_id}/deltas
HEAD /api/v1/clusters/{cluster_id}/versions/{version_id}/deltas
```

Returns all DELTAs in `delta_id` ascending order.

---

### 2.5 Operations

Operations seal a source version and create new downstream versions. They are the mechanism for progressing the cluster lifecycle.

#### Create an operation

> **Required scope**: see per-type table below.

```
POST /api/v1/clusters/{cluster_id}/operations
```

`{cluster_id}` is the **target** cluster for all merge operations (`union`, `intersection`, `conflict_free_join`) and the **source** cluster for `stage`, `branch`, and `split`.

Request body varies by `operation_type`:

---

**`stage`** — seals the working version and opens a new empty version on the same cluster. Automatically advances `head_version_id` when `source_version_id` equals the current head.

> **Required scope**: `people-gator:annotate`

```json
{
  "operation_type": "stage",
  "source_version_id": "<uuid>",
  "cluster_role": "manual_cluster"
}
```

Returns the new `version_id`.

---

**`branch`** — creates a parallel version from a source version without advancing the main head.

> **Required scope**: `people-gator:annotate`

```json
{
  "operation_type": "branch",
  "source_version_id": "<uuid>",
  "cluster_role": "manual_cluster"
}
```

Returns the new branch `version_id`. The cluster `head_version_id` is **not** updated.

---

**`union`** — merges two or more source versions into a new target version on this cluster. Membership is the union of all source memberships — `add` wins over `remove` for the same evidence item. All source versions must be backed by a TASK for workflow-advancing use. After the operation, the reviewer calls `PATCH /api/v1/clusters/{cluster_id}` to explicitly advance `head_version_id`.

> **Required scope**: `people-gator:review`

```json
{
  "operation_type": "union",
  "source_versions": [
    { "cluster_id": "<uuid>", "version_id": "<uuid>" },
    { "cluster_id": "<uuid>", "version_id": "<uuid>" }
  ],
  "cluster_role": "automatic_cluster"
}
```

Returns the new `version_id` and `operation_id`.

---

**`intersection`** — same structure as `union`. Membership is the intersection of all source memberships — only evidence present in every source is included.

> **Required scope**: `people-gator:review`

```json
{
  "operation_type": "intersection",
  "source_versions": [
    { "cluster_id": "<uuid>", "version_id": "<uuid>" },
    { "cluster_id": "<uuid>", "version_id": "<uuid>" }
  ],
  "cluster_role": "automatic_cluster"
}
```

---

**`conflict_free_join`** — identical result to `union` but performs a pre-commit conflict check. An evidence item is **in conflict** if it has `delta_type = add` in at least one source membership and `delta_type = remove` in at least one other. Returns `409 Conflict` with a list of conflicting `evidence_id`s if any are found. The caller resolves conflicts by writing explicit DELTAs to a working version and retrying.

> **Required scope**: `people-gator:review`

```json
{
  "operation_type": "conflict_free_join",
  "source_versions": [
    { "cluster_id": "<uuid>", "version_id": "<uuid>" },
    { "cluster_id": "<uuid>", "version_id": "<uuid>" }
  ],
  "cluster_role": "automatic_cluster"
}
```

Conflict response (`409`):
```json
{
  "code": "merge_conflict",
  "message": "Conflicts detected. Resolve before retrying.",
  "conflicting_evidence_ids": ["<uuid>", "<uuid>"]
}
```

---

**`split`** — forks one source version into two or more new clusters. Each `split_target` specifies the DELTAs (by evidence ID) to write to the new cluster's initial version. All split target DELTAs are written atomically in the same transaction as the OPERATION rows. Returns `409 Conflict` with code `concurrent_head_advance` if the source version has been sealed by a concurrent operation before the split commits.

> **Required scope**: `people-gator:review`

```json
{
  "operation_type": "split",
  "source_version_id": "<uuid>",
  "split_targets": [
    {
      "cluster_role": "manual_cluster",
      "evidence_ids": ["<uuid>", "<uuid>"]
    },
    {
      "cluster_role": "manual_cluster",
      "evidence_ids": ["<uuid>"]
    }
  ]
}
```

Returns an array of new `{ cluster_id, version_id }` objects, one per split target. New cluster `head_version_id` values are **not** set (they start as the initial split version); reviewers advance them explicitly.

---

### 2.6 Role Promotion

`cluster_role` on a new VERSION is set by the caller in the `operation_type: stage` or merge operation body. Allowed progressions are enforced by the server:

| From | To | Required scope |
|---|---|---|
| `saved_search` | `automatic_cluster` | `people-gator:annotate` |
| `automatic_cluster` | `manual_cluster` | `people-gator:annotate` |
| `manual_cluster` | `manual_cluster` | `people-gator:annotate` |
| `automatic_cluster` | `grounded_cluster` | `people-gator:review` |
| `manual_cluster` | `grounded_cluster` | `people-gator:review` |
| `grounded_cluster` | `manual_cluster` | `people-gator:review` (re-open) |
| `authority_cluster` | `grounded_cluster` | `people-gator:verify` |

Any other transition returns `422 Unprocessable Entity` with code `invalid_role_transition`.

---

### 2.7 Tasks

TASKs tie a VERSION chain to the formal annotation and review workflow. A TASK grants the assignee the right to write DELTAs against the task's working version and makes that chain eligible for workflow-advancing operations (`union`, `intersection`, `conflict_free_join`). Any authenticated annotator may branch any cluster and write DELTAs without a TASK — this is personal working space. A TASK is required only for formal workflow progression.

#### List tasks

> **Required scope**: `people-gator:annotate` (own tasks); `people-gator:review` (submitted tasks); `people-gator:admin` (all tasks).

```
GET  /api/v1/tasks
HEAD /api/v1/tasks
```

| Parameter | Type | Description |
|---|---|---|
| `assignee_id` | UUID | Filter by assignee. |
| `task_role` | string | `annotate`, `review`, or `verify`. |
| `status` | string | `pending`, `submitted`, `review`, `closed`. |
| `cluster_id` | UUID | Filter by cluster. |
| `limit` | int | Default 50. |
| `after_id` | UUID | Keyset cursor. |

---

#### Get a task

> **Required scope**: `people-gator:annotate`

```
GET  /api/v1/tasks/{task_id}
HEAD /api/v1/tasks/{task_id}
```

Returns: `task_id`, `cluster_id`, `pinned_version_id`, `head_version_id`, `assignee_id`, `created_by`, `task_role`, `status`.

---

#### Discover allowed operations on a task

> **Required scope**: `people-gator:annotate`

```
OPTIONS /api/v1/tasks/{task_id}
```

Returns the status transitions the calling principal may invoke right now. Availability depends on the task's current `status`, the caller's scope, and whether the caller is the `assignee_id`, the `created_by` principal, or a reviewer picking up the task.

Response `200 OK`:

```json
{
  "task_id": "<uuid>",
  "current_status": "submitted",
  "allowed_methods": ["GET", "HEAD", "OPTIONS", "PATCH"],
  "allowed_operations": [
    {
      "operation": "submit",
      "method": "PATCH",
      "url": "/api/v1/tasks/<uuid>",
      "body": { "status": "submitted" },
      "requires_scope": "people-gator:annotate",
      "requires_role": "assignee",
      "available": false,
      "unavailable_reason": "invalid_task_transition"
    },
    {
      "operation": "retract",
      "method": "PATCH",
      "url": "/api/v1/tasks/<uuid>",
      "body": { "status": "pending" },
      "requires_scope": "people-gator:annotate",
      "requires_role": "assignee",
      "available": true,
      "unavailable_reason": null
    },
    {
      "operation": "pick_up",
      "method": "PATCH",
      "url": "/api/v1/tasks/<uuid>",
      "body": { "status": "review" },
      "requires_scope": "people-gator:review",
      "requires_role": "any_reviewer",
      "available": true,
      "unavailable_reason": null
    },
    {
      "operation": "close",
      "method": "PATCH",
      "url": "/api/v1/tasks/<uuid>",
      "body": { "status": "closed" },
      "requires_scope": "people-gator:review",
      "requires_role": "assigned_reviewer",
      "available": false,
      "unavailable_reason": "invalid_task_transition"
    },
    {
      "operation": "cancel",
      "method": "PATCH",
      "url": "/api/v1/tasks/<uuid>",
      "body": { "status": "closed" },
      "requires_scope": "people-gator:admin",
      "requires_role": "admin_or_creator",
      "available": false,
      "unavailable_reason": "invalid_task_transition"
    }
  ]
}
```

`requires_role` values:

| Value | Meaning |
|---|---|
| `assignee` | Caller must be the task's `assignee_id` |
| `any_reviewer` | Any principal carrying `people-gator:review` |
| `assigned_reviewer` | The specific reviewer who moved the task to `review` |
| `admin_or_creator` | Any `people-gator:admin` or the `created_by` principal |

`unavailable_reason` uses the same vocabulary as `OPTIONS /api/v1/clusters/{cluster_id}` plus `invalid_task_transition` (the transition is not allowed from the current status).

---

#### Create a task

> **Required scope**: `people-gator:admin`

```
POST /api/v1/tasks
```

```json
{
  "cluster_id": "<uuid>",
  "pinned_version_id": "<uuid>",
  "assignee_id": "<uuid>",
  "task_role": "annotate"
}
```

`pinned_version_id` is **immutable** after creation — it anchors the shared baseline for inter-annotator agreement calculations. `head_version_id` starts equal to `pinned_version_id`.

Returns `201 Created`.

---

#### Update task status

> **Required scope**: see transition table.

```
PATCH /api/v1/tasks/{task_id}
```

```json
{ "status": "submitted" }
```

Allowed transitions:

| From | To | Authorised actor | Notes |
|---|---|---|---|
| `pending` | `submitted` | Task `assignee_id` (`people-gator:annotate`) | Hands `head_version_id` to the review queue. |
| `submitted` | `pending` | Task `assignee_id` | Retract submission. `head_version_id` unchanged. |
| `submitted` | `review` | Any principal with `people-gator:review` | Reviewer picks up the task. |
| `review` | `closed` | The reviewer who moved to `review` | Reviewer should commit a merge operation before closing. |
| `pending` | `closed` | Task `created_by` or `people-gator:admin` | Cancellation; no version changes required. |

Any other transition returns `422` with code `invalid_task_transition`.

---

## 3. Data Import

### 3.1 Concepts

Import feeds pre-computed artifacts into the system. The People Gator API does not run inference — OCR, face detection, NER, and embedding generation are performed by external pipelines. Import endpoints accept typed evidence with full provenance.

The import hierarchy:
```
SOURCE_SCHEMA    (resolver family, e.g. "kramerius-iiif")
  └── SOURCE     (one document or scan artifact)
        └── DERIVED_EVIDENCE or AUTHORITY_EVIDENCE
```

A human face image uploaded by an annotator is also a `SOURCE` (under the `image-upload` schema) — user uploads follow the on-demand fast-path described in §3.5.

---

### 3.2 Source Schemas

Source schemas define how storage paths are resolved for a family of sources. They are registered once and reused. The primary key is the `schema_name` string — there is no surrogate UUID.

> **Required scope**: `GET` — `people-gator:ingest`; `POST` — `people-gator:admin`.

#### List source schemas

```
GET  /api/v1/source-schemas
HEAD /api/v1/source-schemas
```

---

#### Get a source schema

```
GET  /api/v1/source-schemas/{schema_name}
HEAD /api/v1/source-schemas/{schema_name}
```

---

#### Register a source schema

```
POST /api/v1/source-schemas
```

`resolver_type` must be one of: `db-source-table-row`, `s3-image`, `http-image`, `fsspec-image`, `fsspec-pagexml`, `s3-table`. The `resolver_config` structure is discriminated by `resolver_type` and validated against the per-type Pydantic schema at registration time. No arbitrary keys are allowed.

```json
{
  "schema_name": "kramerius-iiif",
  "resolver_type": "http-image",
  "resolver_config": {
    "base_url_template": "https://api.kramerius.mzk.cz/",
    "path_template": "search/iiif/uuid:{page_id}/full/max/0/default.jpg"
  }
}
```

Allowed placeholder keys per `resolver_type`:

| `resolver_type` | Allowed placeholder keys |
|---|---|
| `db-source-table-row` | `principal_id` |
| `s3-image` | `principal_id`, `file_id` |
| `http-image` | `file_name` |
| `fsspec-pagexml` | `page_id`, `library`, `document_id` |
| `fsspec-image` | `library`, `document_id`, `page_id` |
| `s3-table` | `text_type` |

Returns `201 Created`. `schema_name` must be globally unique.

---

### 3.3 Sources

#### List sources

> **Required scope**: `people-gator:ingest`

```
GET  /api/v1/sources
HEAD /api/v1/sources
```

| Parameter | Type | Description |
|---|---|---|
| `source_schema_name` | string | Filter by schema. |
| `provider` | string | Filter by provider (`kramerius`, `nkcr`, `wikimedia`, `local`). |
| `limit` | int | Default 50. |
| `after_id` | UUID | Keyset cursor. |

---

#### Get a source

> **Required scope**: `people-gator:ingest`

```
GET  /api/v1/sources/{source_id}
HEAD /api/v1/sources/{source_id}
```

---

#### Discover allowed operations on a source

> **Required scope**: `people-gator:ingest`

```
OPTIONS /api/v1/sources/{source_id}
```

Sources are immutable after registration. `OPTIONS` exposes whether the caller can inspect or act on the source's processing pipeline. Availability depends on the processing status of each MODEL_AGENT queue entry.

Response `200 OK`:

```json
{
  "source_id": "<uuid>",
  "allowed_methods": ["GET", "HEAD", "OPTIONS"],
  "allowed_operations": [
    {
      "operation": "view_processing_status",
      "method": "GET",
      "url": "/api/v1/sources/<uuid>/processing",
      "requires_scope": "people-gator:ingest",
      "available": true,
      "unavailable_reason": null
    },
    {
      "operation": "upload_image_search",
      "method": "POST",
      "url": "/api/v1/search",
      "requires_scope": "people-gator:annotate",
      "available": false,
      "unavailable_reason": "insufficient_scope",
      "note": "Use the source's evidence as query signals via evidence_ids in POST /api/v1/search."
    }
  ]
}
```

The `allowed_methods` array will never include `PATCH`, `PUT`, or `DELETE` — sources cannot be mutated or removed after registration. Re-ingesting the same content returns the existing `source_id` via the idempotent `content_hash` check.

---

#### Register a source

> **Required scope**: `people-gator:ingest`

```
POST /api/v1/sources
```

`content_hash` is a BLAKE3 256-bit hash, hex-encoded as a 64-character lowercase string. If an existing SOURCE row has the same `content_hash`, the server returns `200 OK` with the existing `source_id` (idempotent).

```json
{
  "source_schema_name": "kramerius-iiif",
  "source": "uuid:abc123",
  "provider": "kramerius",
  "content_hash": "<blake3-hex-64>",
  "metadata": {
    "library": "mzk",
    "document_id": "uuid:abc123",
    "page_id": "uuid:def456"
  }
}
```

On success, one `SOURCE_PROCESSING` row per active MODEL_AGENT relevant to this source type is written with `processing_status = queued`. Returns `201 Created` or `200 OK` (duplicate).

---

#### Get source processing status

> **Required scope**: `people-gator:ingest`

```
GET  /api/v1/sources/{source_id}/processing
HEAD /api/v1/sources/{source_id}/processing
```

Returns the `SOURCE_PROCESSING` rows for this source — one per MODEL_AGENT that has been queued for it.

```json
{
  "source_id": "<uuid>",
  "processing": [
    {
      "producer_id": "<uuid>",
      "model_slug": "retinaface-r50-v1",
      "evidence_type": "face_detection",
      "processing_status": "complete",
      "started_at": "<iso8601>",
      "completed_at": "<iso8601>",
      "error_message": null
    }
  ]
}
```

`processing_status` values: `queued`, `in_progress`, `complete`, `failed`.

---

### 3.4 Derived Evidence

DERIVED_EVIDENCE is produced by MODEL_AGENTs: `face_detection`, `named_entity`, and `text_region`. `producer_id` must be a registered `MODEL_AGENT.principal_id` for the given `evidence_type`.

#### Ingest a derived evidence item

> **Required scope**: `people-gator:ingest`

```
POST /api/v1/evidence/derived
```

When `evidence_id` is null a new EVIDENCE identity is created. When `evidence_id` is provided and `content_hash` matches the current version, `200 OK` is returned (idempotent). When `evidence_id` is provided and `content_hash` differs, a new `evidence_version_id` is minted (`201 Created`).

```json
{
  "evidence_id": null,
  "source_id": "<uuid>",
  "source_path": "uuid:def456",
  "evidence_type": "face_detection",
  "schema_version": "v1",
  "producer_id": "<model-agent-principal-id>",
  "content_hash": "<blake3-hex-64>",
  "produced_metadata": {
    "bounding_box": {
      "box": { "min": { "x": 0.12, "y": 0.08 }, "max": { "x": 0.34, "y": 0.41 } },
      "label": "face"
    },
    "keypoints": [
      { "point": { "x": 0.20, "y": 0.18 }, "label": "left_eye" },
      { "point": { "x": 0.28, "y": 0.18 }, "label": "right_eye" }
    ],
    "image": { "width_px": 1200, "height_px": 1600 },
    "confidence": 0.97
  }
}
```

Returns `{ evidence_id, evidence_version_id, status }` where `status` is `created`, `updated`, or `unchanged`.

---

#### Bulk ingest derived evidence

> **Required scope**: `people-gator:ingest`

```
POST /api/v1/evidence/derived/bulk
```

Accepts an array of evidence ingest objects (same schema as single ingest). Processed atomically within a single transaction. Maximum batch size: 500 items. Returns an array of `{ evidence_id, evidence_version_id, status }`.

---

#### Revise derived evidence metadata (human correction)

> **Required scope**: `people-gator:annotate`

```
POST /api/v1/evidence/derived/{evidence_id}/revise
```

Sets `revised_metadata` on a DERIVED_EVIDENCE row and mints a new `evidence_version_id`. The `produced_metadata` is always retained. `revisor_id` is set to the calling user's `principal_id`.

```json
{
  "evidence_version_id": "<uuid>",
  "revised_metadata": {
    "bounding_box": {
      "box": { "min": { "x": 0.11, "y": 0.07 }, "max": { "x": 0.35, "y": 0.42 } },
      "label": "face"
    },
    "image": { "width_px": 1200, "height_px": 1600 },
    "confidence": 0.97
  }
}
```

Returns `{ evidence_id, evidence_version_id }`.

---

#### Get an evidence item

> **Required scope**: `people-gator:annotate`

```
GET  /api/v1/evidence/{evidence_id}
HEAD /api/v1/evidence/{evidence_id}
```

Returns the latest active version. Includes both `produced_metadata` and `revised_metadata` (when present) for DERIVED_EVIDENCE.

---

#### Discover allowed operations on an evidence item

> **Required scope**: `people-gator:annotate`

```
OPTIONS /api/v1/evidence/{evidence_id}
```

Returns what the calling principal can do with this evidence item. The two key axes are evidence family (`derived` vs `authority`) and whether the item is stale or soft-deleted.

Response `200 OK`:

```json
{
  "evidence_id": "<uuid>",
  "evidence_type": "face_detection",
  "evidence_family": "derived",
  "is_stale": false,
  "is_deleted": false,
  "allowed_methods": ["GET", "HEAD", "OPTIONS"],
  "allowed_operations": [
    {
      "operation": "revise",
      "method": "POST",
      "url": "/api/v1/evidence/derived/<uuid>/revise",
      "requires_scope": "people-gator:annotate",
      "available": true,
      "unavailable_reason": null
    },
    {
      "operation": "view_cluster_memberships",
      "method": "GET",
      "url": "/api/v1/evidence/<uuid>/memberships",
      "requires_scope": "people-gator:annotate",
      "available": true,
      "unavailable_reason": null
    }
  ]
}
```

`evidence_family` is `derived` for `face_detection`, `named_entity`, `text_region`; `authority` for `grounded_name`, `grounded_description`, `authority_identifier`.

`unavailable_reason` values specific to evidence:

| Reason | Meaning |
|---|---|
| `authority_evidence` | `revise` is not available — authority evidence is replaced wholesale by re-sync, not revised in place |
| `evidence_deleted` | Item is soft-deleted; no write operations are permitted |
| `evidence_stale` | Item has been superseded; revision is blocked to avoid branching stale lineage |

---

#### Get a specific evidence version

> **Required scope**: `people-gator:annotate`

```
GET  /api/v1/evidence/{evidence_id}/versions/{evidence_version_id}
HEAD /api/v1/evidence/{evidence_id}/versions/{evidence_version_id}
```

---

#### List evidence

> **Required scope**: `people-gator:annotate`

```
GET  /api/v1/evidence
HEAD /api/v1/evidence
```

| Parameter | Type | Description |
|---|---|---|
| `source_id` | UUID | Filter by source. |
| `evidence_type` | string (repeatable) | Filter by type. |
| `schema_version` | string | Filter by schema version. |
| `is_stale` | bool | Include stale items. Default `false`. |
| `limit` | int | Default 50. |
| `after_id` | UUID | Keyset cursor on `evidence_id`. |

---

### 3.6 Authority Evidence

AUTHORITY_EVIDENCE is produced by SERVICE_AGENTs: `grounded_name`, `grounded_description`, and `authority_identifier`. `producer_id` must be a registered `SERVICE_AGENT.principal_id`.

#### Ingest authority evidence

> **Required scope**: `people-gator:ingest`

```
POST /api/v1/evidence/authority
```

```json
{
  "evidence_id": null,
  "source_id": "<uuid>",
  "source_path": null,
  "evidence_type": "grounded_name",
  "schema_version": "v1",
  "producer_id": "<service-agent-principal-id>",
  "content_hash": "<blake3-hex-64>",
  "metadata": {
    "name": "Antonín Dvořák",
    "type": "preferred",
    "language": "cs"
  }
}
```

Authority evidence has no `revised_metadata` — re-sync creates a new EVIDENCE version (`is_stale = true` on the old one).

Returns `{ evidence_id, evidence_version_id, status }`.

---

#### Bulk ingest authority evidence

> **Required scope**: `people-gator:ingest`

```
POST /api/v1/evidence/authority/bulk
```

Same rules as derived bulk ingest. Maximum batch size: 500 items.

---

#### Import an authority entity (convenience)

> **Required scope**: `people-gator:ingest`

```
POST /api/v1/import/authority-entity
```

Convenience endpoint that atomically:
1. Registers or updates the SOURCE row for the authority entity.
2. Bulk-upserts all `grounded_name`, `grounded_description`, and `authority_identifier` AUTHORITY_EVIDENCE items.
3. If no authority cluster yet exists for this entity's source: creates a new CLUSTER, writes an `empty` OPERATION, writes DELTA entries for all ingested evidence, and stages to `authority_cluster`.
4. If the authority cluster already exists: writes DELTAs for updated evidence and stages a new `authority_cluster` VERSION.

All steps execute within a single transaction.

```json
{
  "source_schema_name": "nkcr-authority",
  "source": "AUT10000001",
  "provider": "nkcr",
  "content_hash": "<blake3-hex-64>",
  "source_metadata": { "nkcr_id": "AUT10000001" },
  "producer_id": "<service-agent-principal-id>",
  "names": [
    { "name": "Antonín Dvořák", "type": "preferred", "language": "cs" },
    { "name": "Antonin Dvorak", "type": "alias",     "language": "en" }
  ],
  "descriptions": [
    { "description": "Czech composer (1841–1904)", "language": "en" }
  ],
  "identifiers": [
    { "identifier": "Q182048", "authority_type": "wikidata" },
    { "identifier": "AUT10000001", "authority_type": "nkcr" }
  ]
}
```

Returns `201 Created` (new entity) or `200 OK` (updated) with `source_id`, `cluster_id`, and all `evidence_id` values.

---

### 3.7 Image Upload (on-demand)

User-uploaded images are registered as `s3-image` sources with `provider = local` and immediately processed by the default active face detection MODEL_AGENT inline with the request (on-demand fast path). Requires the `image-upload` SOURCE_SCHEMA to be pre-registered.

> **Required scope**: `people-gator:annotate`

```
POST /api/v1/sources/upload
Content-Type: multipart/form-data
```

| Field | Description |
|---|---|
| `image` | Image file (JPEG or PNG). |

The server:
1. Computes the BLAKE3 hash of the image bytes.
2. Checks for an existing SOURCE with the same hash; if found returns `200 OK` with the existing `source_id` and any previously extracted `face_detection` evidence.
3. Otherwise uploads the image to S3, registers the SOURCE row, dispatches inline face detection, ingests the resulting `face_detection` DERIVED_EVIDENCE items, and returns `201 Created`.

Returns `201 Created` or `200 OK`:

```json
{
  "source_id": "<uuid>",
  "content_hash": "<blake3-hex-64>",
  "processing_status": "complete",
  "evidence": [
    {
      "evidence_id": "<uuid>",
      "evidence_version_id": "<uuid>",
      "evidence_type": "face_detection",
      "confidence": 0.97
    }
  ]
}
```

Returns `422 Unprocessable Entity` with code `no_face_detected` if the face detection pipeline finds no faces in the image.

---

## 4. Principals

Principals are the actors that create VERSIONs, write DELTAs, and produce EVIDENCE. There are three types: `user`, `service_agent`, `model_agent`.

#### List principals

> **Required scope**: `people-gator:admin`

```
GET  /api/v1/principals
HEAD /api/v1/principals
```

| Parameter | Type | Description |
|---|---|---|
| `principal_type` | string | `user`, `service_agent`, `model_agent`. |
| `is_active` | bool | Default `true`. |
| `limit` | int | Default 50. |
| `after_id` | UUID | Keyset cursor. |

---

#### Get a principal

> **Required scope**: `people-gator:annotate` (own record); `people-gator:admin` (any).

```
GET  /api/v1/principals/{principal_id}
HEAD /api/v1/principals/{principal_id}
```

Returns `principal_type`-specific fields alongside the base `principal_id`, `display_name`, `is_active`.

---

#### Get current user (self)

> **Required scope**: `people-gator:annotate`

```
GET  /api/v1/principals/me
HEAD /api/v1/principals/me
```

Returns the USER record for the authenticated principal, creating it on first call.

---

#### Register a service agent

> **Required scope**: `people-gator:admin`

```
POST /api/v1/principals/service-agents
```

```json
{
  "agent_slug": "pipeline:authority-sync-wikidata",
  "display_name": "Wikidata Authority Sync",
  "description": "Periodic Wikidata authority record synchronisation pipeline."
}
```

`agent_slug` must be unique and follow `<category>:<name>` convention. Returns `201 Created` with the new `principal_id`.

---

#### Register a model agent

> **Required scope**: `people-gator:admin`

```
POST /api/v1/principals/model-agents
```

```json
{
  "display_name": "ArcFace R100 v2",
  "evidence_type": "face_detection",
  "role": "face",
  "model_slug": "arcface-r100-v2",
  "model_version": "2.0.0",
  "registry_source": "mlflow",
  "registry_uri": "models:/face-detector/3",
  "is_active": true
}
```

`(evidence_type, role, model_slug)` must be unique. The vector slot name for this agent is `face:arcface-r100-v2`. Returns `201 Created` with the new `principal_id`.

---

#### Update model agent active status

> **Required scope**: `people-gator:admin`

```
PATCH /api/v1/principals/model-agents/{principal_id}
```

```json
{ "is_active": false }
```

Retiring an agent sets `is_active = false`. Existing SEARCH_PROFILE_MODALITY rows that reference this agent will surface a warning at query time. The agent row is never deleted while EVIDENCE records reference its `producer_id`.

---

## 5. Export

Export requests are audit-logged. Responses are either streamed directly for small exports or returned as a signed download URL for large ones.

### 5.1 Cluster State Export

> **Required scope**: single cluster — `people-gator:annotate`; with `include_history` — `people-gator:review`; bulk (more than one cluster) — `people-gator:admin`.

```
POST /api/v1/export/cluster-state
```

```json
{
  "cluster_ids": ["<uuid>"],
  "format": "jsonl",
  "include_history": false
}
```

`format` options: `json` (single cluster), `jsonl` (streamable bulk), `csv` (tabular, one row per cluster-evidence pair), `jsonld` (linked data, preferred for authority-grounded clusters).

Response for small exports: the export document directly, with appropriate `Content-Type`. For large exports (more than 1 000 members or 10 clusters): `202 Accepted` with a signed S3 URL polling endpoint.

Each cluster record contains:
- `export_type`: `cluster_state`
- `exported_at`: ISO 8601
- `cluster_id`, `cluster_role`, `head_version_id`
- `members`: list of `{ evidence_id, evidence_version_id, evidence_type, weight, source_id, provider, metadata }`
- `authority_links`: subset of members where `evidence_type = authority_identifier`, with `identifier` and `authority_type` at top level
- `version_history`: empty by default; populated when `include_history = true` — each entry: `version_id`, `cluster_role`, `actor_id`, `operation_type`

---

### 5.2 Inter-Annotator Agreement Export

> **Required scope**: `people-gator:review`

```
POST /api/v1/export/inter-annotator-agreement
```

```json
{
  "cluster_id": "<uuid>",
  "pinned_version_id": "<uuid>"
}
```

Requires at least two TASKs in `submitted` or `review` status sharing the given `pinned_version_id` on this cluster. Returns `422` if fewer than two such tasks exist.

Format: JSONL. Each record contains:
- `export_type`: `inter_annotator_agreement`
- `cluster_id`, `pinned_version_id`, `exported_at`
- `tasks`: list of `{ task_id, assignee_id, submitted_version_id, membership_evidence_ids }`
- `metrics.pairwise_jaccard`: list of `{ task_a, task_b, jaccard }` — Jaccard index `|A ∩ B| / |A ∪ B|` per pair
- `metrics.fleiss_kappa`: Fleiss' κ over the binary add/remove decision per evidence item across all annotators
- `metrics.agreement_set_evidence_ids`: evidence present in **all** annotator memberships
- `metrics.disagreement_set_evidence_ids`: evidence present in some but not all annotator memberships

---

## 6. Common Conventions

### Pagination

All list and search endpoints use keyset pagination with `limit` and `after_id`. Because all IDs are UUIDv6 (k-sortable by creation time), `after_id` is the last ID seen on the previous page — no separate cursor token is needed.

```json
{
  "total": 142,
  "limit": 50,
  "next_after_id": "<uuid-of-last-result>",
  "results": []
}
```

`next_after_id` is `null` when the current page is the last one.

---

### Error responses

```json
{
  "code": "version_sealed",
  "message": "Version <uuid> already has an outgoing OPERATION and cannot accept new DELTAs."
}
```

Common codes:

| Code | HTTP status | Description |
|---|---|---|
| `not_found` | 404 | Requested resource does not exist |
| `forbidden` | 403 | Insufficient scope or ownership violation |
| `version_sealed` | 409 | DELTA write attempted on a sealed version |
| `concurrent_head_advance` | 409 | Optimistic CAS on `head_version_id` failed — re-read and retry |
| `invalid_role_transition` | 422 | Cluster role progression is not permitted |
| `invalid_task_transition` | 422 | Task status transition is not permitted |
| `merge_conflict` | 409 | `conflict_free_join` detected add/remove conflicts; see `conflicting_evidence_ids` |
| `no_face_detected` | 422 | Image upload produced no face detections |
| `batch_too_large` | 422 | Bulk ingest batch exceeds 500 items |
| `content_hash_mismatch` | 409 | Supplied `content_hash` does not match stored value for an existing evidence version |
| `resolver_validation_failed` | 422 | SOURCE.metadata placeholder values failed per-key format validation |

---

### Idempotency

`POST /api/v1/sources`, `POST /api/v1/evidence/derived`, `POST /api/v1/evidence/authority`, and `POST /api/v1/import/authority-entity` are idempotent on `content_hash`. Callers may safely retry on network failure.

---

### Content hashing

All `content_hash` fields use **BLAKE3** with 256-bit (32-byte) output, hex-encoded as a 64-character lowercase string. Compute the hash over the raw bytes of the content before any encoding or transformation.
