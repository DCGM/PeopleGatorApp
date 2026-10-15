# Contributing

Read [AGENTS.md](AGENTS.md) for mandatory workflow, seed maintenance and UI rules.
Use [Start here](docs/START_HERE.md) for code navigation and
[Development](docs/DEVELOPMENT.md) for local stores and validation.

## Writing an issue

Before implementation, search for a relevant existing issue and reuse it. Adapt
its description to the [change-request template](.github/ISSUE_TEMPLATE/change_request.md)
while preserving its requirements and discussion; do not open a duplicate.

For new bugs, features, documentation or maintenance work, select **Change request**
in GitHub's new-issue chooser. Until the template is merged to `main`, copy its
contents from the issue branch and omit the YAML front matter.

Complete the summary, problem/current behavior, intended behavior, scope and
verifiable acceptance criteria. Include reproduction steps and environment
details for bugs. Add a validation plan, preview/contract/documentation impact
and related work; explain conditional details with `Not applicable` where
appropriate. Put planned checks in the issue and actual results, skips and
limitations in the PR.

## Issue → main-based branch → commits → pull request

1. Read the relevant GitHub issue's full description and acceptance criteria.
   Reuse it; create one first if the work has no issue.
2. Start from current `main` and create/reuse a dedicated issue branch such as
   `issue/2-repository-documentation`. Preserve unrelated local changes; do not
   reset the checkout. Cloud tasks already have isolated checkouts and need no
   extra worktree unless explicitly requested.
3. Implement and verify coherent functional units, committing each as it is
   ready. Scope commits to the issue and explain resulting behavior.
