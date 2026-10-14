# Vision, users and roadmap

People Gator makes a person in a digitized collection discoverable through both
visual and textual evidence. A useful result should lead back to the source page
and make the identity assignment available for human review. Keeping provenance
and uncertainty visible matters as much as retrieving similar faces or names.

## Users and their work

| User | Workflow |
| --- | --- |
| Researcher or collection reader | Search names or reference faces, inspect scans and follow linked evidence |
| Annotator or curator | Review candidate identities, edit aliases, assign and verify faces and OCR mentions |
| Ingestion operator | Register documents/pages and model definitions, ingest prepared annotations, vectors and media |
| Maintainer or deployment operator | Validate migrations, inspect processing metadata, review repairs and operate isolated previews |

These are workflow descriptions. Actual API permissions come from explicit
scopes, not these labels; see [Architecture](ARCHITECTURE.md#access-rules).

## What is implemented

The app has scan search, a registered-document list, people search, person details
and a page workspace. PostgreSQL stores identities, aliases, evidence and
model-specific face vectors. Annotation links distinguish automatic, manual and
verified assignments. Processing metadata records the last actor and time for
identities and sources. Search combines text and face rankings with RRF.

Synthetic previews demonstrate face-only, mention-only and mixed identities,
unassigned evidence, link review states and document filtering. The
[seed guide](../people-gator-api/docs/preview-seeding.md) describes the scenarios.
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

1. Strengthen evidence review: improve candidate evaluation and annotation
   ergonomics while preserving provenance and review state.
2. Improve collection coverage: build and document integration workflows for
   additional prepared OCR/face datasets and models, with validation on import.
3. Prepare broader use: replace demo authentication with a reviewed login flow,
   define deployment-specific permissions and verify backup/restore operations.
4. Evaluate retrieval quality and operations: measure ranking on representative
   evidence, investigate performance with real collection sizes, and add useful
   dashboards without exposing document text or credentials.

Any change should extend the synthetic preview, tests and documentation alongside
the behavior it adds. Follow [Contributing](../CONTRIBUTING.md) and
[AGENTS.md](../AGENTS.md) for that workflow.

