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
published port) and Traefik on `web`. One command, run as the deployment account
from anywhere, clones the repository shallowly (`ref` selects the branch),
copies `compose.yaml` and the examples into `~/peoplegator-infra`, creates the
private files there the first time and starts the stack:

```sh
ref=main; d=~/peoplegator-infra; t=$(mktemp -d) && git clone -q --depth 1 --branch $ref https://github.com/DCGM/PeopleGatorApp.git $t && install -d -m 700 $d && cp $t/deploy/infrastructure/compose.yaml $t/deploy/infrastructure/example.env $t/deploy/infrastructure/traefik.example.yaml $d/ && rm -rf $t && { [ -f $d/infra.env ] || sed -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(openssl rand -hex 32)|" -e "s|^TRAEFIK_CONFIG=.*|TRAEFIK_CONFIG=$d/traefik.yaml|" -e "s|^DOCKER_SOCKET=.*|DOCKER_SOCKET=$(docker context inspect -f "{{.Endpoints.docker.Host}}" | sed "s|^unix://||")|" $d/example.env > $d/infra.env; } && chmod 600 $d/infra.env && { [ -f $d/traefik.yaml ] || cp $d/traefik.example.yaml $d/traefik.yaml; } && { [ -f $d/dashboard.users ] || { p=$(openssl rand -hex 12); printf "admin:%s\n" "$(openssl passwd -apr1 $p)" > $d/dashboard.users && chmod 600 $d/dashboard.users && echo "Traefik dashboard login: admin / $p"; }; } && docker compose -f $d/compose.yaml --env-file $d/infra.env up -d --wait --remove-orphans
```

- `infra.env`, from [`example.env`](../infrastructure/example.env): generated
  PostgreSQL password, user, `HTTPS_PORT`, the Traefik config path and the
  current Docker context's socket;
- `traefik.yaml`, from [`traefik.example.yaml`](../infrastructure/traefik.example.yaml):
  the HTTPS-only `websecure` entry point, the dashboard, the Docker provider and
  the `letsencrypt` resolver (set the ACME e-mail);
- `dashboard.users`: the dashboard's basic-auth login, `admin` with a generated
  password printed once. The dashboard answers only on `TRAEFIK_DASHBOARD_HOST`
  (default `traefik-preview.peoplegator.dev`), behind that login. Add users with
  `printf 'name:%s\n' "$(openssl passwd -apr1 '<password>')" >> ~/peoplegator-infra/dashboard.users`.

Rerun the same command after editing either file or pulling a newer `main`; passwords,
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
own. Every runner therefore runs the job-started guard, which admits only this
repository's events for the environments listed for that runner
(same-repository pull requests and `main` for `preview`, `main` for `staging`,
`v*` tags whose commit is on `main` for `release`) and refuses fork pull requests
from the event payload, whatever the workflow says.

[`deploy/runner/install.sh`](../runner/install.sh) sets a runner up as the
deployment account, as a `systemctl --user` service that keeps running without a
login. Enable lingering once as root (`sudo loginctl enable-linger <account>`),
select the Docker context (`docker context use rootless`), take a registration
token from **Settings → Actions → Runners → New self-hosted runner** (valid for an
hour; a `gh` login with admin rights works instead), then run from anywhere:

```sh
ref=main; t=$(mktemp -d) && git clone -q --depth 1 --branch $ref https://github.com/DCGM/PeopleGatorApp.git $t && RUNNER_TOKEN=<token> $t/deploy/runner/install.sh preview,staging; rm -rf $t
```

Use `release` instead of `preview,staging` on the production host. The script
checks the prerequisites (Docker with Compose on the current context, Python with
venv, git, lingering, a user session), downloads the latest official runner and
verifies its SHA-256, registers it as `<host>-<environments>` with the matching
labels, installs the guard as `~/.local/libexec/people-gator/job-started.sh`,
writes `ACTIONS_RUNNER_HOOK_JOB_STARTED` and `PEOPLE_GATOR_RUNNER_ENVIRONMENT` to
the runner's `.env` and enables `github-runner@<name>` from
[`github-runner@.service`](../runner/github-runner@.service). Rerunning it (without
a token) refreshes the guard, the environment and the service of an existing
runner. Status and logs: `systemctl --user status github-runner@<name>` and
`journalctl --user -u github-runner@<name>`. To remove a runner, stop it with
`systemctl --user disable --now github-runner@<name>`, unregister it with
`~/actions-runner/<name>/config.sh remove --token <token>` (from the same
Settings page) and delete `~/actions-runner/<name>`.

Also set
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
