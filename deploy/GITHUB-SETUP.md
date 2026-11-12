# Deployment setup

Each environment is configured by a short list of repository **variables**
(Settings → Secrets and variables → Actions → Variables) and **secrets**,
prefixed `PREVIEW_`, `STAGING_` or `PRODUCTION_`. Everything not listed here is a
fixed convention (table at the end).

Store `STAGING_*` secrets in the `staging` environment and `PRODUCTION_*` secrets
in `production` (Settings → Environments, or `gh secret set … --env`). Those
environments only admit `main` and `v*` tags, so pull-request workflows cannot
read them; a repository secret is readable by any same-repository pull request.
The workflow uses the same names either way. `PREVIEW_*` secrets stay repository
secrets.

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
gh secret set PREVIEW_DATABASE_URL --body 'postgresql://postgres:SECRET@postgres:5432/postgres'
gh variable set PREVIEW_OTEL_ENDPOINT --body http://lgtm:4318
gh secret set PREVIEW_RUM_CLIENT_TOKEN --body RUM_TOKEN

gh variable set STAGING_HOST --body staging.peoplegator.dev
gh secret set STAGING_DATABASE_URL --env staging --body 'postgresql://postgres:SECRET@postgres:5432/postgres'
gh variable set STAGING_S3_BUCKET --body peoplegator-staging
gh variable set STAGING_S3_REGION --body us-east-1
gh variable set STAGING_S3_ENDPOINT_URL --body https://s3.example.org
gh secret set STAGING_S3_ACCESS_KEY_ID --env staging --body KEY
gh secret set STAGING_S3_SECRET_ACCESS_KEY --env staging --body SECRET
gh variable set STAGING_BACKUP_S3_BUCKET --body peoplegator-db-backup
gh variable set STAGING_BACKUP_S3_PREFIX --body production/db-backups/
gh variable set STAGING_BACKUP_S3_REGION --body us-east-1
gh variable set STAGING_BACKUP_S3_ENDPOINT_URL --body https://s3.example.org
gh secret set STAGING_BACKUP_S3_ACCESS_KEY_ID --env staging --body READ_ONLY_KEY
gh secret set STAGING_BACKUP_S3_SECRET_ACCESS_KEY --env staging --body READ_ONLY_SECRET
gh variable set STAGING_OTEL_ENDPOINT --body http://lgtm:4318

