# Start here

Read the [project overview](../README.md) and [Vision](VISION.md), then use
[Development](DEVELOPMENT.md) to install dependencies and run a synthetic local
instance. No project data or external inference credentials are needed for that
path. Read [AGENTS.md](../AGENTS.md) before editing and use an issue branch based
on `main` as described in [Contributing](../CONTRIBUTING.md).

## Explore the synthetic instance

1. Start the database, migrate, run the seed twice, then start API and Vite.
2. Search people for **Ada Novak**. Inspect her profile, aliases, linked faces
   and OCR mentions. Other fixtures include faces-only, mentions-only and
   evidence-free people.
3. Open **Lina Archivist** for the compact person review page. Faces starts with
   two rows; expand for all linked faces, then review Found faces and Similar
   people below. Mentions provides Flat, Document, Page and Mention views with
   selection for Verify/Unlink. Details keeps profile editing and Statistics
   shows link states and last changes.
4. Open the application root to land on **Documents** and explore registered
   documents in the table across libraries. Compare document-wide page/evidence
   totals and last-change metadata. Use
   **Columns** to choose fields, including All annotations, Faces and Text mentions
   count groups and the optional **First page** thumbnail.
   Click a sortable heading to sort; click again to reverse the order. Horizontal
   scrolling keeps the page width bounded, and reaching the final row loads the
   next cursor batch. The PeopleGator logo
   and first breadcrumb return here. Open **Scan search** for pages and evidence;
   follow a result into its page workspace and inspect the OCR/face overlays. Use the
   **Document pages** strip below the scan to open other pages of that document.
5. On disposable data, change an identity field or assignment and inspect its
   last-processing metadata. Try link-state filters and the mobile filter toggle.
   Review fixture details in the
   [seed guide](../people-gator-api/docs/PREVIEW-SEEDING.md).

## Check the API without printing credentials

With the synthetic native instance running, open `/login.html` at the frontend
origin and submit the provisioned demo account at the issuer. The OIDC callback
returns to the app. Open `/docs`, authorize with the same provider session and
use **Try it out** for `/api/v1/me` or an entity search. Tokens stay in memory and
are not printed. For a reproducible desktop/mobile journey, run:

```sh
OIDC_APP_ORIGIN=http://localhost:5173 OIDC_AUTHORITY=http://localhost:5173 \
  node people-gator-app/scripts/check-oidc-login.mjs
```

For exact endpoint bodies and parameter names use the running API's `/docs` or
export OpenAPI locally. See [Search filters](SEARCH_FILTERS.md) for query rules.

## Navigate the code

| Task | Start reading here |
| --- | --- |
| API initialization/configuration | `people-gator-api/src/people_gator_api/app.py`, `settings.py`, `services/database_service.py` |
| API request or filter | `routes/v1/`, `routes/v1/query_dependencies.py`, corresponding `schemas/` module |
| Persistence change | `persistence/contracts.py`, `persistence/postgres/`, `alembic/versions/` |
| Identity/evidence transition | `persistence/entity_links.py`, Postgres repositories, `schemas/entity_links.py` |
| Media/layout/crops | `media/`, `filesystem/`, `services/filesystem_service.py` |
| Frontend screen | `people-gator-app/src/router/index.ts`, `views/`, `viewmodels/`, `query/` |
| Generated contract | `people-gator-app/src/client/`, `openapi-ts.config.ts` |
| Preview fixtures and operators | `seeding/`, `cli/`, `deploy/people-gator-deploy/` |

The [Architecture](ARCHITECTURE.md) guide connects those modules; the
[Database](DATABASE.md) guide maps SQL tables and IDs. Paths above are relative
to the repository, except frontend subdirectories within `people-gator-app/src`
and backend subdirectories within `people-gator-api/src/people_gator_api`.

## Test before touching project data

Run frontend `npm run build` and `npm run test:unit -- --run`. Run backend
`uv run --locked pytest tests` with the disposable PostgreSQL URLs in
[Development](DEVELOPMENT.md#test-stores-and-validation) to enable integration and
migration coverage. Keep skipped service tests distinct from executed passes.
Do not point destructive schema tests at your seed store or an external dataset.

For a feature change, run its focused tests during implementation and the relevant
CI checks before opening the PR. Add a usable synthetic fixture and preservation
coverage for changed visible/data behavior, following AGENTS.md. Use the
[PR guidance and template](../CONTRIBUTING.md#writing-a-pull-request) to report
results and applicable desktop/mobile screenshot evidence. Documentation
changes need link/command/contract checks; do not change application behavior
merely to make a documentation example appear to work.

Documents and Scan search also offer **Minimum annotations**: choose All
annotations, Faces or Text mentions, then a state and inclusive minimum.
Use several minima together, remove their tags individually, and sort by the
same counts. Document count headers offer the same ordering as the selector.
See [count rules and URL fields](SEARCH_FILTERS.md#annotation-count-ordering-and-minima-78)
and the seed guide's `annotation-count-documents`/`annotation-count-pages` examples.

Documents columns keep fixed widths when sorting, filtering or loading more rows.
Full titles wrap over multiple lines within a row. Use the table's horizontal
scroll region to reach additional fields on narrow screens. The preview manifest's
`document-table-widths` link provides contrasting short/long titles and local media.

People search supports admin merges: search **Rina Merge**, select records (Shift
adds an inclusive range in display order), then choose **Last selected (name)** or
**First selected (name)**. Both merge immediately into the named person. Clear
resets selection. Only loaded, explicitly selected people participate; changing
search/filters clears selection, while sorting preserves selection order for
people still loaded. See the seed guide for disposable practice data.

The corner checkbox starts or toggles person selection. Before selecting, a card
opens its person; while selecting, card clicks only add people and never remove
them. Use a checkbox to remove someone, or Shift-click a checkbox or card to add
an inclusive range. Clear restores normal navigation.

The scan workspace's top-bar breadcrumbs show the stored document name and page
number when available, falling back independently to archive UUIDs. The document
breadcrumb opens that document's pages. Explore the seed CLI's
`breadcrumb-*` links for named, missing-metadata and long-title examples.
