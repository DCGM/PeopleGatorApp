# Deployment setup

Each environment is configured by a short list of repository **variables**
(Settings → Secrets and variables → Actions → Variables) and **secrets**
(same page, Secrets), prefixed `PREVIEW_`, `STAGING_` or `PRODUCTION_`. Everything
not listed here is a fixed convention (table at the end).

| Name (after the prefix) | Kind | Preview | Staging | Production | Meaning |
| --- | --- | --- | --- | --- | --- |
| `HOST` | variable | required | required | required | Hostname; previews run at `https://pr-<N>.<HOST>` |
| `DATABASE_URL` | secret | required | required | required | `postgresql://user:password@host:5432/db`; the shared server's admin URL for previews/staging (each gets its own databases), the application role for production |
| `MIGRATION_DATABASE_URL` | secret | | | optional | A separate migration role; defaults to `DATABASE_URL` |
| `STORAGE_DIR` | variable | optional | | | Media directory inside the container on a Docker volume (default `/data`) |
| `S3_BUCKET`, `S3_REGION` | variable | optional | required | required | S3 media storage (previews use the volume unless set) |
| `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` | secret | with `S3_*` | required | required | |
| `S3_ENDPOINT_URL` | variable | optional | optional | optional | For non-AWS S3 |
| `BACKUP_S3_BUCKET`, `BACKUP_S3_PREFIX`, `BACKUP_S3_REGION`, `BACKUP_S3_ENDPOINT_URL` | variable | | optional | | Read-only bucket of production dumps for `snapshot-init` / `refresh` |
| `BACKUP_S3_ACCESS_KEY_ID`, `BACKUP_S3_SECRET_ACCESS_KEY` | secret | | with `BACKUP_S3_*` | | |
| `OTEL_ENDPOINT` | variable | optional | optional | optional | OTLP HTTP collector on the `logging` network, for example `http://lgtm:4318`; the backend sends logs, traces and metrics there |
| `OTEL_HEADERS` | secret | optional | optional | optional | `Authorization=Basic …` if the collector needs it |
| `RUM_CLIENT_TOKEN` | secret | optional | optional | optional | Enables browser RUM |
| `RUM_SITE` | variable | optional | optional | optional | RUM site, default `openobserve.capturemyhand.com` |
| `USERS_JSON` | secret | optional | | | Preview login accounts in the format of `people-gator-api/example.users.json`; that file is the default |

Omitting `OTEL_*` or `RUM_*` leaves that feature off. For example:

```sh
gh variable set PREVIEW_HOST --body preview.peoplegator.dev
gh secret set PREVIEW_DATABASE_URL --body 'postgresql://preview_admin:SECRET@people-gator-postgres:5432/postgres'
gh variable set PREVIEW_OTEL_ENDPOINT --body http://lgtm:4318
gh secret set PREVIEW_RUM_CLIENT_TOKEN --body RUM_TOKEN

gh variable set STAGING_HOST --body staging.peoplegator.dev
gh secret set STAGING_DATABASE_URL --body 'postgresql://preview_admin:SECRET@people-gator-postgres:5432/postgres'
gh variable set STAGING_S3_BUCKET --body peoplegator-staging
gh variable set STAGING_S3_REGION --body us-east-1
gh variable set STAGING_S3_ENDPOINT_URL --body https://s3.example.org
gh secret set STAGING_S3_ACCESS_KEY_ID --body KEY
gh secret set STAGING_S3_SECRET_ACCESS_KEY --body SECRET
gh variable set STAGING_BACKUP_S3_BUCKET --body peoplegator-db-backup
gh variable set STAGING_BACKUP_S3_PREFIX --body production/db-backups/
gh variable set STAGING_BACKUP_S3_REGION --body us-east-1
gh variable set STAGING_BACKUP_S3_ENDPOINT_URL --body https://s3.example.org
gh secret set STAGING_BACKUP_S3_ACCESS_KEY_ID --body READ_ONLY_KEY
gh secret set STAGING_BACKUP_S3_SECRET_ACCESS_KEY --body READ_ONLY_SECRET
gh variable set STAGING_OTEL_ENDPOINT --body http://lgtm:4318

gh variable set PRODUCTION_HOST --body people.example.org
gh secret set PRODUCTION_DATABASE_URL --body 'postgresql://people_gator:SECRET@people-gator-postgres:5432/people_gator'
gh variable set PRODUCTION_S3_BUCKET --body peoplegator
gh variable set PRODUCTION_S3_REGION --body us-east-1
gh secret set PRODUCTION_S3_ACCESS_KEY_ID --body KEY
gh secret set PRODUCTION_S3_SECRET_ACCESS_KEY --body SECRET
gh variable set PRODUCTION_OTEL_ENDPOINT --body http://lgtm:4318
gh secret set PRODUCTION_OTEL_HEADERS --body 'Authorization=Basic BASE64'
```

## Hosts

- **Shared PostgreSQL and pgAdmin** on the preview/staging host, once:
  `docker compose -f deploy/infrastructure/compose.yaml --env-file /private/infrastructure.env up -d --wait --remove-orphans`
  with a copy of [`deploy/infrastructure/example.env`](infrastructure/example.env)
  (keep that file: it holds the PostgreSQL and pgAdmin passwords, the pgAdmin
  login and host). Any PostgreSQL 16 with pgvector works instead, attached to
  the `db` network (`docker network connect db <container>`),
  including the production database. Hosts upgraded from earlier releases reuse
  their existing env file; previews and staging deployed before the upgrade keep
  working if the recreated server is also attached to their old network:
  `docker network connect --alias preview-postgres people-gator-preview-db people-gator-postgres`
  (drop it once they have been redeployed or closed).
- **Traefik** on the `web` network with the `websecure` entrypoint and its own
  certificates (the stacks only enable TLS on their routers), and DNS for
  `*.<preview host>`, the staging host, the production host and pgAdmin pointing
  at it.
- **OTLP collector** on the `logging` network, only when `OTEL_ENDPOINT` is set.
- **Runners**: one self-hosted runner per host as the deployment account,
  labelled `people-gator-preview`, `people-gator-staging` and/or
  `people-gator-release`, with `docker context use rootless` done once and the
  [job-started guard](runner/job-started.sh) in its `.env`
  (`PEOPLE_GATOR_RUNNER_ENVIRONMENT=preview,staging`). Settings → Actions →
  General: require approval for all outside collaborators.

Then open a pull request or run **CI** manually on `main` (`operation=update`,
or `snapshot-init` for a fresh staging database). A deploy job's `preflight`
step fails with the variable's name when something is missing or invalid; each
success appears under the repository's Deployments.

## Conventions

| Fixed by the deployment | Value |
| --- | --- |
| Docker daemon | the runner account's current context |
| Networks | `web` (Traefik), `db` (PostgreSQL), `logging` (collector, only with `OTEL_ENDPOINT`) |
| Compose projects | `people-gator-pr-<N>`, `people-gator-staging`, `people-gator-release` |
| State and generated files | `~/.local/opt/people-gator-deploy/state/<pr\|staging\|release>` on the host |
| TLS | routers enable TLS; Traefik supplies the certificates |
| Login tokens and CORS | issuer `https://<HOST>`, audience `<HOST>` |
| Images | `ghcr.io/<repo>-frontend` and `-backend`, tag `sha-<commit>` |
