# people-gator-deploy

One installable deployment utility for **PR previews**, **staging from `main`**
and **tagged releases**. It is a standard-library-only Python package with the
`people-gator-deploy` command and an equivalent Python API
(`people_gator_deploy.environments.Environment`). Compose files, the login page,
the collector configuration and the snapshot worker ship inside the package.

**Prerequisites:** Linux, Python 3.11+ with `venv`/`ensurepip`, Git, Docker Engine
and Docker Compose v2.32+, plus the proxy, DNS, runners and buckets in
[HOSTS.md](HOSTS.md). The first installation of each revision downloads
`setuptools` from the configured package index to build the wheel. No API
dependencies are installed on the host; database snapshot work runs in
operation-scoped backend containers.

## First setup

As each deployment runner account (no sudo needed):

```sh
git clone https://github.com/DCGM/PeopleGatorApp.git && cd PeopleGatorApp
python3 deploy/install.py --user --revision "$(git rev-parse origin/main)"
export PATH="$HOME/.local/bin:$PATH"

cp deploy/people-gator-deploy/examples/pr.json /secure/place/pr.json   # edit, keep private
people-gator-deploy pr configure --input /secure/place/pr.json --dry-run
people-gator-deploy pr configure --input /secure/place/pr.json
people-gator-deploy pr install            # creates shared PostgreSQL/collector/pgAdmin
people-gator-deploy pr preflight

people-gator-deploy staging configure --input /secure/place/staging.json
people-gator-deploy staging install
# after the next successful main CI build:
people-gator-deploy staging snapshot-init   # or staging.yml → operation snapshot-init
```

Then delete the edited input copies; the descriptor is now the only private
config. Releases follow the same pattern with `examples/release.json` on the
release runner account. After that, workflows run everything automatically.

## Installation and updates

```sh
python3 deploy/install.py --user --revision <40-character-sha>            # default: ~/.local
python3 deploy/install.py --user --prefix '/srv/deploy tools' --revision <sha>
sudo python3 deploy/install.py --system --revision <sha> --run-as <deployment-user>
```

| Scope | Executable | Versions | Descriptors | State |
| --- | --- | --- | --- | --- |
| user (default) | `~/.local/bin` | `~/.local/lib/people-gator-deploy/versions/<sha>` | `~/.local/opt/people-gator-deploy/environments/<env>/config.json` | `~/.local/opt/people-gator-deploy/state` |
| system | `/usr/local/bin` | `/opt/people-gator-deploy/versions/<sha>` | `/etc/people-gator-deploy/environments/<env>/config.json` | `/var/lib/people-gator-deploy` |

The installer reads only committed files (`git archive` of the requested commit),
builds a wheel into a new virtual environment, records version, commit, schema
versions and a SHA-256 of every installed file in `installation.json`, verifies
it, then atomically renames it into `versions/<sha>`. Interrupted or failed
installs leave earlier versions and the default executable untouched. Installing
an existing commit only re-verifies it. The default executable
(`bin/people-gator-deploy`) moves only to a descendant commit, so installing an
older commit pins it without downgrading the default.

**How updates happen.** Every deployment workflow run installs the utility at its
own workflow commit — the reviewed `main` commit that triggered it, or the tagged
commit for releases — before doing anything else, and then uses that exact
versioned executable for the whole job:

- If that version is already installed and its file digests verify, it is reused
  (about 0.1 s). A corrupt or modified version fails the job.
- Otherwise it is built and installed (a few seconds; needs Git and package-index access), and the
  default executable advances if the commit is newer.
- So after any merge to `main`, the next preview/staging job on each runner
  account runs the new utility; nothing is checked against GitHub separately, and
  no host job polls for updates.

Outside CI, update the interactive default with `people-gator-deploy self update
--from-main` (clones into a temporary directory, resolves `main` to an exact
commit, then calls the same installer) or pin a version with
`self ensure --revision <sha>`; `self check` verifies the running installation.
A system installation is only upgraded by its operator; CI refuses to touch it.
Utility updates never change an environment; `<env> update` never changes the
utility. Old versions are kept (about 31 MB each, one per deployed `main` commit); remove
`versions/<sha>` manually only when no job or container uses it.

## Descriptors

Each environment has one versioned descriptor (mode 600, owned by the deployment
account) holding all its settings and secrets. It is selected by, in order:
`--config <path>`, `PEOPLE_GATOR_DEPLOY_CONFIG`, then the installation scope's
`environments/<env>/config.json`. Every command prints the selected path and
scope. Repository `.env` files and ambient AWS/Docker/Compose variables are never
read.

