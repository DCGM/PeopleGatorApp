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
3. Open the application root to land on **Documents** and explore registered
   documents, including document groups across libraries. Switch to **Table** to
   compare document-wide page/evidence totals and last-change metadata. Use
   **Columns** to choose fields, including the optional **First page** thumbnail;
   horizontal scrolling keeps the page width
   bounded, and reaching the final row loads the next cursor batch. The PeopleGator logo
   and first breadcrumb return here. Open **Scan search** for pages and evidence;
   follow a result into its page workspace and inspect the OCR/face overlays. Use the
   **Document pages** strip below the scan to open other pages of that document.
4. On disposable data, change an identity field or assignment and inspect its
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
