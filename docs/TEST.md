# Testing strategy

This guide explains what the repository tests today, how to run those checks,
which tests to write for a change and where future coverage would be useful.
Use [Development](DEVELOPMENT.md#test-stores-and-validation) for environment and
disposable-store setup, and [Contributing](../CONTRIBUTING.md) for the issue and
pull-request workflow.

## Goals and boundaries

Tests should protect observable behavior, data contracts and important failure
paths. Choose the smallest test that can detect the relevant failure; use a real
integration when correctness depends on the database, storage or HTTP boundary.
An assertion about a mock call alone does not prove that the corresponding
transaction or external service works.

Keep fixtures synthetic, deterministic and self-contained. Avoid production
data, external inference dependencies and timing-sensitive assertions. Add
tests for meaningful behavior rather than copying implementation details into
assertions. A reversible documentation or presentation edit does not need a new
automated test when link, command or focused manual checks provide adequate
verification.

## Current coverage

The examples below are representative source references, not a claim of complete
coverage. Passing these suites does not establish a coverage percentage or prove
every endpoint, browser journey or deployment works.

| Area | What is tested and how | Representative sources |
| --- | --- | --- |
| Frontend state and transport | Vitest exercises filters, URL serialization, cursor pagination, assignment state and generated-client credential selection. Query tests use fake responses or mocked transport; they do not contact a live API. | [Document filters](../people-gator-app/src/__tests__/document-filters.spec.ts), [client authentication](../people-gator-app/src/__tests__/client-auth-methods.spec.ts), [cursor query](../people-gator-app/src/__tests__/search-cursor-query.spec.ts) |
| Frontend interactions and media | Vue Test Utils mounts components in jsdom. Tests exercise active tags, mobile collapse state, keyboard selection, navigation links and object-URL cleanup. Query/viewmodel data, viewport signals or browser APIs are mocked where needed. | [Filter view](../people-gator-app/src/__tests__/PeopleProcessingFiltersView.spec.ts), [person detail](../people-gator-app/src/__tests__/PersonDetailView.spec.ts), [object URLs](../people-gator-app/src/__tests__/ObjectUrl.spec.ts), [Vitest configuration](../people-gator-app/vitest.config.ts) |
| Schemas and HTTP contracts | pytest validates request/response rules, OpenAPI routes and query parameters. In-process FastAPI clients exercise selected validation and upload behavior with dependency overrides. Some route tests inspect OpenAPI without executing a request. | [Schema contracts](../people-gator-api/tests/services/persistence/test_schema_contracts.py), [media routes](../people-gator-api/tests/routes/test_media_routes.py), [query dependencies](../people-gator-api/tests/routes/test_query_dependencies.py) |
| Authentication and scopes | Service tests use temporary credential files and real token signing/verification for login, refresh and failure cases. HTTP API-key tests exercise credential selection, revocation and scope failures with fake repositories and mocked bearer verification. | [JWT service](../people-gator-api/tests/services/test_auth_service.py), [HTTP authentication](../people-gator-api/tests/services/test_api_key_auth.py) |
| PostgreSQL behavior | Opt-in integration tests exercise real repositories, search, filters, cursors, evidence changes, processing metadata and transaction rollback. Concurrency examples include API-key registration and annotation updates. Separate SQL-shape tests use mocked sessions to inspect bounded search/HNSW queries; those are not performance benchmarks. | [Repository round trip](../people-gator-api/tests/services/persistence/test_postgres_integration.py), [processing metadata](../people-gator-api/tests/services/persistence/test_entity_touch_integration.py), [merge rollback](../people-gator-api/tests/services/persistence/test_postgres_entity_merge.py), [HNSW query tests](../people-gator-api/tests/services/persistence/test_postgres_hnsw.py) |
| Migrations and schema validation | Opt-in tests migrate disposable PostgreSQL stores, repeat migration, detect drift, preserve bootstrap data and exercise rollback. Schema validation is also tested with a restricted runtime role. | [Schema validation](../people-gator-api/tests/services/persistence/test_postgres_schema_validation.py), [bootstrap adoption](../people-gator-api/tests/services/persistence/test_bootstrap_adoption.py) |
| Synthetic preview and media | Seed tests migrate isolated schemas, use real local files and query repositories/media services. They cover vectors, filters, OCR spans, crops, rerun/edit preservation and interrupted checkpoints. Selected HTTP tests use real PostgreSQL with an overridden authentication context. Media unit tests use generated image bytes and fake storage to exercise cache/error paths. | [Preview seed suite](../people-gator-api/tests/services/persistence/test_preview_seed.py), [page images](../people-gator-api/tests/services/media/test_page_image.py), [OCR spans](../people-gator-api/tests/services/media/test_text_mention_span_service.py), [seed guide](../people-gator-api/docs/PREVIEW-SEEDING.md) |
| Storage and optional adapters | Local filesystem tests use temporary files; S3 tests use mocked clients. Weaviate repository/client tests use fakes, with a separate opt-in test against a disposable live Weaviate server. Passing mock tests does not establish live S3 or Weaviate compatibility. | [Local storage](../people-gator-api/tests/services/filesystem/test_local.py), [S3 adapter](../people-gator-api/tests/services/filesystem/test_s3.py), [live Weaviate](../people-gator-api/tests/services/persistence/test_weaviate_link_integration.py) |
| Preview lifecycle and observability | unittest checks the controller using fake commands, SQL and GitHub responses. Installation tests use temporary copies. Compose configuration checks require the Docker CLI; database isolation and actual OTLP log delivery are separate opt-in Docker checks. These do not install the controller on a real preview host. | [Controller tests](../deploy/preview/tests/test_preview.py), [installation tests](../deploy/preview/tests/test_installation.py), [log delivery](../deploy/preview/tests/test_observability.py) |

Type checking and compilation catch contract/type/build errors; they are not
behavioral test suites. The frontend currently has no configured real-browser
end-to-end runner. jsdom keyboard tests do not verify actual viewport layout,
browser focus rendering or light/dark appearance. Use the synthetic exploration
and API smoke example in [Start here](START_HERE.md#explore-the-synthetic-instance)
for manual checks until those journeys have browser automation.

## Running and interpreting checks

Install the pinned dependencies using the
[development setup](DEVELOPMENT.md#prerequisites-and-installation). Run frontend commands from
`people-gator-app`, backend commands from `people-gator-api`, and controller
commands from the repository root.

### Focused checks during implementation

Choose the files or test cases affected by the change. For example:

```sh
# From people-gator-app: filter serialization and component interactions
npm run test:unit -- --run src/__tests__/document-filters.spec.ts src/__tests__/PeopleProcessingFiltersView.spec.ts
```

```sh
# From people-gator-api: schema validation without a live database
uv run --locked pytest tests/services/persistence/test_schema_contracts.py

# With disposable PostgreSQL URLs configured as in Development
uv run --locked pytest tests/services/persistence/test_preview_seed.py -k reruns
```

Use pytest's `path/to/test.py::test_name` or `-k expression`, and Vitest's file
selection or `-t` name filter to narrow an investigation. A focused pass is useful
feedback, but does not replace relevant integration or CI checks.

### Broader local validation

```sh
# From people-gator-app
npm run type-check
npm run test:unit -- --run
npm run build
```

```sh
# From people-gator-api, with isolated test settings
uv run --locked pytest tests
```

Without live-service opt-ins, the backend suite runs unit/mocked checks and skips
database integrations. For full PostgreSQL coverage, configure
`PEOPLE_GATOR_POSTGRES_TEST_URL` and `PEOPLE_GATOR_SCHEMA_TEST_URL` using the
[disposable-store instructions](DEVELOPMENT.md#test-stores-and-validation).
Keep repository tests, destructive schema tests and the seeded development
instance separate. Seed tests migrate private schemas and use disposable local
storage; they still require a disposable database with suitable permissions.

Live Weaviate coverage needs both `PEOPLE_GATOR_WEAVIATE_TEST_HTTP_PORT` and
`PEOPLE_GATOR_WEAVIATE_TEST_GRPC_PORT` pointing at a disposable local service.
The ordinary S3 adapter tests do not need a real bucket.

```sh
# From the repository root
python3 deploy/preview/tests/test_preview.py -v
python3 deploy/preview/tests/test_installation.py -v
python3 deploy/preview/tests/test_observability.py -v
```

The [preview host guide](../deploy/preview/README.md#validation) explains
`PREVIEW_TEST_POSTGRES_CONTAINER` for actual database-isolation checks and
`PREVIEW_TEST_OTEL=1` for Docker log-delivery checks. These flags require the
documented disposable infrastructure; do not enable them against shared data.

Report passes, failures and skips separately, along with commands, relevant
service prerequisites and material limitations. A skipped integration is
unexecuted coverage. A smoke check verifies a small operational path, not every
feature. Static documentation checks validate links/claims; a documented runtime
example needs execution before it can be reported as tested.

### What PR CI runs

The [PR CI workflow](../.github/workflows/pr-ci.yml) currently runs:

1. Frontend dependency installation, type checking and the Vitest suite.
2. Backend locked dependency installation and disposable PostgreSQL databases
   for repository tests (`ci`), schema tests (`ci_schema`) and CLI smoke (`ci_seed`).
3. Real CLI migration → seed → seed → schema check using disposable local storage,
   followed by the backend pytest suite.
4. Preview-controller tests from the exact workflow commit in a separate
   checkout. The workflow enables live PostgreSQL isolation; it does not enable
   live Weaviate or OTLP log delivery.
5. After frontend/backend checks pass, production image builds and GHCR
   publication for same-repository PRs. Forks receive checks without publication.

There is no automated browser journey, performance threshold or coverage
percentage gate in that workflow. Image publication and preview deployment have
their own failure modes; passing behavioral tests alone does not mean a preview
has deployed successfully. See [Deployment](DEPLOYMENT.md#ci-and-preview-lifecycle).

## When to write each kind of test

| Change or risk | Test to add and what it should assert |
| --- | --- |
| Pure logic, parsing or validation changes | Unit tests for meaningful normal, boundary and invalid inputs. Assert outputs and failures through the public function/schema contract. |
| Frontend filters, query state or viewmodels | Unit/query tests for URL round trips, selected values, pagination resets, assignment state and error handling. Add a component test when the user's interaction is part of the requirement. |
| Visible component interactions | Vue component tests for keyboard operation, accessible names, event behavior, loading/errors and cleanup. Use a real browser or focused manual check for layout, focus, viewport and theme behavior that jsdom cannot establish. |
| API requests, responses or access rules | Route/contract tests for schemas, statuses and scope enforcement. Use real HTTP authentication plus persistence integration when correctness spans credential verification and stored actor metadata; explain any dependency override. |
| Persistence, search or evidence relationships | PostgreSQL integration tests for filters, ranking/order, query-bound cursors, constraints, assignment/verification transitions and rollback. Add concurrent cases when a change depends on locking or conflict handling. |
| Schema or migrations | Migration/schema tests for fresh stores and supported existing-data upgrades, repeated execution, drift rejection and rollback. Verify restricted runtime access where permissions are affected. |
| Preview seed or visible/data contracts | Extend the maintained seed scenario and its integration tests in the same change. Query the actual feature/media and retain rerun/edit-preservation and interrupted-checkpoint coverage. Follow [AGENTS.md](../AGENTS.md). |
| Media/storage behavior | Generated-image/local-storage tests for keys, dimensions, cache invalidation, missing assets and resource cleanup. Add live adapter checks when behavior depends on a provider rather than its mocked client. |
| Controller, Compose or observability behavior | Lifecycle/configuration tests for ordering, recovery, isolation and cleanup. Enable the relevant disposable live check for database or telemetry changes. Host installation remains an operator action from reviewed `main`. |
| Critical journeys across browser, API and storage | A small real-browser end-to-end test when the cross-layer behavior needs protection. Such a suite is future work here; record manual validation until it exists. |
| Performance-sensitive changes | A reproducible benchmark/query-plan investigation on synthetic data before setting thresholds. Ordinary SQL-shape tests do not measure latency, recall or load behavior. |
| Documentation or low-impact presentation edits | Link/anchor, source-contract and documented-command checks, plus focused manual inspection where applicable. Add an automated regression only for meaningful behavioral risk. |

Regression describes the purpose of a test, not a separate test runner. For a
bug, choose the level that reproduces the failure and show that it fails before
the fix when practical. For new behavior or changed contracts, add meaningful
acceptance coverage with the implementation in the same PR. Refactors should
retain existing behavioral coverage; new tests are useful when they close an
actual blind spot, not merely because files moved.

## Future coverage priorities

This source audit identifies boundaries to improve; it does not add those suites
or mark their proposed coverage as complete. Keep the plan current as tests are
implemented. Track a new test-suite implementation through its own agreed issue
scope before changing tooling or CI.

| Priority | Current boundary | Future coverage and when to add it |
| --- | --- | --- |
| First: critical browser journeys | Vitest uses jsdom and mocked transport/viewmodels; no browser runner is configured. | Add a small real-browser suite on migrated, seeded PostgreSQL/local storage for demo authentication, search/filter URL restoration, cursor navigation, document/page media review and persisted evidence assignment. Include actual keyboard focus, narrow viewports and theme inspection when browser automation is introduced or a critical journey changes. |
| First: HTTP authentication through persistence | Service tests sign real JWTs; HTTP security tests fake repositories/bearer verification; seeded HTTP tests override the actor. The complete login → authenticated resource write → stored attribution path is not covered by those tests. | Add integrated requests through `/token/login`, refresh and representative protected resource routes without bypassing auth. Verify JWT/API-key actors, missing/invalid/conflicting credentials, insufficient scopes, revocation/replay and unchanged records/timestamps after denied writes when the auth/attribution integration suite is introduced or those boundaries change. |
| Change-driven: existing data guarantees | Real tests already cover search/cursors, processing metadata, verification/reassignment/merge, rollback, migration/adoption and seed preservation. | Extend these suites for each new query/filter, evidence transition, migration or fixture. Add the specific collision, transaction failure, cursor edge case or historical-data scenario introduced by the change; avoid duplicating covered happy paths. |
| Change-driven: media and optional services | Local media and mocked S3 tests exist; live Weaviate/log delivery are opt-in and are not enabled by ordinary PR CI. No live S3 suite is configured. | Require relevant local media/OCR/crop regressions for geometry/cache changes. Add disposable live S3 compatibility tests before claiming provider compatibility from mock tests; run/extend existing live checks when changing Weaviate or telemetry. |
| Change-driven: scale and contention | SQL-shape and selected concurrency tests exist, but no dedicated load/benchmark gate is configured. | Establish reproducible data sizes, baseline query plans, latency/recall observations and concurrent-write invariants when search scale or locking changes. Agree budgets from measurements rather than inventing timing limits or coverage targets. |

## Contributor workflow

Before implementation, map the issue's acceptance criteria to test levels and
record the chosen commands, fixtures and service prerequisites in its Validation
plan. Select checks using the table above and the contribution guidelines.

During implementation, run focused checks and add regressions/acceptance coverage
as each coherent unit is completed. Run relevant broader checks before the PR is
ready; address test and CI findings with focused commits. Avoid re-running
unaffected suites solely to produce a longer list of checks.

In the PR, report executed results, skips and limitations, including manual
browser checks and optional services that were unavailable. Keep these results
separate from proposed tests. Update this guide when the runner, coverage
boundaries, live-test prerequisites or CI execution change.