gh variable set PRODUCTION_HOST --body people.example.org
gh secret set PRODUCTION_DATABASE_URL --env production --body 'postgresql://people_gator:SECRET@postgres:5432/people_gator'
gh variable set PRODUCTION_S3_BUCKET --body peoplegator
gh variable set PRODUCTION_S3_REGION --body us-east-1
gh secret set PRODUCTION_S3_ACCESS_KEY_ID --env production --body KEY
gh secret set PRODUCTION_S3_SECRET_ACCESS_KEY --env production --body SECRET
gh variable set PRODUCTION_OTEL_ENDPOINT --body http://lgtm:4318
gh secret set PRODUCTION_OTEL_HEADERS --env production --body 'Authorization=Basic BASE64'
```

## Hosts

- **PostgreSQL and Traefik** on each host, from
  [`deploy/infrastructure/compose.yaml`](infrastructure/compose.yaml). As the
  deployment account, from anywhere:

  ```sh
  ref=main; d=~/peoplegator-infra; t=$(mktemp -d) && git clone -q --depth 1 --branch $ref https://github.com/DCGM/PeopleGatorApp.git $t && install -d -m 700 $d && cp $t/deploy/infrastructure/compose.yaml $t/deploy/infrastructure/example.env $t/deploy/infrastructure/traefik.example.yaml $d/ && rm -rf $t && { [ -f $d/infra.env ] || { sed -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(openssl rand -hex 32)|" -e "s|^PGADMIN_PASSWORD=.*|PGADMIN_PASSWORD=$(openssl rand -hex 16)|" -e "s|^TRAEFIK_CONFIG=.*|TRAEFIK_CONFIG=$d/traefik.yaml|" -e "s|^DOCKER_SOCKET=.*|DOCKER_SOCKET=$(docker context inspect -f "{{.Endpoints.docker.Host}}" | sed "s|^unix://||")|" $d/example.env > $d/infra.env && for k in HTTPS_PORT TRAEFIK_DASHBOARD_HOST PGADMIN_HOST COMPOSE_PROFILES; do v=$(printenv $k) && sed -i "s|^#* *$k=.*|$k=$v|" $d/infra.env || true; done; }; } && chmod 600 $d/infra.env && { [ -f $d/traefik.yaml ] || cp $d/traefik.example.yaml $d/traefik.yaml; } && { [ -f $d/dashboard.users ] || { p=$(openssl rand -hex 12); printf "admin:%s\n" "$(openssl passwd -apr1 $p)" > $d/dashboard.users && chmod 600 $d/dashboard.users && echo "Traefik dashboard login: admin / $p"; }; } && docker compose -f $d/compose.yaml --env-file $d/infra.env up -d --wait --remove-orphans
  ```

  It shallow-clones the repository (`ref` selects the branch), copies
  `compose.yaml` and the examples into `~/peoplegator-infra`, creates `infra.env`
  (from [`example.env`](infrastructure/example.env), with a generated PostgreSQL
  password and the current Docker socket) and `traefik.yaml` (from
  [`traefik.example.yaml`](infrastructure/traefik.example.yaml)) only if they do
  not exist yet, then starts the stack. The first run also creates the Traefik
  dashboard login (`dashboard.users`) and prints its password once; the dashboard
  is at `https://traefik-preview.peoplegator.dev` (`TRAEFIK_DASHBOARD_HOST`).
  Reruns refresh `compose.yaml` and keep your files. Set the ACME e-mail in `traefik.yaml` and,
  if needed, `HTTPS_PORT` in `infra.env`, and rerun to apply. The database URLs use
  `POSTGRES_PASSWORD` from `infra.env`.
  PostgreSQL runs as `postgres` on the internal `db` network. Traefik serves only
  HTTPS on `HTTPS_PORT` and gets a Let's Encrypt certificate for each host name
  on its first request through the TLS-ALPN-01 challenge, which needs Let's
  Encrypt to reach the host name on public port 443: either this Traefik
  directly, or an edge proxy that forwards the TLS stream unchanged (TCP router
  with `tls.passthrough`) to `HTTPS_PORT`. The public URLs stay `https://<host>`
  without a port; the deploy's readiness check calls them. Point DNS for
  `*.<preview host>`, the staging host and the production host at the public
  entry.
- **OTLP collector** on the `logging` network, only when `OTEL_ENDPOINT` is set.
- **Runners**: one self-hosted runner per host, installed as the deployment
  account with [`deploy/runner/install.sh`](runner/install.sh) as a lingering
  `systemctl --user` service with the job-started guard. Once as root:
  `sudo loginctl enable-linger <account>`; once as the account:
  `docker context use rootless`. Then, with a registration token from Settings →
  Actions → Runners → New self-hosted runner:

  ```sh
  ref=main; t=$(mktemp -d) && git clone -q --depth 1 --branch $ref https://github.com/DCGM/PeopleGatorApp.git $t && RUNNER_TOKEN=<token> $t/deploy/runner/install.sh preview,staging; rm -rf $t
  ```

  Use `release` on the production host. Settings → Actions → General: require
  approval for all outside collaborators.

Then open a pull request or push to `main`. A deploy job's `preflight`
step fails with the variable's name when something is missing or invalid; each
success appears under the repository's Deployments.

## Staging host

Staging runs under its own Linux account with its own rootless Docker, next to
the preview account: the infrastructure stack uses fixed names (`postgres`, `db`,
`web`), so each Docker daemon runs one. The staging database lives in that
account's `postgres` container; staging creates its own database and role there.

1. **Account.** As root: `useradd -m peoplegator-staging && loginctl enable-linger peoplegator-staging`.
   Open a login session (`sudo machinectl shell peoplegator-staging@`; plain `su`
   has no systemd user session), install rootless Docker
   (`dockerd-rootless-setuptool.sh install`) and run `docker context use rootless`.
