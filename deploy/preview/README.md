# Pull request previews

For automatic main deployments and explicit production-snapshot initialization,
see [Staging](STAGING.md). Staging retains its own database, credentials and media;
PR previews continue to use the automatic synthetic seed.

Opening, reopening, or updating a PR runs frontend type checks and unit tests,
backend unit/integration/migration tests, and preview-controller tests on a
self-hosted CI runner. Only after these pass does that runner build the existing
production Dockerfiles and push frontend/backend images to GHCR. Images have a
tag unique to the workflow run and attempt, plus the tested commit's revision
label.

Application tests and image builds use the PR's exact head commit. The preview
controller suite is checked out separately from the workflow's commit, so PR
branches created before `deploy/preview` was added can still run those checks.

CI keeps npm's package cache under the runner's tool-cache directory at
`people-gator/npm`, outside the checkout. Installs prefer cached packages and
download only missing data instead of restoring a GitHub Actions cache archive.
Image builds also use local BuildKit state, with a stable builder name for each
repository, runner, and component. The builder container is removed after the
job while its cache volume is retained for the next build. The frontend Docker
build keeps downloaded npm packages in a BuildKit cache mount across lockfile
changes. No image build cache is uploaded to or downloaded from GitHub Actions.
The first build on each runner is cold; cache reuse requires retaining that
runner's tool-cache directory and Docker volumes. Builds on other runners or
fresh disposable machines start with their own caches.

Each image matrix job uses a private temporary Docker registry configuration;
one job's completion cannot log out another job sharing the same runner account.
The selected Docker context is imported into that directory. Buildx metadata stays
in its original directory via `BUILDX_CONFIG`, so cache reuse and the setup action's
later builder cleanup keep working. Login-action logout is disabled only for these
private configs; an unconditional cleanup step deletes each job's directory.

The preview host runs a versioned controller release through a self-hosted Actions
runner. Each lifecycle job publishes its exact reviewed `main` bundle into a
runner-owned directory without sudo; operator settings and preview state stay
separate. A successful `PR CI` run triggers deployment at
`https://pr-123.preview.peoplegator.dev`. The controller queries GitHub to verify
the workflow identity, repository, open PR state and current head SHA. It pulls
the two images, checks their revision labels, and deploys by immutable digest.
There is no PR checkout, build, Docker socket mount or administrator DB password
inside the preview containers.

All previews share **one PostgreSQL 16/pgvector container**. PR 123 receives
database `preview_pr_123` and login `preview_pr_123`, with a random password and
no cluster administration privileges. Other PR roles cannot connect to its database.
Extensions are installed by the controller; Alembic migrations run from the
backend image using the PR login. The controller then runs the same image's
`seed` command before the API starts in validation mode. A seed failure blocks
candidate startup. The repeatable seed uses persistence interfaces to add
synthetic identities, linked face vectors, documents/pages, OCR mentions and local
media; see [preview seeding](../../people-gator-api/docs/PREVIEW-SEEDING.md).
Updating a preview retains its database, password, media storage and JWT keys.
GitHub CI uses one separate, temporary pgvector service per backend test run,
with separate databases on that service for contract tests, migration tests and
seed CLI smoke checks.

All PR containers (`frontend`, `backend`, `migrate`, `seed`, and `storage-init`) send
stdout/stderr through Docker's Fluentd driver to a shared OpenTelemetry Collector.
The collector exports OTLP HTTP logs to the existing LGTM backend, with PR number,
commit SHA, service name, container ID, and stdout/stderr metadata. This also
captures frontend access/error logs, migration output and seed output without
application SDK changes. The collector and a persistent pgAdmin instance belong to the shared
infrastructure project, so closing a PR leaves them running.

Closing or merging a PR removes its Compose project and storage volume, forcibly
disconnects DB sessions, then drops its database and login. Hourly reconciliation
retries missed closures and failed cleanup. Reopened PRs are protected against
delayed close events. State persists until cleanup succeeds. A host file lock
also serializes operator commands against Actions jobs.

## Install on the preview host

The host needs Linux x86-64, Python 3.10+, Docker with Compose v2.20+ and an existing
Traefik instance on Docker network `web`, with entrypoint `websecure` and resolver
`tlschallenge`, plus an OTLP HTTP backend on Docker network `logging` (both names
are configurable). Builds currently target `linux/amd64`. For rootless Docker, use
the same user/socket for the runner, controller and Traefik.

