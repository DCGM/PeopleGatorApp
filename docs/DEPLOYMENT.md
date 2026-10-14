# Docker deployment, configuration and CI/CD

## Choose a deployment workflow

| Workflow | Entry point | Intended use |
| --- | --- | --- |
| Native API/Vite and Docker database | [Development](DEVELOPMENT.md) | Local coding and disposable tests |
| Compose Watch | `compose.dev.yaml` | Local reload; schema bootstrap and sample users |
| Existing live preview | `compose.live-preview.yaml` | Developer-managed shared host with external Traefik and S3 |
| PR preview | [Host installation](../deploy/preview/README.md) | Isolated synthetic review environment per same-repository PR |
| Production-format images | `people-gator-api/Dockerfile`, `people-gator-app/Dockerfile` | Building blocks for a separately configured release deployment |

There is no general production Compose/release workflow supplied here.
`compose.live-preview.yaml` uses development images/reload and a fixed hostname;
it is not a production release template. It needs the existing `web` network,
Traefik/TLS and S3 settings. Its startup migrates/adopts before API validation;
see [Database migrations](../people-gator-api/docs/database-migrations.md).

## Production-format images

From the repository root:

```sh
docker build -t people-gator-api:release people-gator-api
docker build --build-arg VITE_API_BASE_URL=/ \
  -t people-gator-app:release people-gator-app
```

The API image installs locked runtime dependencies, packages Alembic revisions
and runs as UID/GID `10001:10001`. Its entrypoint supports `api`, `migrate`, `seed`
and `check`; `api` forces reload/debug off and PostgreSQL validation on.
The frontend serves built assets through unprivileged nginx on port 8080 with
`/healthz`. API base URL is a **build-time** argument. `/` uses same-origin routing:
your proxy must send `/api`, `/token/`, `/.well-known/`, `/docs`, `/redoc` and
`/openapi.json` to the API and other paths to the frontend.

Provision PostgreSQL/pgvector and a private container network first. Configure a
migration role and restricted runtime role; initialize local volume ownership,
install a reviewed users file, and keep runtime settings outside Git. Then run
one migration job, check readiness, and start the API only after success:

```sh
docker run --rm --network production --env-file migration.env \
  people-gator-api:release migrate
docker run --rm --network production --env-file runtime.env \
  people-gator-api:release check
docker run -d --name people-gator-api --network production \
  --env-file runtime.env -v people-gator-storage:/data \
  people-gator-api:release api
```

The `production` network and environment files above are operator-provided, not
repository files. Start the frontend image on that network and configure your
HTTPS proxy; verify API health, authentication, media and frontend requests through
the real routed origin. Migration jobs must not run concurrently per replica.
Face-model registration creates indexes and needs DDL privileges: provision models
before runtime use with a restricted role. Seed only intentionally synthetic
demo/preview stores, not a real release database. Follow the
[production startup guide](../people-gator-api/docs/production-startup.md) for
privileges and exact validation limits and [Data maintenance](DATA_MAINTENANCE.md)
for backup/restore review.

The current browser embeds automatic demo login credentials and requests all
scopes. Replacing this with a reviewed user login flow is required before treating
the application as a production access-controlled UI. Changing `VITE_*` values
cannot make embedded credentials secret.

## Configuration reference

The source of truth is
[`settings.py`](../people-gator-api/src/people_gator_api/settings.py). Settings use
`PEOPLE_GATOR_API__` and nested `__`, load API-working-directory `.env`, and allow
environment overrides. Exactly one persistence object and one storage object must
be non-null. No `ENABLED`/`BACKEND` selectors are used. JSON configuration can
explicitly set the unused object to null, as in [Development](DEVELOPMENT.md).