4. Push the branch and open a PR targeting `main`. Link the issue (for example
   `Closes #2`), summarize the behavior and record checks and material limitations.
   Follow [Writing a pull request](#writing-a-pull-request) and the default
   template, including required desktop/mobile evidence. Use a draft PR while
   incomplete.
5. Address review and CI failures with further commits. Keep the PR description
   current. Merge only with authorization; do not push implementation to `main`.

## Writing a pull request

Use the [default PR template](.github/pull_request_template.md). Until it is
available on `main`, copy its contents from the issue branch into the PR body;
also use it when creating a PR through the CLI. Keep author prompts in HTML
comments or remove them after filling the sections. Start every PR description
with **Solution TL;DR** and keep it current as the implementation changes.

| Section | What to include |
| --- | --- |
| Solution TL;DR | One to three sentences explaining the problem solved and resulting behavior; include a concrete before/after example when useful. |
| Related issue | `Closes #N` when the PR completes the issue; `Refs #N` for partial work or a roadmap item that must remain open. Link other dependencies when relevant. |
| Changes | Meaningful changes in the final implementation and design choices/tradeoffs needed for review, rather than a chronological work log. |
| Validation | Exact checks actually run and outcomes, relevant manual/browser results and skipped/blocked checks with reasons. Keep plans separate from executed passes; link CI evidence where useful. |
| Screenshots | Embed the required desktop and mobile evidence described below, or briefly explain an applicable exemption. |
| Impact and limitations | Applicable API/schema/client/migration effects, preview-seed scenario and documentation updates, rollout/operator steps and known limitations. Use brief, explained `Not applicable` responses for conditional items. |

Complete the template's short checklist for issue linkage, relevant validation,
screenshots when required, and applicable seed/contract/documentation updates.
Describe the final change so reviewers can assess it without reading the
conversation or reconstructing it from commits. Use the
[testing strategy](docs/TEST.md), [seed requirements](AGENTS.md#keeping-pull-request-previews-representative)
and [seed guide](people-gator-api/docs/PREVIEW-SEEDING.md) for detailed policies.

### Frontend screenshot evidence

Every frontend feature or user-visible frontend change must include screenshots
of each major changed screen, component or interaction state in **both desktop
and mobile views**. An unrelated page or desktop-only evidence is insufficient.

- Capture the actual running application from the PR revision using synthetic
  seeded data in a [local instance](docs/DEVELOPMENT.md#readiness-and-first-checks)
  or its PR preview. Use real browser captures, not mockups; exclude private data
  and credentials.
- Label each capture with the feature/state and viewport dimensions in CSS
  pixels. Suggested defaults are desktop **1440 × 900** and mobile **390 × 844**;
  document other dimensions if used. Responsive filter changes must exercise the
  existing below-640px mobile behavior.
- Show the resulting UI and important changed states, such as expanded mobile
  filters or an open assignment dialog. For visual bug fixes, add before evidence
  when practical alongside the required after captures. Include light/dark
  evidence when theme behavior changes.
- Embed images in the PR description with meaningful alt text/captions. Preview
  URLs and videos may supplement screenshots. Use the template's H3 feature/state
  heading followed by a two-column Markdown table: label the headers **Desktop**
  and **Mobile** with their CSS viewport dimensions, and embed the matching images
  in the next rendered row. Repeat the heading/table block for each major
  feature/state, replacing placeholder headings, URLs and alt text. Update
  evidence when later commits materially change the UI.
- Backend-only, documentation-only and frontend-internal changes with no rendered
  UI impact may mark screenshots `Not applicable` with a brief reason.
  User-visible frontend changes cannot use this exemption. If capture is blocked,
  explain the blocker and keep the PR draft until required evidence is supplied.
- Screenshots supplement relevant tests and actual manual keyboard/responsive
  checks. Report those checks separately; a static image alone does not verify
  interaction or accessibility.

## Checks and contracts

Use the [testing strategy](docs/TEST.md) to choose test levels, understand current
coverage and plan future checks. Record planned validation in the issue and
executed results, skips and limitations in the PR.

| Change | Relevant validation |
| --- | --- |
| Frontend | `npm run type-check`, `npm run test:unit -- --run`; `npm run build` when compilation changes |
| Backend | Focused pytest tests plus `uv run --locked pytest tests` with disposable PostgreSQL URLs for integration coverage |
| Schema/migrations | Migration tests against a separate empty schema store; migrate, repeat, validate and exercise restricted runtime access |
| Seed or visible/data behavior | Extend seed fixtures/docs/tests; run seed twice on isolated migrated PostgreSQL and local storage |
| Preview/controller/Compose | `test_preview.py`, `test_installation.py`, `test_observability.py`; enable relevant documented live checks |
| Documentation | Verify relative links, source contracts and executable examples; distinguish tested commands from operator-only steps |

Run frontend commands in `people-gator-app`, backend commands in
`people-gator-api`, controller commands from root. CI additionally smoke-tests
migration/seed/check CLI and builds production images for same-repository PRs.
Skipped optional services are not successful integration checks. Never use project
or production stores for destructive schema tests.

Keep dependency lockfiles reproducible (`npm ci`, `uv sync --locked`). Export
OpenAPI from local settings and regenerate `src/client/` for intentional API
contract changes. Route/service code uses `Database`/`Filesystem` contracts;
mutation paths carry real actor context. See [Architecture](docs/ARCHITECTURE.md).

For user-visible behavior, schema, persistence, relationships, vectors, media,
authentication attribution or filters, update the synthetic preview in the same
change. Preserve stable keys and reviewed edits and provide scenario coverage,
not just row counts. Follow the detailed requirements in AGENTS.md. Shared search
panels use the prescribed shadcn-vue controls, wrapping/responsive layout and
accessible tags; do not restyle shared UI primitives for a screen-specific change.

## Review and operations

Never commit credentials or private datasets. Keep application changes separate
from trusted preview-host releases: after one-time operator provisioning, the
lifecycle workflow automatically publishes validated controller/Compose bundles
from its exact reviewed `main` revision without sudo. Candidate PR code must not
become the host controller. Keep operator configuration and preview state outside
release bundles; infrastructure upgrades remain explicit operator actions.
Review migrations, backup/restore and retained-data repairs before applying them;
follow [Data maintenance](docs/DATA_MAINTENANCE.md).

Document current behavior accurately and label proposals. When a command fails,
diagnose whether the environment or repository contract is wrong before altering
tests, schema or configuration. Report unresolved access/service prerequisites
and the exact checks that were not run.