```sh
people-gator-deploy staging configure --input <json> [--dry-run]   # create or merge
people-gator-deploy staging configure --interactive                 # top-level prompts
people-gator-deploy staging migrate-config [--dry-run]              # explicit schema upgrades
```

`configure` deep-merges the input into the descriptor (so a file with only
`{"storage": {"secret_access_key": "…"}}` rotates one secret), validates
everything, keeps a private `config.backup-<sha256>.json` and refuses concurrent
edits (`--expected-digest` for read-modify-write tools). It never contacts
services or prints secrets. Once installed, state/infrastructure paths and the
staging bucket identity cannot change: that needs a data migration, not an empty
destination.

Common fields: `repository`, absolute `state_dir`, explicit `docker_context`,
`web_network`, and the hostname (`domain` for previews, `host` otherwise).
Optional: `certificate_resolver`, `otel_network`, `otel_http_endpoint`,
`preview_log_port`, `pgadmin_host`, `pgadmin_email`. Complete examples:
[`pr`](examples/pr.json), [`staging`](examples/staging.json),
[`release`](examples/release.json).

* **pr** — `users_file`, `database_network`, and `infrastructure`
  (`mode: managed`, a Compose `project` and its own `state_dir`): the preview
  environment owns the shared PostgreSQL/collector/pgAdmin.
