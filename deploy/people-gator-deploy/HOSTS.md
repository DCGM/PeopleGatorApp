# Host prerequisites

Everything the deploy jobs expect on a host and never create. The GitHub side and
the three configuration secrets are in [GITHUB-SETUP.md](../GITHUB-SETUP.md);
commands and operations in the [utility guide](README.md).

## Docker, proxy and networks

- Linux x86-64 (images are built for `linux/amd64`), Docker Engine with Compose
  v2.32+, Python 3.11+ with `venv`, Git, and outbound access to GitHub (API and
  GHCR) and the Python package index.
- The deployment account's **current Docker context** is used (`docker context
  use rootless` once for rootless Docker). Run the runner service, Traefik and
  the shared stack under that account and daemon; containers on one daemon cannot
  join another daemon's networks.
- Networks: `web` with Traefik (HTTPS-only entry point `websecure` whose ACME
  resolver issues a certificate per host name), `db` for PostgreSQL (both
  created by the shared stack), and `logging` with the OTLP collector when
  `OTEL_ENDPOINT` is set.
- DNS: `*.<preview host>`, the staging host and the production host point at
  the Traefik host. The preview wildcard does not cover staging.

## Shared PostgreSQL and Traefik

[`deploy/infrastructure/compose.yaml`](../infrastructure/compose.yaml) runs
PostgreSQL 16 with pgvector as `postgres` on the internal `db` network (no
published port) and Traefik on `web`. Prepare two private files:

- a copy of [`example.env`](../infrastructure/example.env): PostgreSQL password
  and user, `HTTPS_PORT`, the path below and the Docker socket;
- a copy of [`traefik.example.yaml`](../infrastructure/traefik.example.yaml): the
  static Traefik configuration with the HTTPS-only `websecure` entry point, the
  Docker provider and the `letsencrypt` resolver (set the ACME e-mail).

```sh
docker compose -f deploy/infrastructure/compose.yaml --env-file /private/infrastructure.env up -d --wait --remove-orphans
```

Rerun the same command after editing a file or pulling a newer `main`; passwords,
certificates (`traefik-acme` volume) and data are kept. Certificates come from
Let's Encrypt's TLS-ALPN-01 challenge, one per host name on its first request
(each new preview's first page load waits for issuance; Let's Encrypt allows 50
new certificates per week per registered domain, renewals exempt). The challenge
reaches the host name on public port 443: expose Traefik there directly, or
forward the TLS stream unchanged from an edge proxy, for example an edge Traefik
TCP router with `HostSNI(…)` / `HostSNIRegexp(…)` rules and `tls.passthrough: true`
pointing at `HTTPS_PORT`. An edge that terminates TLS itself breaks the challenge
and the inner routers. Test with Let's Encrypt's staging CA (`caServer` in
`traefik.yaml`) first and delete the `traefik-acme` volume when switching.
Rootless Docker needs `net.ipv4.ip_unprivileged_port_start` at or below
`HTTPS_PORT` when it is under 1024.

Back up the env files with the `peoplegator-infra_postgres-data`
volume. `PREVIEW_DATABASE_URL` / `STAGING_DATABASE_URL` is then
`postgresql://<POSTGRES_USER>:<POSTGRES_PASSWORD>@postgres:5432/postgres`.
For a database shell use `docker exec -it postgres psql -U <POSTGRES_USER>`; a
PR-only connection uses role/database `preview_pr_<N>` and the password in
`<state dir>/pr-<N>/state.json`. Never print these files in Actions.

## GitHub runners

The `frontend`, `backend` and `images` jobs run on GitHub-hosted `ubuntu-24.04`
runners; self-hosted runners serve only the deploy jobs of same-repository
events:

| Runner label | Jobs | `PEOPLE_GATOR_RUNNER_ENVIRONMENT` |
| --- | --- | --- |
| `people-gator-preview` | `deploy-preview`, `remove-preview`, `prune-previews` | `preview` |
| `people-gator-staging` | `deploy-staging` | `staging` |
| `people-gator-release` | `deploy-release` | `release` |

