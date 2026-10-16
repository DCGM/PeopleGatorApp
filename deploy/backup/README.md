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