2. **PostgreSQL, Traefik and pgAdmin** on a port of its own. The exported values
   go into the new `infra.env`:

   ```sh
   export HTTPS_PORT=2443 TRAEFIK_DASHBOARD_HOST=traefik-staging.peoplegator.dev PGADMIN_HOST=pgadmin-staging.peoplegator.dev COMPOSE_PROFILES=pgadmin
   ref=main; d=~/peoplegator-infra; t=$(mktemp -d) && git clone -q --depth 1 --branch $ref https://github.com/DCGM/PeopleGatorApp.git $t && install -d -m 700 $d && cp $t/deploy/infrastructure/compose.yaml $t/deploy/infrastructure/example.env $t/deploy/infrastructure/traefik.example.yaml $d/ && rm -rf $t && { [ -f $d/infra.env ] || { sed -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(openssl rand -hex 32)|" -e "s|^PGADMIN_PASSWORD=.*|PGADMIN_PASSWORD=$(openssl rand -hex 16)|" -e "s|^TRAEFIK_CONFIG=.*|TRAEFIK_CONFIG=$d/traefik.yaml|" -e "s|^DOCKER_SOCKET=.*|DOCKER_SOCKET=$(docker context inspect -f "{{.Endpoints.docker.Host}}" | sed "s|^unix://||")|" $d/example.env > $d/infra.env && for k in HTTPS_PORT TRAEFIK_DASHBOARD_HOST PGADMIN_HOST COMPOSE_PROFILES; do v=$(printenv $k) && sed -i "s|^#* *$k=.*|$k=$v|" $d/infra.env || true; done; }; } && chmod 600 $d/infra.env && { [ -f $d/traefik.yaml ] || cp $d/traefik.example.yaml $d/traefik.yaml; } && { [ -f $d/dashboard.users ] || { p=$(openssl rand -hex 12); printf "admin:%s\n" "$(openssl passwd -apr1 $p)" > $d/dashboard.users && chmod 600 $d/dashboard.users && echo "Traefik dashboard login: admin / $p"; }; } && docker compose -f $d/compose.yaml --env-file $d/infra.env up -d --wait --remove-orphans
   ```

   pgAdmin is at `https://pgadmin-staging.peoplegator.dev` behind the printed
   dashboard login, then its own login (`grep ^PGADMIN_ ~/peoplegator-infra/infra.env`).
   Its server `postgres` takes `POSTGRES_PASSWORD` from `infra.env`.
3. **Edge and DNS.** Point `staging.peoplegator.dev`, `traefik-staging.peoplegator.dev`
   and `pgadmin-staging.peoplegator.dev` at the public entry. On the edge proxy, add
   them to the staging TCP router (`tls.passthrough`) towards `<host IP>:2443`, not
   `localhost`. The edge entry point needs `allowACMEByPass: true` so certificate
   challenges reach this Traefik.
4. **Runner**, as the staging account, with a new registration token:

   ```sh
   ref=main; t=$(mktemp -d) && git clone -q --depth 1 --branch $ref https://github.com/DCGM/PeopleGatorApp.git $t && RUNNER_TOKEN=<token> $t/deploy/runner/install.sh staging; rm -rf $t
   ```

5. **Secrets** in the `staging` environment (Settings → Environments → staging).
   This copies the database URL from the host without printing it; the S3
   commands prompt for their values:

   ```sh
   R=DCGM/PeopleGatorApp
   ssh peoplegator-staging@<host> '. ~/peoplegator-infra/infra.env; printf "postgresql://%s:%s@postgres:5432/postgres" "$POSTGRES_USER" "$POSTGRES_PASSWORD"' | gh secret set STAGING_DATABASE_URL --env staging -R $R
   gh secret set STAGING_S3_ACCESS_KEY_ID --env staging -R $R
   gh secret set STAGING_S3_SECRET_ACCESS_KEY --env staging -R $R
   ```

6. **Logins.** Upload the staging users to `peoplegator_api/users.json` in the
   `STAGING_S3_BUCKET`, in the format of `people-gator-api/example.users.json`.
7. **Deploy.** Every push to `main` deploys staging (or run **CI** manually on
   `main`). The first deploy creates an empty database; later ones migrate it.

## Conventions

| Fixed by the deployment | Value |
| --- | --- |
| Docker daemon | the runner account's current context |
| Networks | `web` (Traefik), `db` (PostgreSQL), `logging` (collector, only with `OTEL_ENDPOINT`) |
| Compose projects | `people-gator-pr-<N>`, `people-gator-staging`, `people-gator-release` |
| State and generated files | `~/.local/opt/people-gator-deploy/state/<pr\|staging\|release>` on the host |
| TLS | HTTPS only on Traefik's `websecure` entry point; certificates from its ACME resolver |
| Login tokens and CORS | issuer `https://<HOST>`, audience `<HOST>` |
| Images | `ghcr.io/<repo>-frontend` and `-backend`, tag `sha-<commit>` |
