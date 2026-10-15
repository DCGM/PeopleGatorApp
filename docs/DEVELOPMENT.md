# Local development and test stores

Run commands from the directories shown. Use an existing checkout; in Codex cloud
each task is already isolated, so do not create a worktree unless requested.
Keep credentials, `.env` files, media and disposable databases out of Git.

## Prerequisites and installation

Use Git, Docker with a working daemon, Node satisfying
`^22.18.0 || >=24.12.0` (Node 24 for CI parity), and uv. The API's
`.python-version` selects Python 3.14; uv can install the managed interpreter.
In Codex cloud, when the home directory is read-only, set writable cache/tool
locations before installing or running uv/npm:

```sh
export UV_CACHE_DIR=/workspace/.cache/uv
export UV_PYTHON_INSTALL_DIR=/workspace/.python
export npm_config_cache=/workspace/.cache/npm
```

Use the committed lockfiles instead of refreshing dependency versions:

```sh
cd people-gator-api
uv sync --locked --python 3.14
cd ../people-gator-app
npm ci --prefer-offline --no-audit --no-fund
cd ..
```

## Native API and Vite with Docker PostgreSQL

This workflow needs no project dataset, S3 credentials, embedding server or
OpenRouter key. Port 55432 keeps its database separate from a host PostgreSQL
using 5432. All passwords below are disposable local development examples.

From the repository root, create the store once:

```sh
docker run -d --name people-gator-dev-db \
  -e POSTGRES_USER=test -e POSTGRES_PASSWORD=test -e POSTGRES_DB=people_gator \
  -p 127.0.0.1:55432:5432 \
  -v people-gator-dev-postgres:/var/lib/postgresql/data pgvector/pgvector:pg16
```

For later sessions run `docker start people-gator-dev-db`. Wait until
`docker exec people-gator-dev-db pg_isready -U test -d people_gator` succeeds.
Preserve the named volume if you want to keep annotation edits.

Create `people-gator-api/.env` with the following content, or merge it into your
existing local configuration without overwriting user settings:

```dotenv
PEOPLE_GATOR_API__PERSISTENCE={"postgres":{"host":"127.0.0.1","port":55432,"user":"test","password":"test","database":"people_gator","schema_mode":"validate"},"weaviate":null}
PEOPLE_GATOR_API__STORAGE={"local":{"root":".cache/storage"},"s3":null}
PEOPLE_GATOR_API__HOST=127.0.0.1
PEOPLE_GATOR_API__PORT=8000
PEOPLE_GATOR_API__JWK__ISSUER=http://localhost:5173
PEOPLE_GATOR_API__JWK__AUDIENCE=localhost
```

Exactly one persistence configuration and one storage configuration must be
non-null. Do not add `ENABLED` flags; current settings select by presence.
Environment variables override `.env` values. Launch from `people-gator-api`
because the storage path and `.env` lookup are relative to that working directory.

Initialize local users, migrate and seed from `people-gator-api`:

```sh
mkdir -p .cache/storage/peoplegator_api
test -e .cache/storage/peoplegator_api/users.json || \
  cp example.users.json .cache/storage/peoplegator_api/users.json
uv run --locked python -m people_gator_api.cli.database migrate
uv run --locked python -m people_gator_api.cli.seed
uv run --locked python -m people_gator_api.cli.seed
uv run --locked python -m people_gator_api.cli.database check
uv run --locked people-gator-api
```

Run each command only after the preceding one succeeds. The second seed run
demonstrates repeatability; existing edits and checkpoint identities are retained.
The supplied users file provides `test` / `test`. It is local demo authentication,
not an account to expose with private collection data. For API reload, set
`PEOPLE_GATOR_API__RELOAD=true` before starting the process.

Create `people-gator-app/.env.local`:

```dotenv
VITE_API_BASE_URL=http://localhost:8000
VITE_API_USERNAME=test
VITE_API_PASSWORD=test
```

In a second terminal, from `people-gator-app`:

```sh
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Set the API base explicitly: without it the client falls back to a remote
development server. The app automatically logs in with the configured demo
credentials and requests all four scopes. `VITE_*` values enter browser code.

## Readiness and first checks

The API must complete startup/schema validation. Check its functional health:

```sh
curl --fail http://127.0.0.1:8000/api/v1/health
curl --fail http://127.0.0.1:5173/
```

Health should return `{"status":"ok"}` and the frontend should return Vite's
application HTML. In a browser, use people search for Ada Novak and inspect her
faces and OCR mentions, then open a seeded document/page. Authenticate an API
request through `/token/login` and verify `/api/v1/entities` returns fixtures;
see [Start here](START_HERE.md). A running PID alone does not establish readiness.
Codex onboarding supports local HTTP validation, not user-facing localhost links.

Use this running synthetic instance or the PR preview to capture required
desktop/mobile screenshots from the PR revision. Follow the
[PR evidence policy](../CONTRIBUTING.md#writing-a-pull-request) for changed
screens/states, viewport labels and embedding images; report actual browser
checks separately from screenshots and keep blocked required captures in a draft PR.

## Test stores and validation

The [testing strategy](TEST.md) explains current coverage, when to write each kind
of test and priorities for future coverage. This section covers local execution
and disposable-store setup.

Frontend checks from `people-gator-app`:

```sh
npm run build
npm run test:unit -- --run
```

`build` runs type checking and Vite compilation. Lint/format scripts perform
automatic writes; use them deliberately and inspect the diff.

Backend tests can run without a live store: `uv run --locked pytest tests` from
`people-gator-api` exercises unit and mocked-service behavior, while opt-in
database checks skip. For full PostgreSQL coverage create **separate disposable
databases**, never point test URLs at the seeded development or production store:

```sh
docker exec people-gator-dev-db psql -U test -d postgres -v ON_ERROR_STOP=1 \
  -c 'CREATE DATABASE people_gator_tests' \
  -c 'CREATE DATABASE people_gator_schema_tests'
```

Create each only if absent on subsequent runs. In a dedicated shell from
`people-gator-api`, override inherited development settings:

```sh
export PEOPLE_GATOR_API__PERSISTENCE='{"postgres":{"host":"127.0.0.1","port":55432,"user":"test","password":"test","database":"people_gator_tests","schema_mode":"bootstrap"},"weaviate":null}'
export PEOPLE_GATOR_API__STORAGE='{"local":{"root":"/tmp/people-gator-tests"},"s3":null}'
export PEOPLE_GATOR_POSTGRES_TEST_URL=postgresql+asyncpg://test:test@127.0.0.1:55432/people_gator_tests
export PEOPLE_GATOR_SCHEMA_TEST_URL=postgresql+asyncpg://test:test@127.0.0.1:55432/people_gator_schema_tests
uv run --locked pytest tests
```

Schema tests drop/recreate objects. Reuse only disposable stores. Optional live
Weaviate coverage needs its own service and
`PEOPLE_GATOR_WEAVIATE_TEST_HTTP_PORT`/`PEOPLE_GATOR_WEAVIATE_TEST_GRPC_PORT`;
it is not required for the PostgreSQL path. CI also tests the migration/seed CLI
twice in a third isolated database and runs preview-controller tests:

```sh
python3 deploy/preview/tests/test_preview.py -v
python3 deploy/preview/tests/test_installation.py -v
python3 deploy/preview/tests/test_observability.py -v
```

Run those three from the repository root. The host guide explains opt-in Docker
database-isolation and real log-delivery checks.

For the disposable media-upload concurrency investigation, see
[Reproduce media upload connection starvation](../people-gator-api/docs/MEDIA-UPLOAD-CONCURRENCY.md).
It starts its own PostgreSQL container and local S3 endpoint and checks the
connection-pool saturation threshold without using the development store.

## Compose Watch alternative

From the repository root, create a root `.env` (distinct from the API `.env`)
with `POSTGRES_USER=people_gator`, `POSTGRES_PASSWORD=people_gator` and
`POSTGRES_DB=people_gator`. Then run:

```sh
docker compose -f compose.dev.yaml up --build --watch
```

Use a Compose version supporting Watch and `initial_sync` (2.32+). This starts
Traefik, PostgreSQL, API reload and Vite at the default HTTP port 8080. For
rootful Docker set `DOCKER_SOCKET=/var/run/docker.sock`; the default expects a
rootless socket. `HTTP_HOST`, `HTTP_PORT`, `PUBLIC_ORIGIN` and
`HTTP_API_BASE_URL` change routing/client origins. Development Compose bootstraps
schema and mounts the sample users file, but does not automatically seed. To
use the synthetic data, migrate/adopt before seeding:

```sh
docker compose -f compose.dev.yaml exec backend \
  uv run --locked python -m people_gator_api.cli.database migrate --adopt-bootstrap
docker compose -f compose.dev.yaml exec backend \
  uv run --locked python -m people_gator_api.cli.seed
```

For retained stores, follow the migration guide when schema changes arrive;
bootstrap alone cannot add missing columns. `docker compose down` stops the
stack; `down -v` deletes its data and is appropriate only for a deliberate reset
of disposable stores.

## Updating the API client

Use the normal API configuration, then export the local contract without starting
services, from `people-gator-api`:

```sh
uv run --locked python scripts/export_openapi.py /tmp/people-gator-openapi.json
```

From `people-gator-app`:

```sh
npm run openapi-ts -- --input /tmp/people-gator-openapi.json
npm run type-check
```

Review and commit intended `src/client/` changes with the API contract change.
Do not hand-edit generated client files or fetch a different deployed server's
schema to represent your local change.
