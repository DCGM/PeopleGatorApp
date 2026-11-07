# Host prerequisites

External services the utility checks but never creates. Prepare them before
`people-gator-deploy <env> install`. Commands and the `DEPLOY_*` settings are
covered in the [utility guide](README.md).

## Docker, proxy and networks

- Linux x86-64 (images are built for `linux/amd64`), Docker Engine with Compose
  v2.32+, Python 3.11+ with `venv`, Git. For rootless Docker, run the runner
  service, the deploy jobs and Traefik as the same account and socket, and set
  `DEPLOY_DOCKER_CONTEXT` (for example `rootless`). The utility names that
  context on every call; it never changes the host's active context.
- An existing Traefik instance on `DEPLOY_WEB_NETWORK` (default `web`) with
  entrypoint `websecure` and resolver `tlschallenge`
  (`DEPLOY_CERTIFICATE_RESOLVER=none` reuses an existing wildcard certificate).
  Wildcard issuance requires DNS-01.
- An OTLP HTTP backend on `DEPLOY_OTEL_NETWORK` (default `logging`, endpoint
  `DEPLOY_OTEL_HTTP_ENDPOINT`, default `http://lgtm:4318`). The shared collector
  receives Docker fluentd logs on `127.0.0.1:<DEPLOY_PREVIEW_LOG_PORT>` (default 24224).
- DNS: `*.<DEPLOY_DOMAIN>` (previews), `DEPLOY_PGADMIN_HOST`, the staging
  `DEPLOY_HOST` and the production `DEPLOY_HOST` all point to the Traefik host.
  The preview wildcard does not cover staging.
- Outbound access from the deploy account to GitHub (API and GHCR) and to the
  Python package index: each deploy job builds the utility into a job-local
  virtual environment.

## GitHub runners and tokens

The `frontend`, `backend` and `images` jobs run on GitHub-hosted `ubuntu-24.04`
runners, so no PR code runs on your hosts except the deploy jobs of
same-repository pull requests. Self-hosted runners serve only the deploy jobs:

| Runner labels | Jobs | `PEOPLE_GATOR_RUNNER_ENVIRONMENT` | GitHub Environment |
| --- | --- | --- | --- |
| `self-hosted,linux,x64,people-gator-preview` | `deploy-preview`, `remove-preview`, `prune-previews` | `preview` | `preview` |
| `self-hosted,linux,x64,people-gator-staging` | `deploy-staging` | `staging` | `staging` |
| `self-hosted,linux,x64,people-gator-release` | `deploy-release` | `release` | `production` |

Labels only select a runner: in a public repository any workflow in a PR, branch
or tag can request them, and a pull request's workflow file is the pull request's
own. Install the job-started guard on every self-hosted runner. It admits only
this repository's events for the runner's environment (same-repository pull
requests and `main` for `preview`, `main` for `staging`, `v*` tags whose commit
is on `main` for `release`) and refuses fork pull requests from the event
payload, whatever the workflow says:

```sh
install -D -m 755 deploy/runner/job-started.sh ~/.local/libexec/people-gator/job-started.sh
# In each runner directory; the script itself must live outside it:
echo "ACTIONS_RUNNER_HOOK_JOB_STARTED=$HOME/.local/libexec/people-gator/job-started.sh" >> .env
echo "PEOPLE_GATOR_RUNNER_ENVIRONMENT=preview" >> .env   # or staging / release
```

Restart each runner service while idle so it reads `.env`, for example
`sudo ./svc.sh stop && sudo ./svc.sh start`, or
`systemctl --user restart github-runner@<runner>` for a user unit. A runner that
carries several labels must still name one environment; register one runner per
environment. Copy the script from reviewed `main`, and refresh the copy when it
changes. Refused jobs fail in their `Set up runner` step.

