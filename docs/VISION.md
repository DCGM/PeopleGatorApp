# Vision, users and roadmap

People Gator manages a searchable collection of person identities for human
users and automated document-processing pipelines. An identity brings together
names and aliases, descriptive information, external identifiers where available,
and linked faces and text mentions. Grounding an identity in this evidence lets
a user or processing system follow a match back to its original document/page
and inspect why that person is a candidate.

Identity management and retrieval are core responsibilities of the application.
Curators maintain and review identities; processing systems search those same
records to gather information about people automatically detected in documents.
New evidence and human corrections can then improve the identities available to
subsequent processing. Provenance, uncertainty and review state must remain
visible throughout that cycle.

## Users and their work

| User | Workflow |
| --- | --- |
| Researcher or collection reader | Search names or reference faces, inspect scans and follow linked evidence |
| Annotator or identity curator | Maintain identity names, aliases and descriptive information; review candidates, assign and verify faces and OCR mentions, and resolve duplicate identities with the required permissions |
| Document-processing pipeline (API client) | Search existing identities using detected names and prepared face evidence, retrieve their information and supporting sources, and record new evidence and identity assignments |
| Ingestion operator | Connect processing outputs to the identity collection: register documents/pages and model definitions, ingest prepared annotations, vectors and media, and configure the pipeline's API access |
| Maintainer or deployment operator | Validate migrations, inspect processing metadata, review repairs and operate isolated previews |

These are workflow descriptions. Actual API permissions come from explicit
scopes, not these labels; see [Architecture](ARCHITECTURE.md#access-rules).

## Supporting the document-processing pipeline

People Gator provides the identity and evidence layer that an external processing
pipeline can query and enrich. For example, when a pipeline detects a person's
name or face in a newly processed document, it can use the API to:

1. Register the source, retain detected names for text queries and ingest
   prepared face evidence, including model-specific vectors where available.
2. Search for candidate identities by detected names and/or stored reference
   faces. Face-vector search uses registered models and already stored vectors.
3. Retrieve candidate profiles, names/aliases and descriptive information, then
   inspect the associated faces, mentions and source documents/pages. This gives
   the pipeline existing information about the detected person together with
   evidence for assessing the match.
4. Record an identity assignment and additional evidence, including text mentions
   for the selected or newly created identity, under its processing actor.
   Curators can review and correct these links in the app, making the maintained
   identity collection useful to later processing runs.

The external pipeline orchestrates detection, retrieval and any automatic
matching or information-gathering decisions. Search returns ranked candidates;
its scores are not identity probabilities, and an automatic assignment remains
distinct from a verified one. A pipeline should retain uncertainty when evidence
is insufficient. See [Search filters](SEARCH_FILTERS.md) and
[Database ingestion](DATABASE.md#ingestion-order) for the current API semantics.

## What is implemented

The app has scan search, a registered-document list, people search, person details
and a page workspace. Identity profiles contain names, aliases, descriptions and
optional external identifiers. PostgreSQL stores these profiles, their evidence
and model-specific face vectors. The API exposes identity management, retrieval
and ingestion operations for processing clients; search combines text and face
rankings with RRF. Annotation links distinguish automatic, manual and verified
assignments.

Current mention controls support identity assignment and link review. Editing
the extracted mention name or its context is a future capability; the current
mention patch contract changes assignment/review metadata. Processing metadata
records the last actor and time for identities and sources. It does not represent
processing jobs, job membership or a complete history of changes made by a run.

Synthetic previews demonstrate face-only, mention-only and mixed identities,
unassigned evidence, link review states and document filtering. The
[seed guide](../people-gator-api/docs/PREVIEW-SEEDING.md) describes the scenarios.
The seed is also a maintained feature contract, not just empty-database filler.

The API consumes prepared OCR and face artifacts. This repository does not ship
an OCR pipeline, train face models or provision an inference service. An optional
external embedding service and OpenRouter translation integration are separate
runtime dependencies. Transactional operations target PostgreSQL; the optional
Weaviate adapter has different guarantees. The browser currently automatically
logs into a configured demo account; a production identity/login experience is
not implemented here.

## Proposed roadmap

The following are directions for discussion, not promised releases or completed
features. Track accepted work in GitHub issues with acceptance criteria.

1. Edit mentions in the app: let curators correct extracted mention names and
   context while retaining the source relationship and making the effect on
   identity assignment and review state explicit. This extends the existing
   assignment controls to editing the mention content itself.
2. Explore processing jobs: make pipeline runs searchable so users can find the
   jobs that processed a document, inspect all documents belonging to a job and
   see which identities/entities that job created or modified. Navigation should
   connect a job's documents, affected identities and supporting evidence, so a
   curator can investigate a processing result. This needs explicit job/run
   relationships and retained change attribution beyond last-processed metadata;
   job search and a job history UI are not implemented today.
3. Strengthen identity and evidence review: improve candidate evaluation,
   information gathering and annotation ergonomics while preserving provenance,
   uncertainty and review state for both curators and automated clients.
4. Improve collection coverage: build and document integration workflows for
   additional prepared OCR/face datasets and models, with validation on import.
5. Prepare broader use: replace demo authentication with a reviewed login flow,
   define deployment-specific permissions and verify backup/restore operations.
6. Evaluate retrieval quality and operations: measure ranking on representative
   evidence, investigate performance with real collection sizes, and add useful
   dashboards without exposing document text or credentials.

Any change should extend the synthetic preview, tests and documentation alongside
the behavior it adds. Follow [Contributing](../CONTRIBUTING.md) and
[AGENTS.md](../AGENTS.md) for that workflow.
