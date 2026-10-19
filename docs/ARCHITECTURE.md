# Current architecture

This guide describes the checked-in implementation. The deployed environment's
data, credentials and enabled optional services can differ.

## Modules and request flow

The API entry point is
[`app.py`](../people-gator-api/src/people_gator_api/app.py). Its lifespan initializes
the selected database and optional embedding/translation clients, then closes
them on shutdown. Versioned resource routes live under `/api/v1`; token login,
refresh and JWK discovery are separate routes. `/docs`, `/redoc` and
`/openapi.json` expose the current contract.

| Boundary | Responsibility |
| --- | --- |
| `schemas/` | Validated request/response types; omission versus null; portable filters |
| `routes/v1/` | HTTP parameters, scope dependencies, schemas and error responses |
| `services/` | Authentication, process-wide database/filesystem clients and optional external services |
| `persistence/contracts.py` | Typed `Database` facade and repository interfaces |
| `persistence/postgres/` | Transactions, relational constraints, filtering and ranked retrieval |
| `persistence/weaviate/` | Optional adapter, collections and backend queries |
| `filesystem/`, `media/` | Storage interface, local/S3 adapters, page layouts, images, OCR spans and face crops |
| `seeding/`, `cli/`, `alembic/` | Synthetic fixtures, operator commands and reviewed migrations |

Routes receive `DatabaseDependency`; services and seeds use repositories rather
than exposing SQLAlchemy sessions or backend clients across that boundary.
Documents, pages and images are projections of the source repository. Media is
stored outside SQL through `Filesystem`; PostgreSQL contains its identities and
relationships. See [Database](DATABASE.md).

## Access rules

Protected routes accept either a bearer JWT or `X-API-Key`. Sending both returns
400; missing/invalid credentials return 401; insufficient scopes return 403.
JWT login checks Argon2 hashes in the users JSON file in the configured storage.
Refresh sessions rotate and live in process memory, so a restart invalidates
them and multiple workers require routing to the issuing worker.

| Scope | Representative operations |
| --- | --- |
| `people-gator:browse` | Lists, searches, media reads and filter-option lookups |
| `people-gator:annotate` | Create/edit identities, patch faces and mentions, change/verify links |
| `people-gator:ingest` | Register sources, create faces/mentions and upload page assets |
| `people-gator:admin` | Administrative deletion, identity merges, users and face-model registration |

Scopes are explicit; do not assume admin automatically grants every other scope.
Consult each route's dependency for the precise requirement. Mutation actors
carry the database user ID and optional registered API-key ID. API-key hashes and
secrets stay in the credential file, never in the SQL registry; see
[API-key authentication](../people-gator-api/docs/API-KEYS.md).

The browser requests all four scopes and automatically uses `test` / `test`
unless build-time variables override them. Tokens live in `sessionStorage`.
`VITE_*` values are browser-visible; this mechanism is suitable for demo data and
must not distribute a privileged production credential.

## Search and annotation behavior

GET `/api/v1/search-entities`, `/search-faces`, `/search-pages` and
`/search-documents` accept namespaced query/filter parameters. Text and selected
reference-face vectors rank candidates independently, aggregate within each
modality and combine ranks with RRF. Results use higher-is-better scores and UUID
tie-breaking. Ordinary lists use UUID order. Opaque cursors belong to their
original query/filter inputs. See [Search filters](SEARCH_FILTERS.md).

Faces and text mentions have mandatory source provenance and optional identity
assignment. Assigned links have an `automatic`, `manual` or `verified` state;
unassigned links have no state. Verification records a server UTC timestamp and
actor. Reassigning, unlinking or transferring a link during a manual merge clears
its old verification. PostgreSQL applies transitions under locks and protects
them with constraints/triggers. Actual evidence and identity changes update
last-processing metadata in the same transaction; identical writes and reads
do not fabricate a new processing event.

The optional Weaviate adapter does not supply PostgreSQL transaction guarantees:
multi-object writes can partially succeed and cross-process updates use whole
object replacement. Some operations are unsupported. Do not substitute it for
the PostgreSQL migration, seed or maintenance workflows.

## Frontend

[`router/index.ts`](../people-gator-app/src/router/index.ts) maps `/scans`,
`/documents`, `/people`, `/people/:personId` and the library/document/page route
to views. `/` redirects to scan search. `src/client/` is generated from OpenAPI;
`src/query/` owns transport, authentication, query keys and mutations;
`src/viewmodels/` owns screen state, filters, assignment and presentation logic.
Views compose `components/custom/` and shadcn-vue primitives in `components/ui/`.

TanStack Vue Query caches server state. Filters and searches are synchronized
with router query parameters; changes reset cursor pagination and select a new
cache entry. Page media uses managed object URLs. Vitest covers these query,
viewmodel and component contracts. Update the SDK by exporting a local schema as
described in [Development](DEVELOPMENT.md#updating-the-api-client).

## Runtime topology

Development can run native API/Vite processes against a Docker PostgreSQL store,
or use `compose.dev.yaml` with Traefik and Compose Watch. Production-format
frontend images serve static assets through unprivileged nginx; backend images
validate the migrated PostgreSQL schema before accepting traffic. PR previews
use one database and storage volume per PR and immutable image digests. The
`people-gator-deploy` utility, installed from the reviewed `main` workflow
revision, also runs staging and tagged releases. Descriptors and state stay
outside its versioned installations.
See [Deployment](DEPLOYMENT.md) and
[Observability](OBSERVABILITY.md).
