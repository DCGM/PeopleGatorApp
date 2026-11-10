# Deployment setup

Three repository secrets configure the whole pipeline (Settings → Secrets and
variables → Actions → New repository secret), one JSON document per
environment. Everything not listed here is a fixed convention (table at the
end).

## `PREVIEW_CONFIG`

```json
{
  "host": "preview.peoplegator.dev",
  "database": "postgresql://preview_admin:SECRET@people-gator-postgres:5432/postgres",
  "otel": {"endpoint": "http://lgtm:4318"},
  "rum": {"client_token": "RUM_TOKEN", "site": "openobserve.capturemyhand.com"}
}
```

Previews run at `https://pr-<N>.<host>`, each with its own database created
through the admin `database` URL and media on a local volume. Logins use the
repository's demo users (`people-gator-api/example.users.json`); add a
`"users": {...}` object in the same format to change them.

## `STAGING_CONFIG`

```json
{
  "host": "staging.peoplegator.dev",
  "database": "postgresql://preview_admin:SECRET@people-gator-postgres:5432/postgres",
  "storage": {"s3": {"endpoint_url": "https://s3.example.org", "region": "us-east-1",
              "bucket_name": "peoplegator-staging", "access_key_id": "KEY", "secret_access_key": "SECRET"}},
  "backup_source": {"endpoint_url": "https://s3.example.org", "region": "us-east-1",
                    "bucket": "peoplegator-db-backup", "prefix": "production/db-backups/",
                    "access_key_id": "READ_ONLY_KEY", "secret_access_key": "READ_ONLY_SECRET"},
  "otel": {"endpoint": "http://lgtm:4318"},
  "rum": {"client_token": "RUM_TOKEN", "site": "openobserve.capturemyhand.com"}
}
```

Staging shares the preview PostgreSQL and keeps its own database generation;
`backup_source` is the read-only bucket of production dumps used by the manual
`snapshot-init` / `refresh` runs. Users and keys live in the S3 bucket.

## `PRODUCTION_CONFIG`

```json
{
  "host": "people.example.org",
  "database": "postgresql://people_gator:SECRET@people-gator-postgres:5432/people_gator",
  "storage": {"s3": {"endpoint_url": "https://s3.example.org", "region": "us-east-1",
              "bucket_name": "peoplegator", "access_key_id": "KEY", "secret_access_key": "SECRET"}},
  "otel": {"endpoint": "http://lgtm:4318", "headers": "Authorization=Basic BASE64"},
  "rum": {"client_token": "RUM_TOKEN", "site": "openobserve.capturemyhand.com"}
}
```

Production uses the `database` URL as the application role; add
`"migration_database": "postgresql://migrator:SECRET@…"` to migrate with a
separate role. Use `{"local": {"root": "/data"}}` as `storage` to keep media on a
Docker volume instead of S3. Omit `otel` or `rum` to leave that feature off; add
`"extra_env": {"PEOPLE_GATOR_API__OPENROUTER__API_KEY": "…"}` for any other
API setting.

```sh
gh secret set PREVIEW_CONFIG < preview.json
gh secret set STAGING_CONFIG < staging.json
gh secret set PRODUCTION_CONFIG < production.json
```

## Hosts

- **Shared PostgreSQL and pgAdmin** on the preview/staging host, once:
  `docker compose -f deploy/infrastructure/compose.yaml --env-file /private/infrastructure.env up -d --wait --remove-orphans`
  with a copy of [`deploy/infrastructure/example.env`](infrastructure/example.env).
  Any PostgreSQL 16 with pgvector works instead, attached to the `people-gator-db`
  network (`docker network connect people-gator-db <container>`), including the
  production database.
- **Traefik** on the `web` network with the `websecure` entrypoint and the
  `tlschallenge` resolver, and DNS for `*.<preview host>`, the staging host, the
  production host and pgAdmin pointing at it.
- **OTLP collector** (for `otel`) reachable from the `logging` network.
- **Runners**: one self-hosted runner per host as the deployment account,
  labelled `people-gator-preview`, `people-gator-staging` and/or
  `people-gator-release`, with `docker context use rootless` done once and the
  [job-started guard](runner/job-started.sh) in its `.env`
  (`PEOPLE_GATOR_RUNNER_ENVIRONMENT=preview,staging`). Settings → Actions →
  General: require approval for all outside collaborators.

Then open a pull request or run **CI** manually on `main` (`operation=update`,
or `snapshot-init` for a fresh staging database). A deploy job's `preflight`
step fails with the secret name and field when something is missing; each
success appears under the repository's Deployments.

## Conventions

| Fixed by the deployment | Value |
| --- | --- |
| Docker daemon | the runner account's current context |
| Networks | `web` (Traefik), `people-gator-db` (PostgreSQL), `logging` (collector) |
| Compose projects | `people-gator-pr-<N>`, `people-gator-staging`, `people-gator-release` |
| State and generated files | `~/.local/opt/people-gator-deploy/state/<pr\|staging\|release>` on the host |
| TLS | Traefik `tlschallenge` resolver |
| Login tokens and CORS | issuer `https://<host>`, audience `<host>` |
| Previews' media | local Docker volume per PR; `"storage"` overrides |
| Images | `ghcr.io/<repo>-frontend` and `-backend`, tag `sha-<commit>` |
