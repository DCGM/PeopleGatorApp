# Docker deployment, configuration and CI/CD

## Choose a deployment workflow

| Workflow | Entry point | Intended use |
| --- | --- | --- |
| Native API/Vite and Docker database | [Development](DEVELOPMENT.md) | Local coding and disposable tests |
| Compose Watch | `compose.dev.yaml` | Local reload; schema bootstrap and sample users |
| Existing live preview | `compose.live-preview.yaml` | Developer-managed shared host with external Traefik and S3 |
| PR preview | [`people-gator-deploy pr`](../deploy/people-gator-deploy/README.md) | Isolated synthetic review environment per same-repository PR |
| Staging | [`people-gator-deploy staging`](../deploy/people-gator-deploy/README.md) | Every successful `main` build on retained database snapshot; storage managed externally |
| Tagged release | [`people-gator-deploy release`](../deploy/people-gator-deploy/README.md) | Production stack for `v*` tags on tested `main` commits |
| Self-contained production | [`compose.prod.yaml`](#self-contained-production-compose) | Production images with bundled PostgreSQL, deployed to any host with external Traefik |
| Production-format images | `people-gator-api/Dockerfile`, `people-gator-app/Dockerfile` | Building blocks for a separately configured deployment |

The packaged release stack (`compose.release.yaml`) is the supplied production
template: no reload, debug, seed or development mounts, separate migration and
runtime roles, external PostgreSQL/storage/proxy. See its access-boundary
prerequisite below. `compose.live-preview.yaml` uses development images/reload and a fixed hostname;
it is not a production release template. It needs the existing `web` network,
Traefik/TLS and S3 settings. Its startup migrates/adopts before API validation;
see [Database migrations](../people-gator-api/docs/DATABASE-MIGRATIONS.md).

## Self-contained production Compose

[`compose.prod.yaml`](../compose.prod.yaml) builds both production Dockerfiles
and runs the API, frontend and a pgvector PostgreSQL database. Traefik is
external: the stack joins its Docker network and adds router labels. Each target
environment is one env file; copy [`deploy/prod/example.env`](../deploy/prod/example.env)
to `deploy/prod/<env>.env` (ignored by Git) and set at least `APP_HOST`,
`POSTGRES_PASSWORD`, `IMAGE_REGISTRY`/`IMAGE_TAG` and `TRAEFIK_NETWORK`.

The frontend is built for same-origin routing (`VITE_API_BASE_URL=/`), so the
same images serve every environment. Build and push once, then deploy anywhere:

```sh
f="-f compose.prod.yaml --env-file deploy/prod/staging.env"
docker compose $f build && docker compose $f push      # build host
docker compose $f pull && docker compose $f up -d --no-build --wait   # target host
```

Startup order: `db` healthy → `storage-init` (gives `10001:10001` ownership of the
`api-data` root and, if `USERS_FILE` is set, validates it and writes it to the
configured storage, local or S3) → one-shot `migrate` → `backend`
healthy → `frontend`. Re-running `up -d` reruns the idempotent migration and keeps
the `postgres-data` and `api-data` volumes. A failed migration stops the rollout
before the API starts.

| Variable | Purpose / default |
| --- | --- |
| `APP_NAME` | Compose project and Traefik router prefix; unique per environment on a host (`people-gator`) |
| `APP_HOST`, `APP_SCHEME` | Routed hostname (required) and scheme (`https`); set CORS origin, token issuer and audience |
| `IMAGE_REGISTRY`, `IMAGE_TAG`, `COMMIT_SHA` | Images `<registry>/people-gator-api:<tag>` and `<registry>/people-gator-app:<tag>` and reported deployment version |
| `TRAEFIK_NETWORK`, `TRAEFIK_ENTRYPOINT` | External Traefik network (`web`) and entrypoint (`websecure`) |
| `TRAEFIK_TLS`, `TRAEFIK_CERTRESOLVER` | Router TLS (`true`) and resolver (`tlschallenge`); use `false` and empty for HTTP-only entrypoints |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_IMAGE` | Bundled database; password required |
| `USERS_FILE` | Optional users file written to the configured storage (local or S3) on every start; relative paths resolve from the repository root |
| `API_STORAGE` | Storage JSON; defaults to local `/data` in the `api-data` volume, set an S3 object instead |
| `API_ENV_FILE` | Optional dotenv file with other `PEOPLE_GATOR_API__*` settings (OpenRouter, OTEL, embeddings); values cannot override the stack's fixed settings |
| `API_LOG_LEVEL`, `BACKEND_MEMORY` | API log level (`info`) and memory limit (`4g`) |

The database sits on an internal network reachable only by `migrate` and
`backend`. The API uses the database owner role for migrations and runtime; for a
restricted runtime role, use [`compose.release.yaml`](#choose-a-deployment-workflow)
or the [production startup guide](../people-gator-api/docs/PRODUCTION-STARTUP.md).
Back up both volumes as described in [Data maintenance](DATA_MAINTENANCE.md). The
browser login limitation below applies to this stack too.

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
[production startup guide](../people-gator-api/docs/PRODUCTION-STARTUP.md) for
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
| `JWK__ACCESS_TOKEN_LIFETIME_SECONDS` | Access-token lifetime, default 7200; also the longest a disabled user's issued token stays usable |
| `API_KEYS__KEYS_PATH` | API-key credential file key, default `peoplegator_api/api-keys.json` |
| `CORS__ALLOW_ORIGINS`, `CORS__ALLOW_ORIGIN_REGEX` | JSON list and regex; default regex permits loopback HTTP(S) |
| `BATCH__MAX_*_BATCH_SIZE` | Entity, face, text-mention and media limits; each defaults to 10,000 |
| `PAGE_IMAGE_CACHE`, `ALIGNED_FACE_CROP`, `PAGE_LAYOUT`, `IMAGE_CONTENT` | Media/cache prefixes, sizes and rendering controls |
| `EMBEDDING_SERVICE__*` | Optional external embedding endpoints and request timeout |
| `OPENROUTER__API_KEY/MODEL/BASE_URL` | Optional translation service configuration; keep key in secret storage |
| `OTEL__ENABLED`, `OTEL__TRACES_ENDPOINT`, `OTEL__LOGS_ENDPOINT`, `OTEL__METRICS_ENDPOINT` | SDK opt-in and complete HTTP endpoint URLs; standard per-signal `OTEL_EXPORTER_OTLP_*_ENDPOINT` aliases are also accepted; see [Observability](OBSERVABILITY.md) |

For local storage in `runtime.env`, for example:

```dotenv
PEOPLE_GATOR_API__STORAGE={"local":{"root":"/data"},"s3":null}
```

Users and API-key credential files contain Argon2 hashes and allowed scopes and
are read through the selected filesystem. Preserve their keys and JWK material
across deployments. A missing users file is initialized empty, not with a built-in
account. The shipped example supplies demo `test` / `test`. Refresh sessions live
in memory and do not survive API restarts. See
[API-key authentication](../people-gator-api/docs/API-KEYS.md).

Frontend `VITE_API_BASE_URL`, `VITE_API_USERNAME` and `VITE_API_PASSWORD` are
browser-visible build-time variables. `ALLOWED_VITE_HOSTS` affects the development
server only. Development Compose uses root `.env` values `POSTGRES_*`,
`HTTP_HOST`, `HTTP_PORT`, `PUBLIC_ORIGIN`, `HTTP_API_BASE_URL`, `DOCKER_SOCKET` and
optional `OPENROUTER_API_KEY`; it maps them to container settings.

## CI and deployment lifecycle

One workflow, [`ci.yml`](../.github/workflows/ci.yml), runs tests, publishes
images and deploys, with the deploy jobs gated by the event. Tests and image
builds run on ephemeral GitHub-hosted `ubuntu-24.04` runners using the exact PR
head commit:

1. Frontend: Node 24, `npm ci`, type-check and Vitest.
2. Backend: Python 3.14/uv locked sync, isolated PostgreSQL test databases,
   migration → seed → seed → check CLI smoke test, pytest, the database-only
   snapshot suite, and the deployment utility tests (lifecycles, workflow steps,
   runner guard, DB isolation) from the same checkout, plus an install of the
   utility exactly as the deploy jobs perform it. CI uses no secrets or external
   services; the S3 backup and snapshot-restore suites run locally only.
3. `images`: both production Dockerfiles are built with the Actions layer cache
   and labeled with the tested commit; same-repository events publish them to
   GHCR as `sha-<commit>`. Fork PRs receive tests and a build but no publication
   or deployment.
4. Deploy jobs (`needs: images`) run on the self-hosted runners in the same run:
   `deploy-preview` for same-repository PRs, `deploy-staging` for pushes to
   `main` (and manual runs on `main` with an `operation` input),
   `deploy-release` for `v*` tags on `main`. `remove-preview` runs when a PR
   closes; `prune-previews` runs after a staging deploy, daily and on manual
   runs. The whole pipeline is visible in one run; nothing is chained through
   `workflow_run`.

Each deploy job checks out its own commit, installs
[`people-gator-deploy`](../deploy/people-gator-deploy/README.md) into the job's
temporary directory, runs `<environment> preflight`, then one operation with
`--sha <tested commit>`, then sets superseded GitHub Deployments inactive. A PR
therefore deploys with the deploy code of its own branch; staging uses `main`
and releases the tagged commit. Each environment is configured by a short list
of repository variables and secrets (`PREVIEW_*`, `STAGING_*`, `PRODUCTION_*`:
host, database URL, storage, OTel, RUM, users), listed in
[GitHub setup](../deploy/GITHUB-SETUP.md); everything else is a convention. Hosts keep only state directories and the self-hosted runners' [job-started
guard](../deploy/runner/job-started.sh), which admits only this repository's
events for the runner's environment and refuses fork pull requests
(see [host prerequisites](../deploy/people-gator-deploy/HOSTS.md#github-runners)).

The utility verifies repository/open-PR/current-head identity, pulls the
tested commit's images with temporary registry credentials, verifies their
revision labels and deploys by immutable digest. Preview order is selected PR
container removal → storage initialization → migration → seed → backend/frontend
health → routed readiness. A failed seed blocks success and fails the job.
The backend exports logs, traces and metrics directly to the operator's OTLP
collector; container output stays in local rotating `json-file` logs
([Observability](OBSERVABILITY.md)).
Existing database, media and JWT keys survive successful preview updates.
Container removal retains volumes and the database; it also replaces a previous
per-PR stack when local instance state is unavailable. Expect downtime during
preparation, including until a successful retry after a failed migration or
seed. Each PR uses a restricted database role.

Every deploy job declares its GitHub Environment with the application URL, so
each deploy appears under the repository's **Deployments**; after success only
the current deployment per environment (per PR for previews) stays active.
Closing a PR removes that PR's containers, storage, database and role and sets
its deployments inactive; the daily and post-staging prune repeats both for any
preview whose PR is no longer open. Shared PostgreSQL and Traefik remain running. A failed migration has no automatic schema rollback.

The shared PostgreSQL and Traefik are an operator-run Compose stack, [`deploy/infrastructure`](../deploy/infrastructure/compose.yaml)
([hosts](../deploy/GITHUB-SETUP.md#hosts)); the utility installs nothing and every operation first checks that the stack,
networks and Docker are up, failing with the remedy otherwise. GHCR image
names are derived from the repository. Provision the documented DNS, Traefik,
logging network, runner isolation, GitHub Environments and token permissions
before enabling deployment. No database rollback is performed automatically.
