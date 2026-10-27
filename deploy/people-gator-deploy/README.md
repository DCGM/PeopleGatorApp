# people-gator-deploy

One installable deployment utility for **PR previews**, **staging from `main`**
and **tagged releases**. It is a Python package with a pinned boto3 S3 client and the
`people-gator-deploy` command and an equivalent Python API
(`people_gator_deploy.environments.Environment`). Compose files, the login page,
the collector configuration and the database validator ship inside the package.

**Prerequisites:** Linux, Python 3.11+ with `venv`/`ensurepip`, Git, Docker Engine
and Docker Compose v2.32+, plus the proxy, DNS, runners and buckets in
[HOSTS.md](HOSTS.md). The first installation of each revision downloads
`setuptools` to build the wheel and the fully pinned S3 client dependency set
from the configured package index. The host package gathers backup archives;
database restore uses the infrastructure PostgreSQL 16 tools and database
validation runs in operation-scoped backend containers. Candidate application
code never selects backups or receives backup credentials.

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

# Supply a private local custom-format dump, its SHA-256/source revision,
# and an externally maintained API runtime env file in the staging descriptor.
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

The launcher resolves that default symlink to select its version's interpreter.
Linux `readlink` and `dirname` (normally supplied by coreutils) must be on PATH.
Version 1.0.1 fixes invocation through the default executable; reinstall a newer
reviewed revision with `deploy/install.py` if a 1.0.0 default reports `bin/python`
missing. Versioned executables remain usable during that upgrade.

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
`{"snapshot_source_file": "/private/staging-backup-source.json"}` selects the
automatic source), validates
everything, keeps a private `config.backup-<sha256>.json` and refuses concurrent
edits (`--expected-digest` for read-modify-write tools). It never contacts
services or prints secrets. Once installed, state/infrastructure paths, Docker
context, project names and
private runtime/migration file paths cannot change implicitly. Their contents
can be maintained externally without switching the utility's resource identity.

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
  the preview's `project`/`state_dir`) and an absolute `runtime_file` pointing to
  an owned private API env file. It contains externally managed application
  settings such as storage, media prefixes and authentication. Only the backend
  receives it; migration/check/validation tools receive database settings only.
  It must not define persistence settings, which staging owns.

  `snapshot_source_file` names an owned private JSON file with the automatic
  read-only backup source. It is read only for `snapshot-init`/`refresh`.
  See [Backup gathering](#backup-gathering) for setup, selection and failures.
  Optional `project` defaults to `people-gator-staging`.

  Legacy `snapshot` objects remain supported for explicit local recovery. To
  switch an existing fixed-local descriptor, configure `snapshot_source_file`;
  configure removes `snapshot` atomically and preserves a private descriptor
  backup. It does not touch staging data. Supplying both settings directly is
  rejected. No per-date path/checksum/revision edits are needed afterward.
  Pre-rollout descriptors must also configure `runtime_file`, which removes
  obsolete `storage`, `backup_source`, `media_source`, `accounts` and
  `media_transfer` sections. Their external application setup remains operator work.
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
`staging configuration: <path>; snapshot: snapshot needs an absolute path, sha256 and application_revision; run people-gator-deploy staging configure --config '<path>' --input <private-json>`.
Secret values and raw service output are never printed; failed service output is
kept in the environment's private `last-error.log`.

**Ownership and locks.** Installation is fresh only: `install` refuses a non-empty
`state_dir`, infrastructure files or an existing staging/release/infrastructure Compose
project it did not create. Ownership is recorded only after those checks pass.
A first staging/release deployment also checks for project collisions. PR updates
remove the selected PR project's previous containers before redeployment, even
when local per-PR state is unavailable; databases and volumes are retained.
Installation records `owned.json`
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
runs container removal → storage-init → migrate → seed → startup → routed readiness.
Updates stop and remove the selected PR project's containers and orphans without
deleting its database or media volume. Retained state keeps credentials, seeded
identities, edits and media; when local credentials are unavailable, database-role
access is regenerated after stopping the old containers. Stale and already-complete
runs leave the current deployment alone. Expect downtime during preparation; a
failed migration or seed leaves the preview stopped until a successful retry.
`pr cleanup --pr N` removes
one closed preview including its database; `pr reconcile` repeats that for every
preview GitHub reports closed (API errors never imply closure). `pr uninstall`
stops all previews but keeps their data.

**Staging.** `staging update` deploys the current successful main build and
retains the database; it never reads a snapshot, restores or seeds. Initialize
once with `staging snapshot-init`; replace the database only with
`staging refresh --backup-record <private file>`. The one-time initialization
check runs under the environment lock, so queued initializations cannot replace
an already initialized database without the refresh backup guard.

Preparation gathers the latest production archive as described below, pins its
local inode, verifies SHA-256/custom format, restores original rows into a separate
database/role, rejects changes during restore, and validates rows, links, vectors
and migration history.
It then migrates, checks the runtime role and starts the backend/frontend before
recording success. Failed refreshes retain the active database.

Application S3 storage and all media/authentication objects are managed externally. Staging does not
provision buckets/users/keys, copy or validate media, change storage generations,
or impose S3 migration requirements. Missing media does not reject a database
snapshot. Supply the running application's external settings through
`runtime_file`; application startup and routed readiness remain required. Normal
updates and database refreshes leave that file and external storage untouched.

### Backup gathering

Provision a separate read-only identity once for the production backup prefix:
`ListBucket` restricted to that prefix, `GetObject` and `GetObjectVersion` only.
Use the [restore-reader policy example](../backup/restore-policy.example.json).
It needs no production database access, writes, deletes or application storage
permissions. Keep the backup publisher's identity separate.

Copy [staging-backup-source.example.json](examples/staging-backup-source.example.json)
to a private host directory outside the checkout and utility installation. Set
an explicit HTTPS endpoint, region, bucket, prefix and the reader credentials.
The JSON is exactly those six fields; no restore database or target settings.
Make the directory mode 700 and file mode 600, owned by the deployment account.
Use system-trusted TLS; a private CA can be supplied through `AWS_CA_BUNDLE`.
No ambient AWS credentials, application settings or instance profile fill missing
values. Do not put backup credentials in `runtime_file` or GitHub input fields.

Configure the reference once (using an absolute private input JSON path):

```json
{"snapshot_source_file": "/private/staging-backup-source.json"}
```

```sh
people-gator-deploy staging configure --input /private/staging-source-change.json --dry-run
people-gator-deploy staging configure --input /private/staging-source-change.json
```

This configuration change does **not** refresh the running database. The next
explicit `snapshot-init` or guarded `refresh` uses the source. Ordinary `update`,
including automatic successful-main deployments, keeps staging edits and never
reads the source file or contacts the backup bucket. Existing initialization,
refresh backup-record and deployment locks remain in force.

Each snapshot operation follows this sequence:

1. List **all pages** under the configured prefix. Accept only direct-child
   `peoplegator-prod-YYYY-MM-DD.dump` names with real calendar dates. Ignore
   unrelated keys, subdirectories, incomplete uploads and invalid dates. Select
   the greatest filename date, independently of listing order or LastModified.
2. HEAD the selected key. Require publisher `sha256` (64 lowercase hex) and
   `application-revision` (40 lowercase hex) metadata, a nonempty ETag and size.
   Pin those values and any version ID for the operation. A newer dated upload
   during this operation is considered only by the **next** snapshot operation.
3. Stream a conditional `If-Match` GET, requesting the pinned version when
   available, into a mode-600 archive inside a mode-700 temporary directory in
   staging state. Check response identity, exact size, SHA-256, `PGDMP` format
   and a second HEAD. Metadata names are case insensitive. There is no persistent
   archive cache and no reuse of a previous selection.
4. Run `pg_restore --list` before provisioning. Restore into an independent
   candidate database, check the open archive for local mutation, validate the
   restored database, then recheck the current S3 identity/metadata before
   proceeding with migration and activation. A changed selected key fails even
   when an older object version remains readable. SHA/revision metadata follows
   the existing trusted publisher contract; it is not a cryptographic signature.
5. Remove the downloaded archive on ordinary success/failure. Write mode-600
   `generation-*/provenance.json` and successful active `state.json` with bucket,
   selected key/date, ETag, available version ID, size, SHA-256, source application
   revision and restored schema revision. These are private deployment evidence;
   credentials and archive contents never enter public summaries.

An empty source, access/network errors, invalid metadata, changed object, corrupt
latest archive or insufficient disk space stops the operation. There is **no
fallback to older backups** and the active staging database is retained. Public
errors give fixed guidance without relaying provider errors or private values.
Check reader grants and connectivity for gathering failures, publisher metadata
for metadata failures, and the trusted source archive for integrity/format
failures. Repair the source deliberately before retrying. Do not overwrite a dated
object as a routine fix. Ensure private disk capacity for the full compressed
archive; abrupt process/host death can leave a private `snapshot-*` directory or
unserved candidate database for operator cleanup after confirming no job is active.
Media/auth copying, publisher installation and a live staging refresh are outside
this configuration transition.

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
publication before treating a delivery as complete. After routed readiness,
publication commits `state.json` before replacing the retained rollback files.
An interruption before that commit preserves the older rollback target; after
the commit, retries and recovery finish the remaining files from the journal.

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
It runs both legacy local restore and latest-source discovery/download/restore
against disposable TLS MinIO. It verifies the newest archive's actual records
and that a corrupt newer archive creates no database. The backend environment
supplies boto3 and application dependencies; no real operator source is read.
