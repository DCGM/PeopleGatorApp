# PostgreSQL backup operations

The backup worker is independent of API settings and application file storage.
It receives an explicit private JSON configuration with database connection
settings and a dedicated S3 publisher identity for `peoplegator-db-backup`.
The API never needs that identity. The staging application's separate bucket is
`peoplegator-staging`; a third, read-only backup identity is for restore workers.

## Publish a backup

Build from the repository root:

```sh
docker build -f deploy/backup/Dockerfile -t people-gator-backup .
```

Privately copy `publisher.example.json`, chmod it to 600 and replace all
placeholders. Set the actual source application's full Git revision, database
host/name/user/password/port, explicit sslmode and explicit HTTPS S3 endpoint,
region, bucket, prefix and publisher credentials. No `.env`, application settings,
ambient AWS credentials or instance profile supplies missing configuration.
Choose `verify-full` for remote production connections: it explicitly sets
`sslrootcert: system` by default to use libpq 16's system trust support. For a
private CA, set `sslrootcert` to an absolute path and mount that CA read-only into
the worker at the same path. Ambient `PGSSLROOTCERT` is ignored. `verify-ca`
requires an explicit CA path. A local unencrypted
Compose database requires explicit `sslmode: disable`.

Run the worker on the source database's network, passing configuration through
stdin so private host file ownership need not match the container UID:

```sh
docker run --rm -i --read-only --cap-drop ALL --security-opt no-new-privileges \
  --network people-gator-live-preview_default \
  --tmpfs /tmp:size=2g,mode=1777 --log-driver none \
  people-gator-backup publish --config - < /private/publisher.json
```

Choose temporary storage capacity for the full compressed archive plus overhead.
The worker runs without a Docker socket, application storage or shared volumes.
Native use needs PostgreSQL **16** client tools and the API's locked dependencies:
`python -m people_gator_api.backup publish --config /private/publisher.json`.