Labels only select a runner: in a public repository any workflow in a PR, branch
or tag can request them, and a pull request's workflow file is the pull request's
own. Install the job-started guard on every self-hosted runner. It admits only
this repository's events for the environments listed for that runner
(same-repository pull requests and `main` for `preview`, `main` for `staging`,
`v*` tags whose commit is on `main` for `release`) and refuses fork pull requests
from the event payload, whatever the workflow says:

```sh
install -D -m 755 deploy/runner/job-started.sh ~/.local/libexec/people-gator/job-started.sh
# In each runner directory; the script itself must live outside it:
echo "ACTIONS_RUNNER_HOOK_JOB_STARTED=$HOME/.local/libexec/people-gator/job-started.sh" >> .env
echo "PEOPLE_GATOR_RUNNER_ENVIRONMENT=preview,staging" >> .env   # the environments whose labels this runner carries
```

Restart each runner service while idle so it reads `.env` (`sudo ./svc.sh stop &&
sudo ./svc.sh start`, or `systemctl --user restart github-runner@<runner>` for a
user unit). A job for an unlisted environment is refused and GitHub does not move
it to another runner. Refresh the script copy when `main` changes it. Also set
**Settings → Actions → General → Fork pull request workflows** to require
approval for all outside contributors, and protect `v*` tags with a ruleset.
Deploy jobs use only `GITHUB_TOKEN` (contents, pull-requests and packages read,
deployments write; `images` needs packages write); grant the repository's Actions
access to the `peoplegatorapp-frontend` and `peoplegatorapp-backend` packages if
they are private.

## Single-host isolation

When CI, previews and staging share one machine, give deployments their own
account and Docker daemon, so your personal account holds no deployment secrets
and deployment jobs cannot reach your files or containers:

1. As an administrator, once:

   ```sh
   sudo useradd --create-home --shell /bin/bash gator-deploy
   sudo usermod --add-subuids 231072-296607 --add-subgids 231072-296607 gator-deploy
   sudo loginctl enable-linger gator-deploy
   sudo sysctl -w net.ipv4.ip_unprivileged_port_start=80  # persist in /etc/sysctl.d
   ```

   Never add `gator-deploy` to the `docker` group; that grants root.
2. In a login session for the account (`sudo machinectl shell gator-deploy@`),
   run `dockerd-rootless-setuptool.sh install` and `docker context use rootless`.
3. Move the public Traefik (and its tunnel sidecar) and the OTLP collector to
   this daemon. Keep development proxies on your own daemon and ports.
4. Register the runners as `gator-deploy` with the labels of the environments
   they serve, install them with `sudo ./svc.sh install gator-deploy`, and add
   the job-started guard.
5. Start the shared stack, create the three secrets, then run the CI workflow
   manually on `main` with `operation=snapshot-init` and rerun the latest CI of
   open PRs to redeploy their previews.
6. Remove the old runners (`./config.sh remove`) and the old environments'
   containers, volumes and state from your account.

## Staging and releases

Staging shares the preview PostgreSQL through the same admin URL and keeps its
own database generations; its media, users and keys live in the S3 bucket named
in the `STAGING_S3_*` bucket. Sign in at `https://<host>/staging-login.html` with accounts
provisioned in that bucket. Only database backup objects are downloaded by
`snapshot-init`/`refresh` ([backup gathering](README.md#backup-gathering)).

Releases need an external PostgreSQL on `db` (already migrated or
new) with the application role from `PRODUCTION_DATABASE_URL` and, optionally,
a separate migration role from `PRODUCTION_MIGRATION_DATABASE_URL`; private
object storage holding users,
API keys and JWKs, preserved across releases; and a backup before any release
that migrates ([backup](../backup/README.md)), recorded in a mode-600 host file
for the workflow's `backup_record` input. The frontend embeds demo auto-login
credentials: put the release behind a reviewed access boundary.