Configure the deployment runner account's Docker context before starting the
runner service (`docker context use rootless` for rootless Docker), or set
`DOCKER_HOST=unix:///run/user/<uid>/docker.sock` in the service environment. Check
`docker info` as that account. The deployment workflow preserves the selected
context when creating its temporary registry configuration; that directory is
removed after the job. An empty `DOCKER_CONFIG` otherwise hides the rootless
context and makes Docker fall back to `/var/run/docker.sock`. See
[Docker's rootless client configuration](https://docs.docker.com/engine/security/rootless/tips/#client).

1. Point wildcard DNS `*.preview.peoplegator.dev` to the Traefik host. The existing
   `tlschallenge` resolver can issue certificates for individual PR hosts. If
   Traefik already has a wildcard certificate, set `certificate_resolver` to `""`
   in the controller config to reuse it. Wildcard issuance requires DNS-01;
   [Traefik's ACME documentation](https://doc.traefik.io/traefik/reference/install-configuration/tls/certificate-resolvers/acme/)
   describes that setup.
   Also point `pgadmin-preview.peoplegator.dev` to the Traefik host; this hostname
   is outside the PR wildcard. pgAdmin uses the same HTTPS entrypoint and resolver.
2. For a **new installation**, provision settings, state and release directories
   once. Replace `preview-runner` with the deployment service account and group.
   Run these commands from a reviewed, updated `main` checkout:

   ```sh
   sudo install -d -m 755 /opt/people-gator-preview /var/lib/people-gator-preview-controller
   sudo install -m 644 deploy/preview/config.example.json /opt/people-gator-preview/config.json
   sudo install -m 644 people-gator-api/example.users.json /opt/people-gator-preview/users.json
   sudo install -d -m 700 -o preview-runner -g preview-runner /var/lib/people-gator-preview
   sudo install -d -m 700 -o preview-runner -g preview-runner /var/lib/people-gator-preview-controller/releases
   ```

   Keep `repository` set to `DCGM/PeopleGatorApp`; it must match Actions'
   `GITHUB_REPOSITORY`. Edit network/host settings for your environment.
   `otel_http_endpoint` is the OTLP HTTP base URL (default `http://lgtm:4318`,
   without `/v1/logs`); `otel_network` defaults to `logging`. `preview_log_port`
   defaults to `24224`; `pgadmin_email` defaults to `admin@peoplegator.dev`.
   The operator owns `/opt/people-gator-preview` and its configuration/users files;
   the runner owns its private state and release directories. Do not make the
   settings directory writable by the runner: directory write access permits
   replacing even read-only files. The demo users file supplies `test` / `test`;
   previews use writable synthetic data and the frontend logs into that account.
   Existing hosts must use the migration steps below, preserving their settings.
3. As the runner account, publish a reviewed release and initialize infrastructure:

   ```sh
   export PREVIEW_CONFIG=/opt/people-gator-preview/config.json
   controller_revision="$(git rev-parse HEAD)"
   python3 deploy/preview/release.py --revision "$controller_revision"
   controller="/var/lib/people-gator-preview-controller/releases/$controller_revision/preview.py"
   python3 "$controller" init
   ```

   Manual publication requires a `main` checkout with HEAD and the requested
   revision present in `origin/main`; fetch/pull before publishing. It reads Git
   blobs at the requested revision, so dirty/untracked checkout files are never
   copied. It needs Git and the Docker Compose CLI, but validation starts no
   containers and needs no GitHub token or Docker daemon. No sudo is used.

   `init` generates PostgreSQL/pgAdmin passwords in the private state directory,
   validates the collector and starts shared infrastructure. It is an explicit
   operator action, never part of automatic controller publication. Repeated
   `init` preserves passwords and volumes. Back up the state directory together
   with `people-gator-preview-infra_postgres-data` and
   `people-gator-preview-infra_pgadmin-data` before infrastructure upgrades.
4. Register the deployment runner with labels
   `self-hosted,linux,x64,people-gator-preview`. Protect/review `main` and restrict
   its runner group to this repository's
   `.github/workflows/pr-preview.yml@refs/heads/main` where supported. Labels only
   select a runner; they do not enforce that restriction. Do not allow PR CI or
   other untrusted workflows to execute on this account/host. A workflow condition
   is defense in depth, not protection against somebody allowed to change the
   workflow running on that account. GitHub's [self-hosted runner guidance](https://docs.github.com/en/actions/reference/security/secure-use#hardening-for-self-hosted-runners)
   describes this boundary. If workflow/ref restrictions are unavailable, enforce
   equivalent deployment isolation before granting contributor workflows access.
   Preview containers still execute contributor images; use a dedicated preview
   host. Fork PRs do not publish/deploy automatically.
5. Configure a separate self-hosted Linux x64 CI runner with labels
   `self-hosted,linux,x64,people-gator-ci`, Docker Engine/CLI, Node.js 24,
   Python 3.14 and `uv`. Keep its account, Docker daemon and persistent storage
   isolated from the deployment runner. PR CI executes repository code, including
   fork code when enabled. Use ephemeral CI hosts or disable untrusted fork runs;
   the CI account must not access the deployment release cache, state or daemon.
6. Merge workflows and controller changes onto reviewed `main`. Allow the workflow
   token to publish GHCR packages. For existing private packages, grant this
   repository Actions access to `peoplegatorapp-frontend` and
   `peoplegatorapp-backend`. Builds and deployment use `GITHUB_TOKEN`, with no
   SSH deployment key or PostgreSQL secret stored in GitHub. Make frontend/backend
   PR CI jobs required in branch protection as appropriate.

## Automatic controller releases

Every deployment, close, scheduled or manual lifecycle job checks out
`deploy/preview` at its exact `github.workflow_sha`, then runs `release.py`.
The job accepts only the `main` lifecycle workflow ref. The publisher independently
checks workflow/ref/event identity, the workflow SHA and checkout HEAD; manual
publication checks reviewed `origin/main` ancestry. A manual dispatch on another
branch/tag is skipped. `github.workflow_sha` alone is not a trust guarantee:
[GitHub allows dispatch against other refs](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_dispatch).
Runner access restrictions and reviewed branch changes remain essential.

The publisher reads committed versions of `preview.py`, both Compose templates,
`otel-collector.yaml` and `pgadmin-servers.json`. It compiles Python, parses the
pgAdmin JSON and renders both Compose files with synthetic environment values,
checking required lifecycle services including `seed`. It writes a SHA-256
manifest and publishes a complete directory using an atomic rename under a
publication lock. Compose validation never logs rendered configuration or starts
services; collector semantic validation remains part of explicit `init`.

Releases live at
`/var/lib/people-gator-preview-controller/releases/<commit-sha>/`. The directory
must already belong to the runner with mode `700`. An existing release is checked
against committed bytes and revalidated, then reused without rewriting it.
Incomplete, modified or symlinked bundles fail before any preview mutation;
there is no fallback to stale installed code. Interrupted staging cannot replace
an existing release, and a retry can publish the missing bundle. Failed attempts
clean up their own staging directories; a process killed without cleanup may
leave an unused `.staging-*` directory.

The job executes that release's `preview.py` with
`PREVIEW_CONFIG=/opt/people-gator-preview/config.json`. It verifies repository
access even during empty reconciliation, then performs lifecycle work under the
existing host lock. Configuration, users, infrastructure passwords, PR state,
media and databases are never copied into releases or reset by publication.
Application order remains storage initialization → migration → seed → startup;
a failed seed blocks candidate startup. `seeded_version` is recorded only after
seeding and health checks succeed. Older successful runs cannot replace a newer
application deployment, and repeat runs preserve passwords and data.

There is no mutable `current` release pointer. An older workflow rerun selects
its own reviewed release without replacing a newer bundle; workflows predating
this rollout still execute their original installation logic, so use a fresh run.
Releases are retained for compatible recovery. Do not remove a release used by a
running job or an infrastructure bind mount. The collector/pgAdmin mount paths
are resolved relative to their release; retain older bundles and any legacy
`/opt` templates while containers still reference them. Automatic publication does
not recreate infrastructure. After review and backups, an operator can explicitly
run `init` from a newer release to upgrade it. Recovery to older controller code
requires checking its state/schema compatibility; it does not roll back databases.

## Migrate an existing preview host

After these changes reach reviewed `main`, perform this **one-time** provisioning:

```sh
sudo install -d -m 755 /var/lib/people-gator-preview-controller
sudo install -d -m 700 -o preview-runner -g preview-runner /var/lib/people-gator-preview-controller/releases
sudoedit /opt/people-gator-preview/config.json
```

Replace the account/group placeholder. Correct only `repository` to
`DCGM/PeopleGatorApp` if needed. Preserve all other configuration, ownership,
`users.json`, `infrastructure.env`, PR directories, credentials, media, databases
and Docker volumes. Do not copy example settings or rerun `init` for this migration.
Keep the old `/opt` controller/templates for older workflow reruns and existing
infrastructure mounts; new workflows use published releases instead.

Configure the deployment runner restrictions above, then start a **new** manual
`PR preview lifecycle` run on `main`. It should publish/reuse the reviewed release
without sudo and print `GitHub repository access verified: DCGM/PeopleGatorApp`.
Exercise fresh PR CI deployment, repeated deployment, reconciliation with an open
preview, and closure/repeated cleanup. Check retained data/passwords and registry
credential cleanup on success and failure. Subsequent reviewed controller changes
publish automatically; no repeated operator install or runner restart is needed.

## pgAdmin access

Open `https://pgadmin-preview.peoplegator.dev` and sign in with `pgadmin_email`
and the generated `PGADMIN_DEFAULT_PASSWORD` in
`/var/lib/people-gator-preview/infrastructure.env`. Read credentials locally as
the runner/operator; never print this file in Actions output. Changing the initial
email/password in config does not reset an account already stored in the pgAdmin
volume; use pgAdmin's account settings for subsequent changes.

The preconfigured **Preview PostgreSQL** server connects to `preview-postgres:5432`
as `preview_admin`, using `postgres` as its maintenance database. Enter the
separate `POSTGRES_ADMIN_PASSWORD` when connecting. The administrator can browse
all PR databases. For a PR-limited connection, register a server with maintenance
database and username `preview_pr_123`, using that PR's password from its private
state file. pgAdmin retains accounts and server settings in its shared volume.
Its reverse proxy settings trust Traefik's forwarded HTTPS headers and use secure
session cookies, following [pgAdmin's container deployment documentation](https://www.pgadmin.org/docs/pgadmin4/latest/container_deployment.html).

## Preview logging

The [Docker Fluentd driver](https://docs.docker.com/engine/logging/drivers/fluentd/)
forwards logs from the Docker daemon to `127.0.0.1:24224`; the application
containers need no telemetry network or Docker socket. The
[collector's Fluent Forward receiver](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/receiver/fluentforwardreceiver/README.md)
converts those events to OTel logs. Query LGTM with resource attribute
`people-gator.preview.pr = "123"` and service name
`people-gator-preview.frontend`, `.backend`, `.migrate`, or `.storage-init`.
The tested SHA is `vcs.ref.head.revision`; the stream is `log.iostream`.

Docker's asynchronous driver allows startup while the collector is unavailable,
with a bounded in-memory buffer of 8,192 events per container. Docker's local
dual-logging cache retains three 10 MiB files for `docker compose logs`.
The collector persists its outbound queue in `otel-data` and retries OTLP
delivery indefinitely while queue space is available. Long outages, full buffers,
or daemon shutdown can lose logs; this is not an audit log archive. Short-lived
containers can also lose buffered events if the collector is down when they exit.
The collector uses its own default local Docker logger to avoid forwarding loops.
Inspect it with the infrastructure Compose command or LGTM if logs stop arriving.

## Operations and recovery

The Actions deployment job prints the preview URL and tested commit in its job
summary. Failed tests or builds leave an existing preview running. Failed
migrations preserve the previous Compose environment and saved credentials so a
corrected build can retry. A migration can still change the persistent PR schema;
there is no automatic schema rollback. A failed container health check fails the
deployment job; use the saved candidate environment to inspect that attempt.

For manual lifecycle commands, publish from an updated reviewed `main` checkout
as the runner account, then use that exact release. Supply a GitHub token through
your secret manager with repository metadata, Actions and pull-request read access;
log Docker into GHCR with package read access before deploying private images:

```sh
export GH_TOKEN=... # use your secret manager, not a committed file
export GITHUB_REPOSITORY=DCGM/PeopleGatorApp
export PREVIEW_CONFIG=/opt/people-gator-preview/config.json
controller_revision="$(git rev-parse HEAD)"
python3 deploy/preview/release.py --revision "$controller_revision"
controller="/var/lib/people-gator-preview-controller/releases/$controller_revision/preview.py"
python3 "$controller" check-access
python3 "$controller" deploy --run-id 123456789
python3 "$controller" cleanup --pr 123
python3 "$controller" reconcile
```

For explicit recovery, select a retained, reviewed compatible commit SHA in
`controller_revision` and use that bundle. Do not change a global pointer or
remove other releases. No automatic garbage collection deletes mounted bundles.
Unused staging directories can be removed by the runner only when no publisher
is active; inspect running infrastructure mounts before retiring any release.

`cleanup` checks that the PR is closed; it never removes an open preview. Run the
`PR preview lifecycle` workflow manually to reconcile after host downtime. Rerun
the successful CI workflow to retry deployment. A new run attempt publishes new
tags. Cleanup keeps the shared database service and its persistent volume running.

Inspect an active preview from the host, setting `controller_revision` to the
release SHA shown in that deployment job's publication log:

```sh
docker compose --project-name people-gator-pr-123 \
  --env-file /var/lib/people-gator-preview/pr-123/compose.env \
  -f "/var/lib/people-gator-preview-controller/releases/$controller_revision/compose.pr.yaml" ps
docker compose --project-name people-gator-pr-123 \
  --env-file /var/lib/people-gator-preview/pr-123/compose.env \
  -f "/var/lib/people-gator-preview-controller/releases/$controller_revision/compose.pr.yaml" logs --tail 100 backend
```

Use `candidate.env` if a deployment failed before becoming healthy. Avoid printing
rendered Compose configuration into public logs because it includes DB passwords.
Cleanup removes PR containers, networks, media volumes, DBs, roles and private
state. It leaves cached Docker images and GHCR packages available for debugging;
configure GHCR retention and periodically remove unused host images as needed.

## Repository access failures and existing-host remediation

The old example used `DCGM/people_gator`. On October 15, 2026, the installed
`/opt/people-gator-preview/config.json` still contained that value while Actions
ran in `DCGM/PeopleGatorApp`. Deployment's first API request was consequently
`GET /repos/DCGM/people_gator/actions/runs/38706609562`; cleanup of PR #3 would
request `GET /repos/DCGM/people_gator/pulls/3`. The former returns 404 with the
current operator CLI credential, whereas the same run under
`/repos/DCGM/PeopleGatorApp/` is accessible and successful. The historical job
token is no longer available; verification with a fresh job token remains part
of the rollout below. The inspected host had no `pr-*` state, explaining why
earlier reconciliation could succeed without exercising any API endpoint.

The controller derives API URLs, same-repository validation and GHCR image names
from this setting. A repository-scoped workflow token cannot fix a wrong target.
GitHub can return [404 for a private resource without access](https://docs.github.com/en/rest/using-the-rest-api/troubleshooting-the-rest-api#404-not-found-for-an-existing-resource).
Keep the workflow's `GITHUB_TOKEN` with the existing contents, Actions,
pull-request and package read permissions. A successful Docker login alone does
not verify repository API access or permission to pull a particular package.

Apply the one-time [existing-host migration](#migrate-an-existing-preview-host),
including the repository correction, then use a fresh default-branch lifecycle
run to verify with its real job token. Metadata access alone does not establish
Actions, PR or package access: exercise a successful PR CI deployment and confirm
both pulls target `ghcr.io/dcgm/peoplegatorapp-{frontend,backend}:run-<id>-<attempt>`.
If a private image is inaccessible, verify `DCGM/PeopleGatorApp` has Actions read
access in **each package's** settings using [GitHub's registry authentication guide](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry#authenticating-in-a-github-actions-workflow)
before changing credentials. Preserve the runner's rootless Docker context/socket;
registry credentials remain temporary and their cleanup step runs on failure too.

API failures now report the GET endpoint, status and sanitized GitHub request ID;
response bodies, token values and raw exception reasons are omitted. Use the
endpoint to distinguish repository metadata, Actions run/workflow and PR access.
For 401 check token validity; for 403 check permissions and rate limits; for 404
check the repository identity and resource access/existence. None establishes
that a PR is closed. These responses fail immediately and preserve preview state;
network failures and HTTP 500/502/503/504 receive at most three attempts with
one- and two-second waits. Rate-limit responses are not automatically retried;
observe GitHub's retry/reset headers before starting another run.

## Validation

After changing CI, trigger a new PR run with the updated workflow. Re-running
an older run keeps its original commit and workflow; it does not pick up changes
pushed to `main`. Update the PR branch from `main` when it needs the new workflow.
See [GitHub's rerun documentation](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs).

```sh
python3 deploy/preview/tests/test_preview.py -v
python3 deploy/preview/tests/test_installation.py -v
python3 deploy/preview/tests/test_observability.py -v
```

The optional end-to-end log test starts a private network, collector, OTLP sink,
and four short-lived containers, then removes them. It checks real stdout/stderr
delivery and PR/service/commit metadata without contacting the shared database or
LGTM. Pull `python:3.12` and `otel/opentelemetry-collector-contrib:0.162.0`, then run:

```sh
PREVIEW_TEST_OTEL=1 python3 deploy/preview/tests/test_observability.py -v
```

Database isolation tests run when `PREVIEW_TEST_POSTGRES_CONTAINER` names a
disposable pgvector container with local `ci` administrator access. They create
and drop `preview_pr_900001` and `preview_pr_900002`, test real TCP denial between PR roles,
extension provisioning, repeatable provisioning and repeatable cleanup. CI uses
its existing service container for these checks.
