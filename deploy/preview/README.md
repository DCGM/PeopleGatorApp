# Pull request previews

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

The preview host runs an installed controller through a self-hosted Actions
runner. A successful `PR CI` run triggers deployment at
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
media; see [preview seeding](../../people-gator-api/docs/preview-seeding.md).
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
2. Install these files from a reviewed default-branch checkout, replacing
   `preview-runner` with the account running the self-hosted runner:

   ```sh
   sudo install -d -m 755 /opt/people-gator-preview
   sudo install -m 644 deploy/preview/preview.py deploy/preview/compose.*.yaml /opt/people-gator-preview/
   sudo install -m 644 deploy/preview/otel-collector.yaml deploy/preview/pgadmin-servers.json /opt/people-gator-preview/
   sudo install -m 644 deploy/preview/config.example.json /opt/people-gator-preview/config.json
   sudo install -m 644 people-gator-api/example.users.json /opt/people-gator-preview/users.json
   sudo install -d -m 700 -o preview-runner -g preview-runner /var/lib/people-gator-preview
   ```

   Edit `/opt/people-gator-preview/config.json` for the repository and network
   names on your host. Set `otel_http_endpoint` to the OTLP HTTP base URL
   (default `http://lgtm:4318`, without `/v1/logs`), `otel_network` to its existing
   Docker network (default `logging`), and `pgadmin_email` to the administrator's
   login email (default `admin@peoplegator.dev`). `preview_log_port` defaults to
   `24224`; change it if another host collector already uses that port.
   Config/controller/Compose files should be owned by the
   operator; state belongs to the runner. The supplied users file provides the
   frontend's current `test` / `test` demo login. Preview databases start with
   synthetic seed examples; no production data is copied. The frontend currently automatically logs into
   this demo account, so the public preview is writable demo data.
3. As the runner account, initialize the shared infrastructure:

   ```sh
   python3 /opt/people-gator-preview/preview.py init
   ```

   Initialization generates PostgreSQL and pgAdmin passwords in the private
   state directory, validates the collector configuration, and starts PostgreSQL,
   the collector and pgAdmin. PostgreSQL and pgAdmin have no published host ports;
   only the collector's Fluent Forward receiver is published on host loopback.
   Running `init` again upgrades older infrastructure and preserves both passwords
   and all volumes. Back up `people-gator-preview-infra_postgres-data`,
   `people-gator-preview-infra_pgadmin-data`, and the state directory together.
4. Register a self-hosted GitHub Actions runner with labels
   `self-hosted,linux,x64,people-gator-preview`. Allow it to run only this
   repository's trusted `pr-preview.yml` workflow via a restricted organization
   runner group, where available. The runner needs access to the Docker daemon
   and state directory. Preview images execute contributor code; use a dedicated
   preview host for this repository's trusted contributors. Fork PRs run CI
   tests but do not publish or deploy automatically. GitHub documents the trust
   boundaries of these triggers in its
   [secure use guidance](https://docs.github.com/en/actions/reference/security/secure-use).
5. Configure a separate self-hosted Linux x64 CI runner with labels
   `self-hosted,linux,x64,people-gator-ci`. It needs Docker Engine/CLI for the
   PostgreSQL service container, controller integration tests, and image builds,
   plus Node.js 24, Python 3.14, and `uv`. Keep this runner and its Docker daemon
   separate from the preview deployment runner and your personal account: PR
   workflows execute repository code on it, including code from forks. For a
   public repository, use disposable/ephemeral CI machines or disable running
   fork PR code on the self-hosted runner. Restrict its runner group to this
   repository and the `pr-ci.yml` workflow where organization runner groups are
   available. Do not grant it access to the preview host's state or Docker daemon.
6. Merge both workflows onto the repository's default branch. `workflow_run`
   needs its receiving workflow there, and scheduled reconciliation also runs
   there. Include the Alembic revision files in the committed checkout: the
   production migration and validation commands require them. Enable Actions
   and allow the workflow token to publish GHCR packages.
   For existing private packages, grant this repository Actions access to both
   `people_gator-frontend` and `people_gator-backend`. Builds use `GITHUB_TOKEN`;
   no SSH deployment key or PostgreSQL secret is stored in GitHub. Make the
   `frontend` and `backend` PR CI jobs required in branch protection if desired.

The deployer always runs `/opt/people-gator-preview/preview.py`; updating its
trusted installed copy, Compose templates, collector config and pgAdmin server
definition is an explicit operator action.
PR changes to these files cannot change the host controller. Controller updates
should be installed when corresponding workflow changes reach the default branch.

To upgrade an existing host, install the new controller, Compose files,
`otel-collector.yaml` and `pgadmin-servers.json`, add the configuration fields
above to the existing `config.json`, and rerun `init`. Keep the existing config
and state files. New preview deployments receive logging automatically; existing
containers pick up the new logging driver when recreated by the next successful
PR CI run. Reconciliation only handles cleanup and does not recreate open previews.

For the seeding rollout, install both the updated `preview.py` and `compose.pr.yaml`
from a reviewed default-branch checkout. Deploy backend images that include the
`seed` entrypoint command; older images without that command will fail the seed
step rather than starting an empty preview. The fixture code itself ships inside
each candidate backend image and needs no separate host installation. PR CI also
smoke-tests migrations and two seed runs in a dedicated `ci_seed` database, apart
from contract and schema tests.

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

For manual lifecycle commands, provide a GitHub token with repository metadata,
Actions and pull-request read access; log Docker into GHCR with package read
access before deploying private images:

```sh
export GH_TOKEN=... # use your secret manager, not a committed file
python3 /opt/people-gator-preview/preview.py deploy --run-id 123456789
python3 /opt/people-gator-preview/preview.py cleanup --pr 123
python3 /opt/people-gator-preview/preview.py reconcile
```

`cleanup` checks that the PR is closed; it never removes an open preview. Run the
`PR preview lifecycle` workflow manually to reconcile after host downtime. Rerun
the successful CI workflow to retry deployment. A new run attempt publishes new
tags. Cleanup keeps the shared database service and its persistent volume running.

Inspect an active preview from the host:

```sh
docker compose --project-name people-gator-pr-123 \
  --env-file /var/lib/people-gator-preview/pr-123/compose.env \
  -f /opt/people-gator-preview/compose.pr.yaml ps
docker compose --project-name people-gator-pr-123 \
  --env-file /var/lib/people-gator-preview/pr-123/compose.env \
  -f /opt/people-gator-preview/compose.pr.yaml logs --tail 100 backend
```

Use `candidate.env` if a deployment failed before becoming healthy. Avoid printing
rendered Compose configuration into public logs because it includes DB passwords.
Cleanup removes PR containers, networks, media volumes, DBs, roles and private
state. It leaves cached Docker images and GHCR packages available for debugging;
configure GHCR retention and periodically remove unused host images as needed.

## Validation

After changing CI, trigger a new PR run with the updated workflow. Re-running
an older run keeps its original commit and workflow; it does not pick up changes
pushed to `main`. Update the PR branch from `main` when it needs the new workflow.
See [GitHub's rerun documentation](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs).

```sh
python3 deploy/preview/tests/test_preview.py -v
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