* **staging** — `host`, `database_network`, `infrastructure` (`mode: external`,
  the preview's `project`/`state_dir`) and four sections:

  | Section | Needed by | Contents |
  | --- | --- | --- |
  | `storage` | every operation | Staging S3 bucket: `endpoint_url` (HTTPS), `region`, `bucket_name`, `access_key_id`, `secret_access_key`, optional `timeout_seconds` |
  | `backup_source` | `snapshot-init`, `refresh` | Backup bucket reader: `endpoint_url`, `region`, `bucket`, keys, optional `prefix` |
  | `media_source` | `snapshot-init`, `refresh` | Media bucket reader: `endpoint_url`, `region`, `bucket`, keys, optional prefixes |
  | `accounts` | `snapshot-init`, `refresh` | Argon2id `users` for the four staging accounts, optional `api_keys` |

  Optional `media_transfer: {"concurrency": 8, "max_object_mib": 256}`. Routine
  `staging update` needs only `storage`; snapshot operations validate all
  sections before any lookup or change.
* **release** — `host`, `database_network` (external PostgreSQL), mode-600
  `runtime_file` and `migration_file` with only `PEOPLE_GATOR_API__*` lines, and
  `"access_reviewed": true` (see the access boundary below). Optional `project`,
  `backend_memory`.

## Operations

| Operation | pr | staging | release | Meaning |
| --- | --- | --- | --- | --- |
| `configure`, `migrate-config` | ✓ | ✓ | ✓ | Edit/validate the descriptor only |
| `preflight` | ✓ | ✓ | ✓ | Read-only: descriptor, inputs, Docker/Compose, networks, installation |
| `status` | ✓ (`--pr`) | ✓ | ✓ | Read-only: configured / provisioned / running / healthy, recorded SHA/images |
| `check` | ✓ (`--pr`) | ✓ | ✓ | Runtime-role database check and routed readiness; nonzero when unhealthy |
| `install` | ✓ | ✓ | ✓ | Provision managed resources once; repeat is a no-op |
| `update` | `--run-id` | `[--run-id]` | `--tag [--commit] [--run-id] [--backup-record]` | Deploy a verified build with existing resources |
| `uninstall` | ✓ | ✓ | ✓ | Remove this environment's containers; keep data, credentials, config, shared infrastructure |
| `start` / `stop` | `--pr` | ✓ | ✓ | Same images; `start` repeats the check and readiness gates |
| `logs` | `--pr` | ✓ | ✓ | Private operator output (`--tail`) |
| `cleanup` / `reconcile` | ✓ | | | Remove one closed preview / all previews GitHub reports closed |
| `snapshot-init` / `refresh` | | ✓ | | Populate once / replace with `--backup-record` |
| `database-migrate` | | | ✓ | Migration role then runtime check, with `--backup-record` |
| `recover` | | | ✓ | Reactivate retained previous images (`--backup-record --compatibility-reviewed`) |
| `infra-upgrade` | ✓ | | | Owner-only explicit shared-infrastructure upgrade |

Exit codes: `0` success, `1` actionable failure, `2` invalid usage, `130` cancelled.
Failures name the selected path, the field or condition and a corrective
command, for example
`staging configuration: <path>; backup_source: backup_source.endpoint_url must be an explicit HTTPS S3-compatible endpoint; run people-gator-deploy staging configure --config '<path>' --input <private-json>`.
Secret values and raw service output are never printed; failed service output is
kept in the environment's private `last-error.log`.

**Ownership and locks.** Installation is fresh only: `install` refuses a non-empty
`state_dir`, infrastructure files or an existing Compose project it did not
create, and refusals happen before anything is written. It records `owned.json`
and, for managed infrastructure, `infrastructure-owned.json`; an external
environment cannot change infrastructure it does not own. Operations take the
environment's `environment.lock`, then the infrastructure `controller.lock` —
shared for environment work, exclusive for `install`/`infra-upgrade` — so a long
staging refresh does not block previews. Operations journal `operation.json`;
success state is written only after routed readiness. Cancellation (SIGTERM or
Ctrl-C) removes the operation's own containers.

## Environments

**PR previews.** `pr update --run-id` deploys a successful same-repository PR CI
run whose head is still an open PR head; images are verified by revision label
and pinned by digest. Each preview has its own database, role and storage, and
runs storage-init → migrate → seed → startup → routed readiness. Redeployments
keep credentials, seeded identities, edits and media. `pr cleanup --pr N` removes
one closed preview including its database; `pr reconcile` repeats that for every
preview GitHub reports closed (API errors never imply closure). `pr uninstall`
stops all previews but keeps their data.

**Staging.** `staging update` deploys the current successful main build and
retains the database, media and credentials; it never downloads, restores or
seeds, and fences stale attempts before migration and activation. Initialize
once with `staging snapshot-init [--exact-key <dated-key>]`; replace data only
with `staging refresh --backup-record <private file>`. Preparation restores the
verified backup into a new generation database, copies **only media referenced
by the restored rows** (keys derived with the application's canonical helpers;
nothing is listed) with bounded parallelism, reports objects absent at the
source separately from objects that change during transfer, provisions
independent auth without overwriting existing users/keys/JWKs, validates, and
switches the database/media pair together. Progress streams to a private
`*.progress.log` in the generation directory. Failures keep the active pair.

**Releases.** A `v*` tag push runs `release.yml`. The tag resolves to its commit
(annotated or lightweight); moved tags, tags not on `main`, and commits without a
successful main-push CI run are rejected, and that run's tested images are
promoted by digest. If the runtime check reports a pending migration, delivery
stops until rerun with `--backup-record` (take and verify a backup first — see
[backup](../backup/README.md)); then migrate → full runtime-role check → backend
startup → routed readiness → state commit. Expect downtime while the backend
restarts. Re-delivering the deployed tag is a no-op; a tag that does not contain
the deployed commit is refused. `release recover` reactivates the retained
previous images only if their database check accepts the current schema;
changing images never undoes migrations and nothing downgrades a schema. After a
failed activation, recovery targets the last healthy committed release, including
when the first upgrade fails. After a successful activation, it targets the
retained previous release. Activation journals retain the complete environment
and recovery target; retries repair interrupted state/environment/history
publication before treating a delivery as complete.

**Release access boundary.** The production stack has no reload, debug, seed or
development mounts, but the current frontend build embeds demo auto-login
credentials ([DEPLOYMENT.md](../../docs/DEPLOYMENT.md)). Browser-bundled
credentials are not private authentication: place the release behind a
reviewed access boundary (for example, proxy authentication or a private
network) before setting `access_reviewed`.

## CI/CD

Workflows check out their own reviewed commit (`github.workflow_sha`, never a PR
head), run `deploy/install.py --user --revision "$GITHUB_WORKFLOW_SHA"` (see
[updates](#installation-and-updates)), run `<env> preflight`, then one lifecycle
operation with that pinned executable. In CI the installer only accepts the
default-branch `pr-preview.yml`, `staging.yml` and `release.yml`, plus
`release.yml` at a `v*` tag whose commit is already on `main`. Missing
configuration fails the job with the remedy; CI never prompts, guesses setup or
uses sudo. Each runner account needs its own configured descriptors.

## Development

```sh
PYTHONPATH=deploy/people-gator-deploy/src python3 -B -m unittest discover -s deploy/people-gator-deploy/tests -v
# Database-backed and image-backed suites, from people-gator-api with its uv environment:
STAGING_TEST_DATABASE_PORT=… STAGING_TEST_POSTGRES_CONTAINER=… uv run --locked python ../deploy/people-gator-deploy/tests/test_snapshot.py -v
PREVIEW_TEST_POSTGRES_CONTAINER=… PYTHONPATH=deploy/people-gator-deploy/src python3 -B deploy/people-gator-deploy/tests/test_preview.py
PREVIEW_TEST_OTEL=1 python3 -B deploy/people-gator-deploy/tests/test_observability.py
```

`test_staging_runtime.py` needs a backend image, an internal network aliasing
PostgreSQL as `preview-postgres` and Docker; see the PR CI workflow for the setup.
