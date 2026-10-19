# people-gator-deploy

One installable deployment utility for **PR previews**, **staging from `main`**
and **tagged releases**. It is a standard-library-only Python package with the
`people-gator-deploy` command and an equivalent Python API
(`people_gator_deploy.environments.Environment`). Compose files, the login page,
the collector configuration and the snapshot worker ship inside the package.

**Prerequisites:** Linux, Python 3.11+ with `venv`/`ensurepip`, Git, Docker Engine
and Docker Compose v2.32+. The first installation of each revision downloads
`setuptools` from the configured package index to build the wheel. No API
dependencies are installed on the host; database snapshot work runs in
operation-scoped backend containers.

## Install

From a checkout of an explicitly selected, reviewed commit (the checkout is read
with `git archive` and is never modified):

```sh
python3 deploy/install.py --user --revision <40-character-reviewed-sha>
# Custom user prefix (paths with spaces are supported):
python3 deploy/install.py --user --prefix '/srv/deploy tools' --revision <sha>
# Operator only; routine commands then run as the unprivileged account:
sudo python3 deploy/install.py --system --revision <sha> --run-as <deployment-user>
```

The installer prints JSON with the versioned `executable`, scope, descriptor and
state roots and `path_ready`. Add the reported bin directory to `PATH` if needed.

| Scope | Executable | Versions | Descriptors | State |
| --- | --- | --- | --- | --- |
| user (default) | `~/.local/bin` | `~/.local/lib/people-gator-deploy/versions/<sha>` | `~/.local/opt/people-gator-deploy/environments/<env>/config.json` | `~/.local/opt/people-gator-deploy/state` |
| system | `/usr/local/bin` | `/opt/people-gator-deploy/versions/<sha>` | `/etc/people-gator-deploy/environments/<env>/config.json` | `/var/lib/people-gator-deploy` |

`--prefix` replaces `~/.local` (user) or `/` (system). System installs are owned by
root and readable by everyone; descriptor and state roots belong to `--run-as`.
Routine operations never need root.

Each version is a complete virtual environment with an `installation.json`
recording version, source commit, configuration/state schema versions and a
SHA-256 of every installed file. A version is staged and verified before an
atomic rename, so interrupted or failed installs leave the previous version and
default executable working. Reinstalling the same commit verifies and reuses it.
The default executable only moves forward: installing an older commit (for
example, a retried old workflow) pins that version without downgrading the
default. Versions are never deleted automatically; remove an old
`versions/<sha>` directory only when no job or container mount references it.

```sh
people-gator-deploy --version          # version, source commit, schema versions
people-gator-deploy self check         # verify installed file integrity
people-gator-deploy self ensure --revision <sha>   # reuse or install an exact version
people-gator-deploy self update --from-main        # operator: install current reviewed main
```

`self update --from-main` clones into a temporary directory, resolves `main` to an
exact commit and calls the same installer. Utility updates never change an
environment; `<environment> update` never changes the utility. CI cannot upgrade
a system installation; give CI runners their own user installation.

## Descriptors

Each environment has one versioned descriptor (mode 600, owned by the deployment
account). It is selected by, in order: `--config <path>`,
`PEOPLE_GATOR_DEPLOY_CONFIG`, then the installation scope's
`environments/<env>/config.json`. Every command prints the selected path and
scope. Repository `.env` files and ambient AWS/Docker/Compose variables are never
read. Descriptors reference private files; they need not contain every secret.

```sh
people-gator-deploy pr configure --input /private/pr.json --dry-run   # validate only
people-gator-deploy pr configure --input /private/pr.json             # create or merge
people-gator-deploy pr configure --interactive                        # terminal prompts
people-gator-deploy pr migrate-config --dry-run                        # explicit schema upgrades
```

`configure` merges the input into the existing descriptor, preserving other
fields, validates paths/hostnames/overlaps, keeps a private
`config.backup-<sha256>.json` and fails if the file changed concurrently (pass
`--expected-digest` for read-modify-write tools). It never contacts services.
Once an environment is installed, changing its state, infrastructure or private
input paths is refused: that needs a data migration, not an empty destination.

Common fields: `repository` (`DCGM/PeopleGatorApp`), absolute `state_dir`, explicit
`docker_context` (for example `rootless`), `web_network` (external proxy network),
and the hostname (`domain` for previews, `host` otherwise). Optional:
`certificate_resolver`, `otel_network`, `otel_http_endpoint`, `preview_log_port`,
`pgadmin_host`, `pgadmin_email`.

```json
{
  "repository": "DCGM/PeopleGatorApp",
  "state_dir": "/var/lib/people-gator-preview",
  "docker_context": "rootless",
  "domain": "preview.peoplegator.dev",
  "web_network": "web",
  "database_network": "people-gator-preview-db",
  "users_file": "/opt/people-gator-preview/users.json",
  "infrastructure": {"mode": "managed", "project": "people-gator-preview-infra",
                     "state_dir": "/var/lib/people-gator-preview"}
}
```

