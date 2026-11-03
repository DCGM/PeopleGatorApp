# Host prerequisites

External services the utility checks but never creates. Prepare them before
`people-gator-deploy <env> install`. Commands are covered in the
[utility guide](README.md); descriptor shapes are in [`examples/`](examples/).

## Docker, proxy and networks

- Linux x86-64 (images are built for `linux/amd64`), Docker Engine with Compose
  v2.32+, Python 3.11+ with `venv`. For rootless Docker, run the runner service,
  the utility and Traefik as the same account and socket, and set the
  descriptor's `docker_context` (for example `rootless`). The utility names that
  context on every call; it never changes the host's active context.
- An existing Traefik instance on the `web_network` with entrypoint `websecure` and
  resolver `tlschallenge` (`certificate_resolver: ""` reuses an existing wildcard
  certificate). Wildcard issuance requires DNS-01.
- An OTLP HTTP backend on `otel_network` (default `logging`, endpoint
  `http://lgtm:4318`). The shared collector receives Docker fluentd logs on
  `127.0.0.1:<preview_log_port>` (default 24224).
- DNS: `*.<domain>` (previews), `pgadmin_host`, the staging `host` and the release
  `host` all point to the Traefik host. The preview wildcard does not cover staging.

## GitHub runners and tokens

`pr-ci.yml` runs on GitHub-hosted `ubuntu-24.04` runners, so no PR code runs on
your hosts. Self-hosted runners serve only the lifecycle workflows:

| Runner labels | Workflow | Account needs |
| --- | --- | --- |
| `self-hosted,linux,x64,people-gator-preview` | `pr-preview.yml` | Utility user install, `pr` descriptor |
| `self-hosted,linux,x64,people-gator-staging` | `staging.yml` | Utility user install, `staging` descriptor |
| `self-hosted,linux,x64,people-gator-release` | `release.yml` | Utility user install, `release` descriptor |

Labels only select a runner: in a public repository any workflow in a PR, branch
or tag can request them. Install the job-started guard on every self-hosted
runner. It refuses every job except these workflows from reviewed `main` and
release tags whose commit is on `main`:

```sh
install -D -m 755 deploy/runner/job-started.sh ~/.local/libexec/people-gator/job-started.sh
# In each runner directory; the script itself must live outside it:
echo "ACTIONS_RUNNER_HOOK_JOB_STARTED=$HOME/.local/libexec/people-gator/job-started.sh" >> .env
sudo ./svc.sh stop && sudo ./svc.sh start
```

Copy the script from reviewed `main`, and refresh the copy when it changes.
Refused jobs fail in their `Set up runner` step. Also set **Settings → Actions →
General → Fork pull request workflows** to require approval for all outside
contributors, and protect release tags (`v*`) with a ruleset.

Preview containers still execute contributor images. Run lifecycle runners and
deployments under a dedicated account, not a personal one; see
[Single-host isolation](#single-host-isolation). Fork PRs are tested but never
publish images or deploy.

Deployment jobs use only `GITHUB_TOKEN` (contents, actions, pull-requests and
packages read; CI image publication needs packages write). For private GHCR
packages, grant this repository Actions access to `peoplegatorapp-frontend` and
`peoplegatorapp-backend`. No SSH key or database secret is stored in GitHub.
Protect release tags (`v*`) with a ruleset so only maintainers can create them.

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
4. Register the lifecycle runners as `gator-deploy` with labels
   `people-gator-preview,people-gator-staging,people-gator-release`, install them
   with `sudo ./svc.sh install gator-deploy`, and add the job-started guard.
   Several runners can run different environments at the same time; each
   environment still deploys one job at a time.
5. As `gator-deploy`, install the utility from reviewed `main`, configure the
   descriptors with `docker_context: rootless`, then run `pr install`,
   `staging install` and `staging snapshot-init`. Rerun the latest CI of open PRs
   to redeploy their previews.
6. Remove the old runners (`./config.sh remove`) and uninstall the old
   environments and their containers, volumes and state from your account.

## PR previews

- `users_file`: a users JSON with Argon2 hashes, owned by the deployment account
  or root and not group/world writable (the backend container reads it).
  `people-gator-api/example.users.json` supplies the demo `test` / `test` account
  that the preview frontend logs into.
- `pr install` generates the shared PostgreSQL and pgAdmin passwords into
  `<infrastructure.state_dir>/infrastructure.env` (mode 600) and starts
  PostgreSQL, the collector and pgAdmin. Back up that directory with the
  `<project>_postgres-data` and `<project>_pgadmin-data` volumes before
  `pr infra-upgrade`.
- pgAdmin: `https://<pgadmin_host>`, login `pgadmin_email` with
  `PGADMIN_DEFAULT_PASSWORD`. Its preconfigured server connects to
  `preview-postgres:5432` as `preview_admin` (`POSTGRES_ADMIN_PASSWORD`). A PR-only
  connection uses role/database `preview_pr_<N>` and the password in
  `<state_dir>/pr-<N>/state.json`. Never print these files in Actions.
- Logs reach LGTM with resource attribute `people-gator.preview.pr = "<N>"` and
  service names `people-gator-preview.<service>`; the tested SHA is
  `vcs.ref.head.revision`. Buffers are bounded; this is not an audit archive.

## Staging

Staging shares the preview PostgreSQL (`infrastructure.mode: external`) and has
its own hostname and database state. The utility manages **databases only**;
Application S3 storage, media and authentication objects are operated externally.

The private descriptor ([example](examples/staging.json)) names:

- `runtime_file`: an owned private `PEOPLE_GATOR_API__*` env file for the backend's
  externally managed application settings. Supply storage, media prefixes and
  authentication configuration appropriate for your external environment. Do
  not put persistence settings in this file; staging generates its database
  connection. Routine updates require neither a snapshot nor S3 source inputs.
- `snapshot_source_file`: private read-only production backup S3 source, needed
  only by `snapshot-init`/`refresh`. Provision prefix-scoped list/read/version-read
  access once. Each operation selects the latest valid dated archive, downloads
  privately and checks identity, publisher checksum/revision and archive format
  before restore. See [Backup gathering](README.md#backup-gathering), including
  migration from legacy fixed-local `snapshot` descriptors.

Bucket/account provisioning, application signing keys and media copying remain
external. Only database backup objects are downloaded and verified by refresh. Missing scans/layouts do not fail a database
snapshot. Operators maintain external storage/auth compatibility separately;
staging never rewrites media prefixes or imports production auth objects.
Sign in at `https://<host>/staging-login.html` using externally provisioned
accounts. The page contains no credentials; the demo auto-login only works if
those credentials have explicitly been supplied externally.

## Releases

- An external PostgreSQL reachable on `database_network`, already migrated or new,
  with separate **migration** and **runtime** roles. `migration_file` and
  `runtime_file` (mode 600) contain only `PEOPLE_GATOR_API__*` lines: the migration
  file the migration role's persistence settings; the runtime file the runtime
  role, `PEOPLE_GATOR_API__STORAGE…`, JWK issuer/audience and paths. Deployment
  fixes host/port, debug/reload off, `schema_mode=validate` and CORS.
- Private object storage holding users, API keys and JWKs, preserved across
  releases; back up the database before any release that migrates
  ([backup](../backup/README.md)) and record it in a mode-600 file for
  `--backup-record`.
- The frontend embeds demo auto-login credentials. Put the release behind a
  reviewed access boundary before setting `access_reviewed: true`.
