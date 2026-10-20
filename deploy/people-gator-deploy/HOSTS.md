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

| Runner labels | Workflow | Account needs |
| --- | --- | --- |
| `self-hosted,linux,x64,people-gator-ci` | `pr-ci.yml` | Docker, Node.js 24, Python 3.14, `uv`; isolated from deployment accounts |
| `self-hosted,linux,x64,people-gator-preview` | `pr-preview.yml` | Utility user install, `pr` descriptor |
| `self-hosted,linux,x64,people-gator-staging` | `staging.yml` | Utility user install, `staging` descriptor |
| `self-hosted,linux,x64,people-gator-release` | `release.yml` | Utility user install, `release` descriptor |

Labels only select a runner. Protect and review `main`, and restrict deployment
runner groups to the repository's deployment workflows where supported; never let
PR CI or other untrusted workflows run on a deployment account. Preview containers
still execute contributor images: use a dedicated preview host. Fork PRs are
tested but never publish images or deploy.

Deployment jobs use only `GITHUB_TOKEN` (contents, actions, pull-requests and
packages read; CI image publication needs packages write). For private GHCR
packages, grant this repository Actions access to `peoplegatorapp-frontend` and
`peoplegatorapp-backend`. No SSH key or database secret is stored in GitHub.
Protect release tags (`v*`) with a ruleset so only maintainers can create them.

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
S3, media and authentication objects are operated externally.

The private descriptor ([example](examples/staging.json)) names:

- `runtime_file`: an owned private `PEOPLE_GATOR_API__*` env file for the backend's
  externally managed application settings. Supply storage, media prefixes and
  authentication configuration appropriate for your external environment. Do
  not put persistence settings in this file; staging generates its database
  connection. Routine updates require neither a snapshot nor S3 source inputs.
- `snapshot`: needed only by `snapshot-init`/`refresh`. Provide a private, local
  PostgreSQL 16 `pg_dump -Fc` archive, its expected `sha256` and the source
  `application_revision`. Obtain/download backups externally before running the
  utility. The pinned archive is read without copying or deleting it; checksums,
  archive validation and candidate database checks gate activation.

No bucket, account, signing-key, media-copy or S3-object validation is part of
staging installation or refresh. Missing scans/layouts do not fail a database
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