* **pr** — `users_file` is bind-mounted read-only into the backend (UID 10001): a
  regular file owned by the account or root and not group/world writable.
  `infrastructure.mode: managed` makes this environment own the shared
  PostgreSQL/collector/pgAdmin project.
* **staging** — `host`, its own `state_dir`, and `private_dir` holding mode-600
  `storage.json` (destination S3, `local: null`), `backup-source.json`,
  `media-source.json` and `credential-input.json`. Formats match
  `deploy/preview/staging.*.example.json`; see [STAGING.md](../preview/STAGING.md)
  for bucket permissions and account provisioning. Use
  `infrastructure.mode: external` with the preview infrastructure's `state_dir`
  and `project`. Optional `media_transfer: {"concurrency": 8, "max_object_mib": 256}`.
* **release** — `host`, `database_network` (external PostgreSQL), mode-600
  `runtime_file` and `migration_file` containing only `PEOPLE_GATOR_API__*` lines
  (runtime role plus storage/auth; migration role only), and
  `"access_reviewed": true` confirming the access boundary below. Optional
  `project`, `backend_memory`.

## Operations

| Operation | pr | staging | release | Meaning |
| --- | --- | --- | --- | --- |
| `configure`, `migrate-config` | ✓ | ✓ | ✓ | Edit/validate the descriptor only |
| `preflight` | ✓ | ✓ | ✓ | Read-only: descriptor, private inputs, Docker/Compose, networks, installation |
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
| `infra-upgrade` | ✓ | ✓ | | Owner-only explicit shared-infrastructure upgrade |
| `migration-inspect` / `adopt` | ✓ | ✓ | | Existing-host transition (below) |

Exit codes: `0` success, `1` actionable failure, `2` invalid usage, `130` cancelled.
Failures name the selected path, the field or condition and a corrective
command, for example
`staging configuration: <path>; descriptor: missing, symlinked, wrong owner or not mode 600; run people-gator-deploy staging configure --config '<path>' --input <private-json>`.
Secret values and raw service output are never printed; failed service output is
kept in the environment's private `last-error.log`.

**Ownership and locks.** `install` writes `owned.json` in the environment state
and, for managed infrastructure, `infrastructure-owned.json`. Unowned existing
state or infrastructure is never adopted implicitly, and refusals happen before
any file is written. Operations take the environment's `environment.lock`, then
the shared infrastructure `controller.lock` — shared for environment work,
exclusive for `install`/`infra-upgrade`/`adopt` and for legacy controllers, which
lock the same inode. A long staging refresh therefore does not block previews.
Operations journal `operation.json`; success state is written only after routed
readiness. Cancellation (SIGTERM/Ctrl-C) removes the operation's own containers.

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
changing images never undoes migrations and nothing downgrades a schema.

**Release access boundary.** The production stack has no reload, debug, seed or
development mounts, but the current frontend build embeds demo auto-login
credentials ([DEPLOYMENT.md](../../docs/DEPLOYMENT.md)). Browser-bundled
credentials are not private authentication: place the release behind a
reviewed access boundary (for example, proxy authentication or a private
network) before setting `access_reviewed`.

## CI/CD

Workflows check out their own reviewed commit (`github.workflow_sha`, never a PR
head), run `deploy/install.py --user --revision "$GITHUB_WORKFLOW_SHA"` (reusing a
matching install, publishing `executable` to `$GITHUB_OUTPUT`), run
`<env> preflight`, then one lifecycle operation with that pinned executable.
In CI the installer only accepts the default-branch `pr-preview.yml`,
`staging.yml` and `release.yml`, plus `release.yml` at a `v*` tag whose commit
is already on `main`. Missing configuration fails the job with the remedy; CI
never prompts, guesses setup or uses sudo. Each runner account needs its own
configured descriptors.

## Migrate an existing host

Hosts running the legacy `deploy/preview` controller bundles keep their paths,
data, credentials and `controller.lock`:

1. Install the utility as the runner account. Write descriptors with the same
   values as `/opt/people-gator-preview/config.json`: for **pr**,
   `state_dir` and `infrastructure.state_dir` both equal the legacy `state_dir`
   (`project: people-gator-preview-infra`, `mode: managed`); for **staging**, the
   legacy `staging.state_dir`/`private_dir`/`host` with `mode: external`.
2. `people-gator-deploy pr migration-inspect --legacy-config /opt/people-gator-preview/config.json`
   prints the mapping and every mismatch; nothing changes.
3. Disable the lifecycle workflows, let running jobs finish, back up the private
   config/state and database, and record that in a mode-600 file.
4. `people-gator-deploy pr adopt --legacy-config … --backup-record <file>` (then
   `staging`) writes ownership markers only: no paths move, no service restarts.
5. Re-enable the workflows from the reviewed `main`. Keep
   `/var/lib/people-gator-preview-controller/releases` until no job or container
   mount uses an old bundle; old workflow reruns still execute their own commit.

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
