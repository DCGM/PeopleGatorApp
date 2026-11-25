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
   the last **Add column** column (or click any of its cells) to add a hidden field,
   including Annotations, Faces and Mentions counts by mode (All, Automatic, Manual, Verified, Unassigned). Drag a header's
   centered top handle (or use ←/→ on it) to reorder columns; click a header label
   (marked by a chevron) to move it left or right or choose **Remove column**. Defaults show First page, Document
   name, NDK, Library, Pages, Linked entities, Annotations, Faces and Mentions. Column
   choices, order and resized widths persist in localStorage across reloads and browser sessions on the same browser/origin. **Restore default columns** resets all three. Use a header’s full-height sort strip on its left to cycle ascending, descending
   and default ordering. The bounded table scrolls in both directions with a sticky
   header; reaching its last row loads the next cursor batch. On desktop, the table fills the remaining viewport height (the page has no footer or title); on mobile, its section fills the viewport below the top bar. Open a document name or thumbnail to enter its first page in the viewer/editor. The PeopleGator logo
   and first breadcrumb return here. Use the **Document pages** strip below the scan to open other pages; **Expand pages** opens the full-height grid. The document breadcrumb opens this browser directly. Scans search has been retired; old document-scoped links redirect to the document browser.
5. On disposable data, change an identity field or assignment and inspect its
   last-processing metadata. Try link-state filters and the mobile filter toggle.
   Review fixture details in the
   [seed guide](../people-gator-api/docs/PREVIEW-SEEDING.md).

## Check the API without printing credentials

From `people-gator-api`, with the native instance running, this local smoke check
logs in, reads identities and performs a filtered search. It keeps tokens in
memory and prints only outcomes:

```sh
uv run --locked python - <<'PY'
import httpx

with httpx.Client(base_url="http://127.0.0.1:8000") as client:
    health = client.get("/api/v1/health")
    health.raise_for_status()
    assert health.json()["status"] == "ok"
    login = client.post("/token/login", data={
        "username": "test", "password": "test", "scope": "people-gator:browse",
    })
    login.raise_for_status()
    client.headers["Authorization"] = "Bearer " + login.json()["access_token"]
    entities = client.get("/api/v1/entities", params={"return_total_count": "true"})
    entities.raise_for_status()
    assert entities.json()["items"], "Seeded identities are missing"
    search = client.get("/api/v1/search-entities", params={
        "query.text": "Ada", "filter.entity_type": "person",
    })
    search.raise_for_status()
    assert search.json()["items"], "Expected synthetic search results"
    print("Health, login, identity list and filtered search passed")
PY
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

Page browsing keeps the document strip and expanded grid, with sorting and selected-person filtering. Cross-document scan search is retired; the backend page-search/count APIs remain available. Documents keeps only search
and sort above its table; its filter sidebar (a drawer from the sliders button
below 1024px) holds Libraries, Modified by/via key/from/to and **All
annotations**, **Faces**, **Text mentions** and **People** ranges (State, Min, Max).
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

Documents also offers optional **Created** and **Created by** columns through
**Add column**. Created by shows the registering user and API key, when used.
Sources registered before creation tracking show **Unknown**; registration retries
preserve their recorded creation. These columns support the same add/move/remove
and saved layout preferences, without creation sorting. Explore the
seed's `document-creation` link for user, API-key and legacy examples.


Use **Created by**, **Created via key**, **Created from** and **Created to** in
shared filter panels to select the creator and an inclusive
creation interval. The criteria match the listed person, face, mention or source's
own creation; modification filters remain independent. Start with the seed's
`documents-created-by`, `people-created-by`,
`faces-created-by` and `mentions-created-by` examples.


The page workspace's desktop hide buttons sit beside the viewer: the right end
of the transcription header and the left end of the People header. Reopen from
the corresponding viewer-header control. On mobile, People remains visible;
Transcription collapses upward into a labelled bar that also reopens it. Hiding
preserves settings and expanded sizes; Link/Reassign and face Search reveal
People when needed. Scan tools use a regular header above the image, scrolling
horizontally on narrow screens. Explore `page-panel-layout` or
`page-panel-layout-expanded` in the synthetic preview manifest.
