# people-gator-deploy

The deployment utility for **PR previews**, **staging from `main`** and
**tagged releases**. It is a Python package (`people-gator-deploy` command and
the equivalent `people_gator_deploy.environments.Environment` API) with a pinned
boto3 S3 client. Compose files, the staging login page, the collector
configuration and the database validator ship inside the package.

The [CI workflow](../../.github/workflows/ci.yml) runs it **from the checkout of
the commit being deployed**: a PR preview uses the PR's own deploy code, staging
uses `main`, a release uses the tagged commit. Each environment is configured by
a short list of repository variables and secrets
([`deploy/GITHUB-SETUP.md`](../GITHUB-SETUP.md)); everything else is a convention. The utility installs and provisions nothing: the shared
PostgreSQL and Traefik are an operator-run Compose stack
([`deploy/infrastructure`](../infrastructure/compose.yaml)) that every operation
only **checks**, and the application stacks are plain frontend + backend Compose
files.

**Prerequisites:** Linux, Python 3.11+ with `venv`/`ensurepip`, Git, Docker
Engine and Docker Compose v2.32+, plus the proxy, DNS, runners and database in
[GITHUB-SETUP.md](../GITHUB-SETUP.md#hosts). Each deploy job builds the package
into a job-local virtual environment, which downloads `setuptools` and the pinned
S3 client dependencies from the configured package index. Database clients run
in throwaway `pgvector/pgvector:pg16` containers on the database network and
database validation runs in operation-scoped backend containers. Candidate
application code never selects backups or receives backup credentials.

## How deployments run

| Job | Runs when | Runner | Operation |
| --- | --- | --- | --- |
| `frontend`, `backend` | every push and PR (not `closed`, not the schedule) | hosted | tests, seed smoke test, this utility's tests |
| `images` | after tests | hosted | build both images; push `sha-<commit>` tags to GHCR for same-repository events |
| `deploy-preview` | same-repository PR opened/updated | `people-gator-preview` | `pr preflight`, `pr update --pr N --sha <commit>` |
| `remove-preview` | PR closed | `people-gator-preview` | `pr cleanup --pr N` |
| `deploy-staging` | push to `main`; manual run on `main` with `operation` | `people-gator-staging` | `staging preflight`, `staging update\|snapshot-init\|refresh --sha <commit>` |
| `prune-previews` | after a staging deploy, daily, manual run on `main` | `people-gator-preview` | `pr reconcile` |
| `deploy-release` | `v*` tag on `main` (also a manual run on the tag) | `people-gator-release` | `release preflight`, `release update --tag <tag> --sha <commit>` |

Every deploy job checks out its commit, installs this package into
`$RUNNER_TEMP` through [`.github/actions/deploy-tools`](../../.github/actions/deploy-tools/action.yml),
runs `<env> preflight`, then one lifecycle operation, then `deployments supersede`
(see [GitHub Deployments](#github-deployments)). Forks get tests and a local image
build only; no fork event reaches a self-hosted runner (the
[runner guard](HOSTS.md#github-runners) enforces this too).

**Prerequisite checks.** `preflight` and every operation first verify the
Docker context, Compose 2.32+, the `web` and `db` networks (and `logging` with
`OTEL_ENDPOINT`), and that the configured database answers `SELECT 1` from the database
network (both roles for production). Failures name the variable or the missing
network before any Compose command runs. Secret values are never printed.

**Build identity.** The `images` job labels each image with the tested commit and
tags it `sha-<commit>`. `--sha` names that commit; the utility pulls the tag,
verifies the `org.opencontainers.image.revision` label and deploys by immutable
digest. `GITHUB_RUN_ID`/`GITHUB_RUN_ATTEMPT` order workflow runs so an older run
never replaces a newer deployment; operator runs outside Actions compare by
commit only. Previews also require the PR to be open, same-repository and still
at `--sha`; staging requires `--sha` to be the current `main` head before
migration and again before activation; releases require the tag to resolve to
`--sha` and the commit to be on `main`.

**Concurrency.** The pipeline has one concurrency group per event and PR
(`pull_request` runs cancel superseded runs); each deploy target has its own
group that never cancels a running deployment or migration. Operations also take
host file locks (per environment, then the shared infrastructure), so several
runners on one host stay consistent.

## Configuration

Repository variables and secrets prefixed `PREVIEW_`, `STAGING_` or
`PRODUCTION_` name the host, the database URL, the S3 storage (or a preview
volume directory), the OTLP collector, the RUM client and, per environment, the
preview users, the staging backup bucket or the production migration role. The
deploy jobs pass them as `DEPLOY_<NAME>`; the utility validates them (errors name
the variable) and renders the files the Compose stacks read into the
environment's private state directory: `runtime.env` (storage, token
issuer/audience, production persistence), `telemetry.env` (OTel endpoints and
headers, RUM) for the API container only, `migration.env` (production migration
role), `users.json` (previews) and `snapshot-source.json` (staging). Unchanged
files are left alone; files for settings that were removed are deleted. The full
list and the conventions table are in [GITHUB-SETUP.md](../GITHUB-SETUP.md).

## Operator commands

Any operation can run on the host as the deployment account from a checkout of
the deployed commit, with the same values exported as `DEPLOY_<NAME>`:

```sh
export GITHUB_REPOSITORY=DCGM/PeopleGatorApp DEPLOY_HOST=preview.peoplegator.dev
export DEPLOY_DATABASE_URL='postgresql://postgres:SECRET@postgres:5432/postgres'
PYTHONPATH=deploy/people-gator-deploy/src python3 -B -m people_gator_deploy pr preflight
PYTHONPATH=deploy/people-gator-deploy/src python3 -B -m people_gator_deploy pr status --pr 123
```

Snapshot operations need boto3: use the backend environment (`uv run --locked`
from `people-gator-api` with `PYTHONPATH=../deploy/people-gator-deploy/src`) or a
venv with `pip install deploy/people-gator-deploy`. GitHub-reading operations
(`update`, `cleanup`, `reconcile`, `check`, `deployments`) need `GH_TOKEN`;
`update` also needs `GH_ACTOR` for the temporary GHCR login. State lives in
`~/.local/opt/people-gator-deploy/state/<pr|staging|release>` (`DEPLOY_STATE_DIR`
overrides it for unusual hosts).

**Moving a host from the descriptor-based setup.** Start fresh: stop and
remove the old `people-gator-preview-infra` stack, the preview and staging
containers and their volumes, then start the new shared stack
([GITHUB-SETUP.md](../GITHUB-SETUP.md#hosts)), set the variables and secrets,
install the new runner guard with `PEOPLE_GATOR_RUNNER_ENVIRONMENT` in each
runner's `.env` and run `docker context use rootless` once as the deployment
account. Delete the old descriptors (`~/.local/opt/people-gator-deploy/environments`),
versioned installations (`~/.local/lib/people-gator-deploy`),
`~/.local/bin/people-gator-deploy` and state directories. Then run the workflow
manually on `main` with `operation=snapshot-init` for staging and rerun open
PRs' CI to recreate their previews.

## Operations

| Operation | pr | staging | release | Meaning |
| --- | --- | --- | --- | --- |
| `preflight` | ✓ | ✓ | ✓ | Settings, secret files, Docker/Compose, networks and the shared PostgreSQL/collector; no changes |
| `status` | ✓ (`--pr`) | ✓ | ✓ | Read-only: configured / running / healthy, recorded SHA/images |
| `check` | ✓ (`--pr`) | ✓ | ✓ | Runtime-role database check and routed readiness; nonzero when unhealthy |
| `update` | `--pr --sha` | `--sha` | `--tag [--sha] [--backup-record]` | Deploy the tested commit's images |
| `start` / `stop` | `--pr` | ✓ | ✓ | Same images; `start` repeats the check and readiness gates |
| `logs` | `--pr` | ✓ | ✓ | Private operator output (`--tail`) |
| `cleanup` / `reconcile` | ✓ | | | Remove one closed preview / all previews GitHub reports closed |
| `snapshot-init` / `refresh` | | `--sha` | | Populate once / replace with `--backup-record` |
| `database-migrate` | | | ✓ | Migration role then runtime check, with `--backup-record` |
| `recover` | | | ✓ | Reactivate retained previous images (`--backup-record --compatibility-reviewed`) |

`people-gator-deploy deployments supersede <preview|staging|production> [--ref <branch>]`,
`deployments retire --ref <branch>` and `deployments prune` maintain GitHub
Deployments (below). Exit codes: `0` success, `1` actionable failure, `2` invalid
usage, `130` cancelled. Secret values and raw service output are never printed;
failed service output is kept in the environment's private `last-error.log`.

**State and locks.** Each environment owns one private state directory. A first
staging or release deployment refuses an existing `people-gator-staging` /
`people-gator-release` Compose project it did not create. PR updates remove the selected PR project's previous
containers before redeployment, even when local per-PR state is unavailable;
databases and volumes are retained. Operations take the environment's
`environment.lock`, so previews, staging and releases never block each other
and the shared PostgreSQL is only ever touched per database. Operations journal
`operation.json`; success state is written only after routed readiness.
Cancellation (SIGTERM or Ctrl-C) removes the operation's own containers.

## GitHub Deployments

Each deploy job declares its GitHub Environment with the application URL
(`https://pr-<N>.<domain>`, `https://<staging host>`, `https://<production host>`),
so GitHub records a Deployment per run under the repository's **Deployments**.
After a successful deploy, `deployments supersede` sets older deployments of the
same environment (for previews, of the same PR head branch) `inactive`;
`remove-preview` runs `deployments retire` for the closed PR's branch; the prune
job runs `deployments prune`, which keeps one active deployment for staging,
production and each open same-repository PR branch. History is never deleted.
These steps use the job token's `deployments: write` permission and never fail
the deployment itself.

## Environments

**PR previews.** `pr update --pr N --sha <commit>` deploys the images this run
published for an open same-repository PR whose head is still that commit;
images are verified by revision label and pinned by digest. Each preview has its
own database, role and storage, and runs container removal → storage-init →
migrate → seed → startup → routed readiness. Updates stop and remove the
selected PR project's containers and orphans without deleting its database or
media volume. Retained state keeps credentials, seeded identities, edits and
media; when local credentials are unavailable, database-role access is
regenerated after stopping the old containers. Stale and already-complete builds
leave the current deployment alone. Expect downtime during preparation; a
failed migration or seed leaves the preview stopped until a successful retry.
`pr cleanup --pr N` removes one closed preview including its database;
`pr reconcile` repeats that for every preview GitHub reports closed (API errors
never imply closure). `pr stop` stops all previews but keeps their data.

**Staging.** `staging update --sha <commit>` deploys the current `main` build
and retains the database; it never reads a snapshot, restores or seeds.
Initialize once with `staging snapshot-init`; replace the database only with
`staging refresh --backup-record <private file>` (the manual workflow run's
`operation` and `backup_record` inputs). The one-time initialization check runs
under the environment lock, so queued initializations cannot replace an already
initialized database without the refresh backup guard.

Preparation gathers the latest production archive as described below, pins its
local inode, verifies SHA-256/custom format, restores original rows into a
separate database/role, rejects changes during restore, and validates rows,
links, vectors and migration history. It then migrates, checks the runtime role
and starts the backend/frontend before recording success. Failed refreshes
retain the active database.

Application S3 storage and all media/authentication objects are managed
externally. Staging does not provision buckets/users/keys, copy or validate
media, change storage generations, or impose S3 migration requirements. Missing
media does not reject a database snapshot. Supply the running application's
storage through the `STAGING_S3_*` settings; application startup and routed
readiness remain required. Normal updates and database refreshes leave that
configuration and external storage untouched.

### Backup gathering

Provision a separate read-only identity once for the production backup prefix:
`ListBucket` restricted to that prefix, `GetObject` and `GetObjectVersion` only.
Use the [restore-reader policy example](../backup/restore-policy.example.json).
It needs no production database access, writes, deletes or application storage
permissions. Keep the backup publisher's identity separate.

Put the explicit HTTPS endpoint, region, bucket, prefix and the reader
credentials — exactly those six fields, no restore database or target settings —
in the `STAGING_BACKUP_S3_*` variables and secrets ([GITHUB-SETUP.md](../GITHUB-SETUP.md)).
Use system-trusted TLS; a private CA can be supplied through `AWS_CA_BUNDLE`. No
ambient AWS credentials, application settings or instance profile fill missing
values. Do not put backup credentials in the `STAGING_S3_*` settings or workflow inputs.

Changing the backup settings does **not** refresh the running database. The next explicit
`snapshot-init` or guarded `refresh` uses the source. Ordinary `update`,
including automatic successful-main deployments, keeps staging edits and never
reads the source or contacts the backup bucket. Existing initialization, refresh
backup-record and deployment locks remain in force.

Each snapshot operation follows this sequence:

1. List **all pages** under the configured prefix. Accept only direct-child
   `peoplegator-prod-YYYY-MM-DD.dump` names with real calendar dates. Ignore
   unrelated keys, subdirectories, incomplete uploads and invalid dates. Select
   the greatest filename date, independently of listing order or LastModified.
2. HEAD the selected key. Require publisher `sha256` (64 lowercase hex) and
   `application-revision` (40 lowercase hex) metadata, a nonempty ETag and size.
   Pin those values and any version ID for the operation. A newer dated upload
   during this operation is considered only by the **next** snapshot operation.
3. Stream a conditional `If-Match` GET, requesting the pinned version when
   available, into a mode-600 archive inside a mode-700 temporary directory in
   staging state. Check response identity, exact size, SHA-256, `PGDMP` format
   and a second HEAD. Metadata names are case insensitive. There is no persistent
   archive cache and no reuse of a previous selection.
4. Run `pg_restore --list` before provisioning. Restore into an independent
   candidate database, check the open archive for local mutation, validate the
   restored database, then recheck the current S3 identity/metadata before
   proceeding with migration and activation. A changed selected key fails even
   when an older object version remains readable. SHA/revision metadata follows
   the existing trusted publisher contract; it is not a cryptographic signature.
5. Remove the downloaded archive on ordinary success/failure. Write mode-600
   `generation-*/provenance.json` and successful active `state.json` with bucket,
   selected key/date, ETag, available version ID, size, SHA-256, source application
   revision and restored schema revision. These are private deployment evidence;
   credentials and archive contents never enter public summaries.

An empty source, access/network errors, invalid metadata, changed object, corrupt
latest archive or insufficient disk space stops the operation. There is **no
fallback to older backups** and the active staging database is retained. Public
errors give fixed guidance without relaying provider errors or private values.
Check reader grants and connectivity for gathering failures, publisher metadata
for metadata failures, and the trusted source archive for integrity/format
failures. Repair the source deliberately before retrying. Do not overwrite a dated
object as a routine fix. Ensure private disk capacity for the full compressed
archive; abrupt process/host death can leave a private `snapshot-*` directory or
unserved candidate database for operator cleanup after confirming no job is active.

**Releases.** A `v*` tag push runs the `deploy-release` job after that run's
tests and images; the workflow first requires the tagged commit to be on `main`.
The tag resolves to its commit (annotated or lightweight); a moved tag, a tag not
on `main`, or a commit other than `--sha` is rejected, and the images built for
that commit are promoted by digest. If the runtime check reports a pending
migration, delivery stops until the workflow is rerun on the tag with a
`backup_record` input (take and verify a backup first — see
[backup](../backup/README.md)); then migrate → full runtime-role check → backend
startup → routed readiness → state commit. Expect downtime while the backend
restarts. Re-delivering the deployed tag is a no-op; a tag that does not contain
the deployed commit is refused. `release recover` reactivates the retained
previous images only if their database check accepts the current schema;
changing images never undoes migrations and nothing downgrades a schema. After a
failed activation, recovery targets the last healthy committed release, including
when the first upgrade fails. After a successful activation, it targets the
retained previous release. Activation journals retain the complete environment
and recovery target; retries repair interrupted state/environment/history
publication before treating a delivery as complete. After routed readiness,
publication commits `state.json` before replacing the retained rollback files.
An interruption before that commit preserves the older rollback target; after
the commit, retries and recovery finish the remaining files from the journal.

### Release access boundary

The production stack has no reload, debug, seed or development mounts, but the
current frontend build embeds demo auto-login credentials
([DEPLOYMENT.md](../../docs/DEPLOYMENT.md)). Browser-bundled credentials are not
private authentication: place the release behind a reviewed access boundary (for
example, proxy authentication or a private network) before creating the
`PRODUCTION_*` settings.

## Development

The tests need PyYAML (for the workflow tests) and, for the snapshot suites,
boto3; the backend environment provides both:

```sh
# From the repository root with python3-yaml installed, or
PYTHONPATH=deploy/people-gator-deploy/src python3 -B -m unittest discover -s deploy/people-gator-deploy/tests -v
# through the backend environment, as CI does:
cd people-gator-api && PYTHONPATH=../deploy/people-gator-deploy/src uv run --locked python -B -m unittest discover -s ../deploy/people-gator-deploy/tests -v
# Database-backed and image-backed suites, from people-gator-api with its uv environment:
STAGING_TEST_DATABASE_PORT=… STAGING_TEST_POSTGRES_CONTAINER=… uv run --locked python ../deploy/people-gator-deploy/tests/test_snapshot.py -v
PREVIEW_TEST_POSTGRES_CONTAINER=… PYTHONPATH=deploy/people-gator-deploy/src python3 -B deploy/people-gator-deploy/tests/test_preview.py
```

The workflow tests parse `ci.yml`, execute every deploy step's script against a
stub `people-gator-deploy` and parse the recorded commands with the real CLI; the
runner-guard tests run `deploy/runner/job-started.sh` against a disposable Git
origin.

`test_staging_runtime.py` needs a backend image, an internal network aliasing
PostgreSQL as `postgres` and Docker. CI does not run it; from
`people-gator-api`, with a disposable PostgreSQL container and its published port:

```sh
docker network create --internal staging-gate
docker network connect --alias postgres staging-gate "$POSTGRES_CONTAINER"
docker build -t people-gator-staging-gate .
STAGING_TEST_NETWORK=staging-gate STAGING_TEST_IMAGE=people-gator-staging-gate \
STAGING_TEST_POSTGRES_CONTAINER="$POSTGRES_CONTAINER" STAGING_TEST_DATABASE_PORT=… \
STAGING_TEST_DATABASE_USER=… STAGING_TEST_DATABASE_PASSWORD=… \
PYTHONPATH=../deploy/people-gator-deploy/src uv run --locked python ../deploy/people-gator-deploy/tests/test_staging_runtime.py -v
```

It runs both local restore and latest-source discovery/download/restore against
disposable TLS MinIO. It verifies the newest archive's actual records and that a
corrupt newer archive creates no database. The backend environment supplies
boto3 and application dependencies; no real operator source is read.

## Browser RUM and API trace correlation

See [OpenObserve runtime configuration](../../docs/OPENOBSERVE-RUM.md) for the
`OTEL_*` and `RUM_*` settings of each environment, collector
networking, credential boundaries and rollout. The browser receives a
dedicated RUM client token through the API; backend OTLP authorization stays
server-side. No frontend build secrets are required.

### Preview application capabilities

The utility inspects the tested backend image's `org.peoplegator.auth-service`
label. Missing labels select the existing frontend/API recipe. Value `1` selects
the fixed `compose.pr-auth.yaml` recipe shipped with the package; unknown versions
are rejected before replacement. Neither label values nor PR files become host
commands outside the package's own Compose recipes.

Capability 1 runs storage initialization, migration, seed and explicit account
provisioning before starting auth/API/frontend. Only the provisioning container
receives the users file; the issuer retains its own `auth-data` volume and has
no database connection. The API uses a per-preview private issuer alias.
Existing account edits and actor UUIDs survive provisioning reruns. New issuer
keys force re-login unless retained keys are copied explicitly as an operator
step. Closure removes both preview volumes using the saved recipe selector.

The selected topology is saved in the private Compose environment and successful
preview state. An already-seeded build can be repaired when an older utility
omitted its advertised topology. Readiness requires real issuer health/JWKS
responses and the gateway; an HTTP 200 frontend fallback is insufficient.