| Setting/group | Purpose/default |
| --- | --- |
| `HOST`, `PORT`, `RELOAD`, `DEBUG`, `LOG_LEVEL` | API listen address/8000, reload and debug false, INFO logging |
| `PERSISTENCE__POSTGRES__HOST/PORT/USER/PASSWORD/DATABASE` | Required PostgreSQL connection fields; avoid configuring Weaviate alongside it |
| `PERSISTENCE__POSTGRES__SCHEMA_MODE` | `bootstrap` by default; use `validate` for migrated stores |
| `PERSISTENCE__POSTGRES__STARTUP_TIMEOUT_SECONDS` | Connectivity timeout 60 seconds; retry interval 2 seconds |
| `STORAGE__LOCAL__ROOT` | Local filesystem root; default `./storage`; volume must be writable by API UID |
| `STORAGE__S3__ACCESS_KEY_ID/SECRET_ACCESS_KEY/BUCKET_NAME/REGION/ENDPOINT_URL` | S3 backend, mutually exclusive with local configuration |
| `JWK__USERS_PATH`, `JWK__KEY_PATH` | Relative storage keys `peoplegator_api/users.json`, `peoplegator_api/jwks.json` |
| `JWK__ISSUER`, `JWK__AUDIENCE` | Match the intended application origin/identity namespace; defaults target the historical preview host |
| `API_KEYS__KEYS_PATH` | API-key credential file key, default `peoplegator_api/api-keys.json` |
| `CORS__ALLOW_ORIGINS`, `CORS__ALLOW_ORIGIN_REGEX` | JSON list and regex; default regex permits loopback HTTP(S) |
| `BATCH__MAX_*_BATCH_SIZE` | Entity, face, text-mention and media limits; each defaults to 10,000 |
| `PAGE_IMAGE_CACHE`, `ALIGNED_FACE_CROP`, `PAGE_LAYOUT`, `IMAGE_CONTENT` | Media/cache prefixes, sizes and rendering controls |
| `EMBEDDING_SERVICE__*` | Optional external embedding endpoints and request timeout |
| `OPENROUTER__API_KEY/MODEL/BASE_URL` | Optional translation service configuration; keep key in secret storage |
| `OTEL__ENABLED`, `OTEL__HTTP_ENDPOINT` | SDK telemetry opt-in and HTTP exporter endpoint; see [Observability](OBSERVABILITY.md) |

For local storage in `runtime.env`, for example:

```dotenv
PEOPLE_GATOR_API__STORAGE={"local":{"root":"/data"},"s3":null}
```

Users and API-key credential files contain Argon2 hashes and allowed scopes and
are read through the selected filesystem. Preserve their keys and JWK material
across deployments. A missing users file is initialized empty, not with a built-in
account. The shipped example supplies demo `test` / `test`. Refresh sessions live
in memory and do not survive API restarts. See
[API-key authentication](../people-gator-api/docs/api-keys.md).

Frontend `VITE_API_BASE_URL`, `VITE_API_USERNAME` and `VITE_API_PASSWORD` are
browser-visible build-time variables. `ALLOWED_VITE_HOSTS` affects the development
server only. Development Compose uses root `.env` values `POSTGRES_*`,
`HTTP_HOST`, `HTTP_PORT`, `PUBLIC_ORIGIN`, `HTTP_API_BASE_URL`, `DOCKER_SOCKET` and
optional `OPENROUTER_API_KEY`; it maps them to container settings.

## CI and preview lifecycle

[`pr-ci.yml`](../.github/workflows/pr-ci.yml) runs on pull requests using the exact
head commit on a self-hosted Linux x64 runner labeled `people-gator-ci`:

1. Frontend: Node 24, `npm ci`, type-check and Vitest.
2. Backend: Python 3.14/uv locked sync, isolated PostgreSQL test databases,
   migration → seed → seed → check CLI smoke test, then pytest.
3. Trusted preview-controller tests checked out from the workflow commit in a
   separate location, including optional DB isolation checks enabled in CI.
4. After checks pass, same-repository PRs build both production Dockerfiles and
   publish run/attempt-specific tags to GHCR. Fork PRs receive tests but no image
   publication/deployment. Images carry the tested revision label.

[`pr-preview.yml`](../.github/workflows/pr-preview.yml) runs the installed trusted
controller on the separate `people-gator-preview` runner after successful PR CI.
It verifies repository/open-PR/current-head identity, checks host installation,
pulls candidate images, verifies their revisions and deploys by immutable digest.
Deployment order is storage initialization → migration → seed → backend/frontend
health checks. A failed seed blocks success. Existing database, media and JWT keys
survive successful preview updates. Each PR uses a restricted database role.

Close events clean up that PR's containers, storage, database and role; hourly and
manual reconciliation retry missed cleanup. Shared PostgreSQL, pgAdmin and logging
remain running. A failed migration has no automatic schema rollback, even if the
previous application continues running.

Install the controller/Compose/collector from a reviewed `main` checkout using
the [complete host guide](../deploy/preview/README.md). PR code must never replace
trusted host files. In `config.json`, set `repository` to
`DCGM/PeopleGatorApp`: the example currently names the older `DCGM/people_gator`.
GHCR image names are derived from the configured repository. Provision the
documented DNS, Traefik, logging network, runner isolation and token permissions
before enabling deployment. This documentation change does not deploy or publish
any application environment.

