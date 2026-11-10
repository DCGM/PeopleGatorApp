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
- Networks: `web` with an existing Traefik (entrypoint `websecure`, resolver
  `tlschallenge`; wildcard issuance needs DNS-01), `people-gator-db` for
  PostgreSQL (created by the shared stack, or `docker network create
  --internal people-gator-db`), and `logging` with the OTLP collector when
  `otel` is configured.
- DNS: `*.<preview host>`, the staging host, the production host and pgAdmin
  point at the Traefik host. The preview wildcard does not cover staging.

## Shared PostgreSQL and pgAdmin

[`deploy/infrastructure/compose.yaml`](../infrastructure/compose.yaml) runs
PostgreSQL 16 with pgvector as `people-gator-postgres` on `people-gator-db` (no
published port) and pgAdmin behind Traefik, with a private copy of
[`example.env`](../infrastructure/example.env) holding the two passwords:

```sh
docker compose -f deploy/infrastructure/compose.yaml --env-file /private/infrastructure.env up -d --wait --remove-orphans
```

Rerun the same command after editing the file or pulling a newer `main`;
passwords and volumes are kept. Back up the env file with the
`people-gator-preview-infra_postgres-data` and `…_pgadmin-data` volumes. The
admin URL for `PREVIEW_CONFIG` and `STAGING_CONFIG` is
`postgresql://preview_admin:<POSTGRES_ADMIN_PASSWORD>@people-gator-postgres:5432/postgres`.
Any other PostgreSQL 16 with pgvector works instead, attached to
`people-gator-db` (`docker network connect people-gator-db <container>`), as does
the production database with its application and optional migration roles.

pgAdmin: `https://<PGADMIN_HOST>`, login `PGADMIN_DEFAULT_EMAIL` with
`PGADMIN_DEFAULT_PASSWORD`. Its preconfigured server connects as `preview_admin`.
A PR-only connection uses role/database `preview_pr_<N>` and the password in
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
in `storage`. Sign in at `https://<host>/staging-login.html` with accounts
provisioned in that bucket. Only database backup objects are downloaded by
`snapshot-init`/`refresh` ([backup gathering](README.md#backup-gathering)).

Releases need an external PostgreSQL on `people-gator-db` (already migrated or
new) with the application role from `database` and, optionally, a separate
migration role from `migration_database`; private object storage holding users,
API keys and JWKs, preserved across releases; and a backup before any release
that migrates ([backup](../backup/README.md)), recorded in a mode-600 host file
for the workflow's `backup_record` input. The frontend embeds demo auto-login
credentials: put the release behind a reviewed access boundary.