Also set **Settings → Actions → General → Fork pull request workflows** to
require approval for all outside contributors, protect release tags (`v*`) with a
ruleset so only maintainers can create them, and restrict the `staging` and
`production` GitHub Environments to `main` and `v*` tags respectively (an
environment's secrets are only available to jobs whose ref passes its policy).

Deploy jobs use only `GITHUB_TOKEN` (contents, pull-requests and packages read,
deployments write; the `images` job needs packages write). For private GHCR
packages, grant this repository Actions access to `peoplegatorapp-frontend` and
`peoplegatorapp-backend`. No SSH key or database secret is stored in GitHub
outside the Environments' secrets.

Preview containers execute contributor images and same-repository branches run
their own deploy code on the preview host. Run runners and deployments under a
dedicated account, not a personal one; see
[Single-host isolation](#single-host-isolation).

## Single-host isolation

When CI, previews and staging share one machine, give deployments their own
account and Docker daemon. Your personal account then holds no deployment
secrets, and deployment jobs cannot reach your files or containers.

1. As an administrator, once:

   ```sh
   sudo useradd --create-home --shell /bin/bash gator-deploy
   sudo usermod --add-subuids 231072-296607 --add-subgids 231072-296607 gator-deploy
   sudo loginctl enable-linger gator-deploy
   sudo sysctl -w net.ipv4.ip_unprivileged_port_start=80  # persist in /etc/sysctl.d
   ```

   Never add `gator-deploy` to the `docker` group; that grants root.
2. In a login session for the account (`sudo machinectl shell gator-deploy@`),
   run `dockerd-rootless-setuptool.sh install` and use context `rootless`.
3. Move the public Traefik (and its tunnel sidecar) and the OTLP backend to this
   daemon. Containers on one daemon cannot join another daemon's networks. Keep
   development proxies on your own daemon and ports.
4. Register one runner per environment as `gator-deploy` with its label
   (`people-gator-preview`, `people-gator-staging`, `people-gator-release`),
   install them with `sudo ./svc.sh install gator-deploy`, and add the
   job-started guard with the matching `PEOPLE_GATOR_RUNNER_ENVIRONMENT`.
   Several runners can run different environments at the same time; each
   environment still deploys one job at a time.
5. As `gator-deploy`, export the GitHub Environments' `DEPLOY_*` values with
   `DEPLOY_DOCKER_CONTEXT=rootless`, then run `pr install`, `staging install`
   and `staging snapshot-init` from a checkout of `main`
   ([one-time setup](README.md#one-time-host-setup)). Rerun the latest CI of open
   PRs to redeploy their previews.
6. Remove the old runners (`./config.sh remove`) and uninstall the old
   environments and their containers, volumes and state from your account.

## PR previews

- `DEPLOY_USERS_JSON`: a users JSON with Argon2 hashes, written by each job to
  `<DEPLOY_STATE_DIR>/users.json` (mode 644) for the backend container's bind
  mount. `people-gator-api/example.users.json` supplies the demo `test` / `test`
  account that the preview frontend logs into.
- `pr install` generates the shared PostgreSQL and pgAdmin passwords into
  `<DEPLOY_INFRASTRUCTURE_STATE_DIR>/infrastructure.env` (mode 600) and starts
  PostgreSQL, the collector and pgAdmin. Back up that directory with the
  `<project>_postgres-data` and `<project>_pgadmin-data` volumes before
  `pr infra-upgrade`.
- pgAdmin: `https://<DEPLOY_PGADMIN_HOST>`, login `DEPLOY_PGADMIN_EMAIL` with
  `PGADMIN_DEFAULT_PASSWORD`. Its preconfigured server connects to
  `preview-postgres:5432` as `preview_admin` (`POSTGRES_ADMIN_PASSWORD`). A PR-only
  connection uses role/database `preview_pr_<N>` and the password in
  `<DEPLOY_STATE_DIR>/pr-<N>/state.json`. Never print these files in Actions.
- Logs reach LGTM with resource attribute `people-gator.preview.pr = "<N>"` and
  service names `people-gator-preview.<service>`; the tested SHA is
  `vcs.ref.head.revision`. Buffers are bounded; this is not an audit archive.

## Staging

Staging shares the preview PostgreSQL (the same `DEPLOY_INFRASTRUCTURE_STATE_DIR`,
`DEPLOY_INFRASTRUCTURE_PROJECT` and `DEPLOY_DATABASE_NETWORK` as `preview`) and
has its own hostname and state directory. The utility manages **databases only**;
application S3 storage, media and authentication objects are operated externally.

The `staging` GitHub Environment supplies:

- `DEPLOY_RUNTIME_ENV`: `PEOPLE_GATOR_API__*` lines for the backend's externally
  managed application settings. Supply storage, media prefixes and
  authentication configuration appropriate for your external environment. Do
  not put persistence settings in it; staging generates its database
  connection. Routine updates require neither a snapshot nor S3 source inputs.
- `DEPLOY_SNAPSHOT_SOURCE`: the private read-only production backup S3 source,
  needed only by `snapshot-init`/`refresh`. Provision prefix-scoped
  list/read/version-read access once. Each operation selects the latest valid
  dated archive, downloads privately and checks identity, publisher
  checksum/revision and archive format before restore. See
  [Backup gathering](README.md#backup-gathering).

Bucket/account provisioning, application signing keys and media copying remain
external. Only database backup objects are downloaded and verified by refresh.
Missing scans/layouts do not fail a database snapshot. Operators maintain
external storage/auth compatibility separately; staging never rewrites media
prefixes or imports production auth objects. Sign in at
`https://<host>/staging-login.html` using externally provisioned accounts. The
page contains no credentials; the demo auto-login only works if those
credentials have explicitly been supplied externally.

## Releases

- An external PostgreSQL reachable on `DEPLOY_DATABASE_NETWORK`, already migrated
  or new, with separate **migration** and **runtime** roles. `DEPLOY_MIGRATION_ENV`
  and `DEPLOY_RUNTIME_ENV` contain only `PEOPLE_GATOR_API__*` lines: the migration
  secret the migration role's persistence settings; the runtime secret the
  runtime role, `PEOPLE_GATOR_API__STORAGE…`, JWK issuer/audience and paths.
  Deployment fixes host/port, debug/reload off, `schema_mode=validate` and CORS.
- Private object storage holding users, API keys and JWKs, preserved across
  releases; back up the database before any release that migrates
  ([backup](../backup/README.md)) and record it in a mode-600 host file for the
  workflow's `backup_record` input.
- The frontend embeds demo auto-login credentials. Put the release behind a
  reviewed access boundary before setting `DEPLOY_ACCESS_REVIEWED=true`.