The database identity must read all required tables/sequences and schema metadata;
grant read-only database access for backups (including future objects) rather than
using the API's application-storage credentials. `pg_dump` takes a consistent
logical snapshot while normal writes continue. It retains migration history,
models, vectors and links; cluster roles and application media are not archived.
A complete recovery also needs a matching independent backup of media and auth
objects. See [PostgreSQL 16 pg_dump](https://www.postgresql.org/docs/16/app-pgdump.html).

## Publication contract and failure behavior

UTC date at operation start determines
`production/db-backups/peoplegator-prod-YYYY-MM-DD.dump` (prefix configurable).
Archives are PostgreSQL custom format and must pass `pg_restore --list` before
upload. Metadata contains `sha256` and the configured `application-revision`.
Private temporary archives/passfiles are removed on ordinary success or failure;
commands time out after one hour without relaying stderr or data to public logs.

The final dated object is created with `If-None-Match: *`, using PUT for small
files or conditional multipart completion for larger files. There is no overwrite
or nonconditional fallback. Providers must support these preconditions; configure
bucket policies to enforce them and retain dated archives immutably. Concurrent
publishers cannot replace an existing date. See
[S3 conditional writes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html).
An existing dated key fails the one-shot command. Inspect a failed verification
or ambiguous network response before retrying: the final key may already exist.
The worker never deletes a final object on failure. An incomplete multipart upload
is aborted on ordinary failure. Configure provider lifecycle cleanup of incomplete
uploads for process/host crashes, which cannot run cleanup code.
Uploads use at most a 64 MiB part buffer and 10,000 parts (625 GiB per archive);
larger archives need a reviewed worker limit change or physical backup tooling.

Metadata header names are read without case sensitivity, including providers
returning `Sha256` or `Application-Revision`. Checksum and revision values remain
exact, and conflicting duplicate names fail verification. If an older worker
reports a metadata verification failure after upload, inspect/verify that dated
archive with the updated worker; do not overwrite or republish the same dated key
to change metadata casing. Publisher, scheduled existing-object checks and both
restore download paths use this behavior.

Publisher permissions: prefix-scoped ListBucket, GetObject (HEAD verification),
PutObject, AbortMultipartUpload. No bucket creation, final-object deletion or
application-bucket access is required. Private configuration and dumps must stay
outside Git, public CI artifacts and general application logs. Unit and disposable
roundtrip checks are described in the implementation PR; no real dataset is used
in automated checks.

## Restore original data into a new database

Copy `restore.example.json` privately (mode 600). `storage` uses the **restore
reader** identity, with prefix-scoped ListBucket, GetObject and GetObjectVersion
only. `database` is a separate provisioning connection to a maintenance database.
`target` names a new database and an existing restricted LOGIN owner with its own
password. The owner must have no superuser, database/role creation, replication,
bypass-RLS or role-membership privileges. Provision that dedicated owner first;
this command never copies source roles or grants the app provisioning credentials.

With native PostgreSQL 16 tools and backend dependencies, run:

```sh
mkdir -m 700 /private/recovery-reports
python -m people_gator_api.backup restore --config /private/restore.json \
  --report /private/recovery-reports/recovery-2026-10-16.json
```

Optionally pass `--exact-key production/db-backups/peoplegator-prod-YYYY-MM-DD.dump`.
Without it, all listing pages are checked and the greatest valid filename date
is selected. Temporary/unrelated/invalid names are ignored. The selected key's
ETag, available version, size and publisher SHA256/revision metadata are pinned.
Download is conditional and streamed; identity/metadata are checked again after
download. Missing metadata, truncation, checksum mismatch, changed objects or a
corrupt latest archive fail before database creation. There is no older fallback.

The worker image supports the same `restore` command and stdin config. Mount a
private mode-700 report directory at a writable path, owned by the container's
effective UID, and pass `--report` inside it. For rootless Docker the host runner
maps to container UID 0: use `--user 0:0` with all capabilities dropped; for
rootful Docker match the private directory owner's UID/GID. Supply a writable
temporary mount with space for the archive. Neither backup nor provisioning
credentials belong in the API, frontend, process arguments or public logs.

The provisioning identity must create/drop databases, assign ownership to the
target owner, and install the application's compatible `vector`, `pg_trgm` and
`unaccent` extensions. The target starts with public CONNECT revoked. Extension
installation uses provisioning credentials; archive SQL authenticates directly
as the restricted owner, with a separate passfile. Restore is transactional and
ignores source owners, grants, comments and security labels. It preserves data,
links, vector values and Alembic history exactly: no sanitization, seeding,
migration or stamping. It requires a valid restored Alembic revision. Use only
trusted application archives: restoring SQL is not a sandbox. See
[PostgreSQL 16 pg_restore](https://www.postgresql.org/docs/16/app-pgrestore.html).

Existing target databases and existing report files are refused. The report is
reserved exclusively before side effects, written mode 600 and contains source
identity/checksum/revisions and destination identity, without credentials. An
ordinary setup/restore/report failure drops only the database this operation
confirmed creating; source/active databases are untouched. If cleanup fails or
the process/host dies, a partial unserved target/report can remain for operator
inspection. A network failure during CREATE DATABASE has an uncertain result;
the tool cannot safely assume ownership and never drops an unconfirmed target.
Inspect and explicitly remove only that failed candidate before retrying. No
automatic connection/routing switch or destructive in-place recovery is provided.
Before adopting the recovered database, run the compatible application's schema
checks/migrations and validate matching media/auth storage and writable behavior.

## Two buckets and three storage identities

Provision the buckets privately through the provider before enabling the agent.
Keep the account grants separate:

| Identity | Bucket | Operations | Private host configuration |
| --- | --- | --- | --- |
| Backup publisher | `peoplegator-db-backup` | Prefix list/read/write and incomplete multipart abort; no final deletes | `/opt/people-gator-staging/backup-publisher.json` |
| Restore reader | `peoplegator-db-backup` | Prefix list/read/version-read only | `/opt/people-gator-staging/backup-restore.json` |
| Staging application | `peoplegator-staging` | List/read/write/delete, no backup bucket access | `/opt/people-gator-staging/storage.json` |

The three `*-policy.example.json` files are S3 IAM identity-policy examples for
these grants. Change the backup prefix consistently in configuration and policies.
Attach each policy only to its corresponding identity; remove unrelated broader
policies, block anonymous access and enforce conditional backup creation. Providers
with different policy dialects need equivalent bucket/prefix/operation restrictions.
These files do not create buckets/accounts or apply provider policy automatically.

Copy the publisher/restore JSON examples into those private paths, mode 600 in
the runner's mode-700 directory, and supply independent credentials. The restore
file also needs explicit database provisioning/target-owner connection settings.
The app's `storage.json` uses the shape of
[`staging.storage.example.json`](../preview/staging.storage.example.json),
with `local: null` and only the staging identity. Do not put backup credentials
in root `.env`: live-preview's API imports that entire file. No operation inherits
the app's storage settings or AWS credentials.

For later staging initialization, create the controller's private
`backup-source.json` from the restore file's **storage section only**, using
[`staging.backup-source.example.json`](../preview/staging.backup-source.example.json).
That download-only input must not contain database provisioning credentials. Its
bucket is now `peoplegator-db-backup`; the staging destination remains
`peoplegator-staging`. The database loader restores original data. Staging's current
classification/sanitization/activation flow is a separate follow-up in #16; this
change does not claim to make that flow preserve an unmodified production dataset.

## Enable scheduled live-preview backups

The agent is a separate service in the live-preview deployment. This keeps
publisher/database-reader credentials out of the API container. The overlay has
no project name, no `env_file`, no Docker socket and no application file-storage
mount. Run from the repository root, with the existing source deployment/network
already available and the private publisher config provisioned:

```sh
docker compose -f compose.live-preview.yaml -f deploy/backup/compose.agent.yaml \
  --profile backups up -d --no-deps --build backup-agent
```

Only the named agent service starts; this does not rebuild/restart the source API,
frontend or database. The `backups` profile is opt-in and the base live-preview
file is unchanged. Nonsecret settings may be exported before the command:
`BACKUP_PUBLISHER_CONFIG`, `BACKUP_DATABASE_NETWORK`, `BACKUP_AT_UTC` (default
`02:00`), `BACKUP_RETRY_SECONDS` (300), `BACKUP_TEMP_SIZE` (`2g`),
`BACKUP_WORKER_IMAGE`, `BACKUP_RUN_UID` and `BACKUP_RUN_GID`.

The network defaults to `people-gator-live-preview_default`; it must reach both
the configured source database and HTTPS backup endpoint. The source database
itself is not attached to another network. The default worker UID/GID 0 maps to
the runner on the documented rootless Docker host, allowing a mode-600 config
file. On rootful Docker either provision root-owned mode-600 config for UID 0,
or use matching UID/GID and explicitly prepare ownership of the agent state
volume. Never make credentials group/world-readable to work around ownership.
The worker has all capabilities dropped, a read-only filesystem and only a
bounded temporary mount plus its separate persistent lock volume.

Scheduling is daily in UTC. Startup before the due time waits; startup after it
catches up. Failures retry with fixed safe logs and the configured delay. A valid
existing dated object is recognized only after checking length and publisher
metadata; a corrupt/foreign dated object requires operator inspection and is
never overwritten. That metadata check relies on the publisher's atomic immutable
object contract; it is not a full archive restore/checksum download. Finishing a
backup after midnight retains its start date and does not skip the next day's
schedule. Source `application_revision` must be updated with source deployments;
it is operator-supplied provenance, not inferred from a possibly newer worker.

The scheduler holds a nonblocking lock at `/state/agent/controller.lock`. To run
one manual backup using the same lock and service configuration, stop the agent,
run the one-shot command, then restart it (using the same Compose arguments):

```sh
docker compose -f compose.live-preview.yaml -f deploy/backup/compose.agent.yaml --profile backups stop backup-agent
docker compose -f compose.live-preview.yaml -f deploy/backup/compose.agent.yaml --profile backups run --rm --no-deps backup-agent \
  publish --config /run/backup-publisher.json --lock-file /state/agent/controller.lock
docker compose -f compose.live-preview.yaml -f deploy/backup/compose.agent.yaml --profile backups up -d --no-deps backup-agent
```

An already running agent refuses a competing manual command using this lock.
Conditional final-key publication also prevents overwrite by another host that
cannot share the volume. A lock prevents duplicate work; it is not the S3
immutability mechanism. Retain this state volume for the same deployment.

Native schedulers reload the explicit private file on each attempt. Docker file
bind mounts pin the mounted inode: after atomic host config/credential replacement,
recreate only the agent with `up -d --no-deps --force-recreate backup-agent` using
the same Compose arguments. Keep the previous credential valid until recreation.
The API and restore process need no restart when the publisher identity rotates.

## Production deployment and validation

The same image and service work in a production deployment with independently
provisioned database-reader/publisher credentials and its explicit source network.
There is no existing production Compose stack in this repository to install into.
After reviewing source connectivity, bucket policy and capacity, an operator can
use the agent file standalone from the repository root:

```sh
docker compose --project-directory . -p people-gator-production-backup \
  -f deploy/backup/compose.agent.yaml --profile backups up -d --build backup-agent
```

Set the nonsecret overrides above to production's private file path, network and
desired UTC schedule. `--project-directory .` makes the root build context correct
for standalone use. This service continuously schedules backups; production
installation is not performed automatically by PR code or GitHub preview jobs.
Verify one manual publication and a full restore into a separate database before
relying on it for recovery. No retention deletion, PITR/WAL backup or automatic
database replacement is included.

Run the backend's `tests/backup` suite for scheduling/retry/lock/credential tests.
Build the worker and set `BACKUP_TEST_IMAGE` when running
`deploy/backup/tests/test_roundtrip.py` with the backend Python interpreter. It
uses only disposable synthetic PostgreSQL16/pgvector and TLS S3 containers,
including a real scheduled Compose agent; no operator private files are read.
