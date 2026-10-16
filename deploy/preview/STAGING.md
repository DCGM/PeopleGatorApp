# Main staging on the preview host

`staging.yml` deploys successful **push-to-main** runs of `PR CI`, using their
frontend/backend images. PR CI tests and builds the exact main SHA (not a PR
head). It uses random published PostgreSQL test ports so the three runner
processes can test different revisions concurrently. Images are pulled, their
OCI revision checked, and their repository digests pinned before any migration.
The same backend digest migrates, checks and runs the API.

A normal deployment never lists backups, restores, seeds or provisions accounts.
It migrates the retained staging database, validates linked/vector data, prepares
the backend configuration, performs a full runtime-role `check`, starts the API
with `schema_mode=validate`, waits for backend health, starts the frontend, then
checks HTTPS API health, frontend health and HTML. API lifespan independently
validates schema **and migration revision on every startup/restart**. Success
state and Actions summaries are written only after readiness succeeds.

## One-time operator setup

Use the existing host and its rootless Docker context. Keep all existing runner
labels and services. GitHub runner registrations `pcvaskom-1` (3), `pcvaskom-2`
(4), `pcvaskom-3` (5) already have `people-gator-staging`; verified through the
GitHub API during implementation. For replacements register with all applicable
labels `people-gator-ci,people-gator-preview,people-gator-staging`, then verify
through `GET /repos/DCGM/PeopleGatorApp/actions/runners`. Add labels using
`POST /repos/DCGM/PeopleGatorApp/actions/runners/{id}/labels` rather than replacing
the label set or editing local registration files. This needs runner-management
operator permissions; deployment tokens need only repository contents, Actions,
PR and packages read. CI image publication additionally needs packages write.

1. Provision **separate DNS** for `staging.peoplegator.dev` to this host. The
   wildcard `*.preview.peoplegator.dev` does not cover staging. Use the existing
   Traefik `web` network, `websecure` entrypoint and `tlschallenge` resolver.
   DNS/TLS setup must not reset shared Traefik, PostgreSQL or existing previews.
2. Keep the [preview infrastructure/release prerequisites](README.md) in place.
   Operator initialization/upgrades remain explicit. The staging workflow never
   runs `preview.py init`. For staging log metadata, explicitly apply the reviewed
   `otel-collector.yaml` update to the shared collector, under the host lock,
   following the preview infrastructure upgrade procedure. Existing PR metadata
   is retained; staging records use `deployment.environment.name=staging`,
   `service.name=people-gator-staging.<service>` and the staging SHA.
3. Create runner-owned mode-700 directories `/var/lib/people-gator-staging` and
   `/opt/people-gator-staging`. Add just the `staging` object from
   `config.example.json` to private `/opt/people-gator-preview/config.json`.
   Preserve every existing setting and infrastructure password. Keep the state
   directory outside preview state and private inputs outside state/releases.
4. Place the private inputs described below in `/opt/people-gator-staging`, mode
   600, readable by the runner. Templates contain placeholders, never usable
   credentials. Do not place private inputs in Git, release bundles, media,
   Actions variables/output, or uploaded artifacts. Store private backups on
   encrypted operator storage and restrict host/runner access accordingly.
5. After merge, wait for a successful main CI build and invoke **Main staging
   deployment → Run workflow → main → refresh**. An uninitialized normal deploy
   deliberately fails. Verify classification, login, permitted media, entity
   links, vector queries and writable operations before admitting staging users.

Workflow publication accepts only the exact reviewed `main` workflow revision
for `pr-preview.yml` or `staging.yml`. A PR/non-main workflow cannot publish a
controller. Staging deployment/refresh jobs select
`[self-hosted, linux, x64, people-gator-staging]`; CI/preview selectors are
unchanged. Both lifecycle workflows share `people-gator-preview-host` concurrency
and the **same preview-state `controller.lock` inode** (also used manually).
A label alone cannot serialize three runner processes. Do not move that lock,
use independent lock files, or run manual host mutations outside it. Snapshot
preparation currently holds this lock throughout, so large transfers delay PR
lifecycle jobs; account for the 120-minute job/operation limit.

## Backup publisher and source

Copy `staging.backup-source.example.json` privately to `backup-source.json`.
Configure the provider's explicit HTTPS S3-compatible endpoint/region and
dedicated read-only credentials. No AWS-default endpoint, instance-profile or
production runtime credentials are inherited. Grant listing only for the
configured prefix and `GetObject`/`GetObjectVersion` there; no put/delete rights.
The default bucket is `peoplegator-db-backup`, prefix `production/db-backups/`.
Change the leading prefix for the real bucket layout as necessary. This layout
is a contract, **not evidence that a production backup already exists**.

The publisher creates consistent PostgreSQL custom-format `pg_dump -Fc` archives
named exactly `peoplegator-prod-YYYY-MM-DD.dump`, e.g.
`s3://peoplegator-db-backup/production/db-backups/peoplegator-prod-2026-10-15.dump`.
Use UTC dates. Complete uploads under a temporary nonmatching key or as an
uncompleted multipart upload; publish the final matching key only when complete.
Published dated backups are immutable. Retain data, model registrations/vectors,
relationships and Alembic history. Do not include cluster roles. Publish SHA-256
in object metadata `sha256` and source Git SHA in `application-revision`.
The [backup worker](../backup/README.md) creates, validates and publishes this
format, with opt-in live-preview scheduling and a reusable production service.
Provision its publisher identity independently from the restore reader and the
staging application identity. The operator installs/enables the source scheduler;
staging never connects to the live production database to create a dump.

The current bucket split is `peoplegator-db-backup` for archives and
`peoplegator-staging` for application files. Private publisher and restore configs
may live in `/opt/people-gator-staging/backup-publisher.json` and
`backup-restore.json`; only the restore storage section belongs in the staging
controller's download-only `backup-source.json`. Existing private files with an
explicit different source bucket retain that setting until the operator changes
it. Never replace an active staging destination to adopt a new default: retained
destination identity checks still require an explicit data migration.

The restore environment uses PostgreSQL **16** tools from shared
`pgvector/pgvector:pg16`. Supply pg_dump 16 archives from PostgreSQL 16 with the
same compatible pgvector extension version as that service. Higher-major dump
archives require a reviewed explicit tool/infrastructure upgrade; never change
shared infrastructure automatically. `pg_restore --list`, a full transactional
restore and candidate migration/schema/vector checks validate the archive.
Restore ignores production owners, grants, comments and security labels, uses a
new restricted staging-owned role and preserves source Alembic history; it never
stamps/bootstrap-adopts a snapshot to bypass migrations.

Refresh lists **all pages**, filters exact prefix/filename/calendar dates, then
selects the greatest filename date, irrespective of listing/upload order. An
exact-key override must still match this prefix and filename contract. It pins
the key, version ID when present, ETag, size and SHA-256 before restore; conditional
download and a post-download HEAD reject changed/disappeared objects. Complete
length, simple-upload MD5 when applicable, publisher SHA-256 and archive restore
checks protect integrity. Newer objects arriving during an operation do not
change its selection. Missing/denied listing/download, no matching backup or a
corrupt latest archive fails; **there is no older-backup fallback**. Retry of an
explicit operation starts fresh; pass its recorded exact key for reproducibility.

## Required S3 storage

Staging uses **one dedicated staging-owned S3-compatible bucket** for every
application file: scans, OCR, other images, caches, users, API keys and signing
keys. PostgreSQL remains a separate service for relational data and vectors.
There is no local file-storage option, `/data` mount, media/auth Docker volume,
`storage-init` service or local fallback in staging. PR preview storage is unchanged.

Copy `staging.storage.example.json` to private `storage.json`. Set `local` to
JSON `null` and supply the complete `s3` object: explicit HTTPS `endpoint_url`,
`region`, `bucket_name`, `access_key_id`, `secret_access_key` and optional positive
`timeout_seconds`. The controller rejects missing/local/mixed configurations;
the preparation worker independently requires the S3 backend. Runtime and
preparation select the same S3 settings through `PEOPLE_GATOR_API__STORAGE`.
Controller release publication also rejects local staging services/volumes or
backend, migration and check services configured for different buckets.
Never place these credentials in frontend variables or commit the private file.

Provision the bucket explicitly before the first refresh. Use a private bucket,
block anonymous/public reads, and grant the staging principal only this bucket's
required listing/read/write/delete operations. It must have no production or PR
bucket permissions. One bucket contains these distinct key namespaces:

| Keys | Lifecycle |
| --- | --- |
| `peoplegator_api/users.json` | Stable staging users and password hashes |
| `peoplegator_api/api-keys.json` | Stable API-key hashes, owners and scopes |
| `peoplegator_api/jwks.json` | Stable independent ES256 signing keys |
| `generations/<16-hex>/images/ndk/...` | Snapshot's permitted or redacted scans |
| `generations/<16-hex>/page-layouts/...` | Redacted OCR layouts |
| `generations/<16-hex>/images/...` | Other generation media |
| `generations/<16-hex>/cache/page-images/...` | Resized scans |
| `generations/<16-hex>/cache/aligned-face-crops/...` | Aligned face crops |

The configured media helpers apply generation prefixes; canonical document/page
identities remain unchanged. Authentication keys stay outside those media prefixes
and are never served by media routes or mounted in the frontend. The bucket is
not an HTTP static website. Only the backend/preparation workers receive its
private S3 credentials. Every refresh writes a fresh media/cache prefix and
switches that prefix together with the database after validation. Failed
preparation never writes the active prefix or replaces existing credentials.

Backend, migration/check and S3 preparation containers join the configured `web`
network for outbound HTTPS. Preparation also joins the internal database network
when it needs PostgreSQL. PostgreSQL itself stays on its existing internal
network. Ensure Docker DNS and outbound connectivity reach the configured S3
endpoints; an internal-only network cannot download/import S3 objects.

The successful state records endpoint/region/bucket identity. Changing that
identity or supplying legacy local-volume state is rejected before migration or
replacement. Credential rotation within the same bucket is supported through
private `storage.json`; retain access for active containers until redeployment.
Moving buckets or adopting an older local deployment requires an explicit
operator migration of credentials, active media and state under the host lock;
the controller does not silently switch to an empty bucket or convert local data.

### Update an existing host's settings

Run the configuration helper **as the existing deployment runner user**, from
this checkout or a reviewed controller release. The preview host config and its
runner-owned state directory must already exist. The one-time directory setup
above still applies if `/opt` or `/var/lib` cannot be written by that user.

```sh
python3 deploy/preview/configure_staging.py
```

It reads `/opt/people-gator-preview/config.json`, preserves unrelated host and
staging settings, adds missing staging defaults and removes the obsolete
`auth_volume` setting. Prompts collect endpoint, region, bucket and credentials;
both credential fields use hidden input. Enter preserves an existing value.
Only `storage.json` and the staging config stanza can change. Backup/media
reader inputs, account hashes, active database/media, journals and credential
objects in S3 are left untouched. It makes no network calls and does not verify
provider connectivity or create the bucket.

For automation, provide a complete private JSON storage configuration using the
`staging.storage.example.json` shape. Secrets must stay in that private file,
never in command arguments. Optional `--config` selects a different host config:

```sh
python3 deploy/preview/configure_staging.py \
  --config /opt/people-gator-preview/config.json \
  --storage-file /private/staging-storage.json --dry-run
```

Remove `--dry-run` to apply. A dry run writes no files or directories. Apply
takes the same preview host lock as deployments, detects concurrent edits,
creates mode-600 `*.bak-<UTC timestamp>-<suffix>` backups of changed files,
and atomically replaces settings with mode-600 files in mode-700 staging
directories. Ordinary write failures restore already-replaced settings. Reruns
with the same settings retain file contents and create no additional backups.
Backups contain credentials and must remain private; retain them for recovery.

For active S3 staging, endpoint/region/bucket must match committed `state.json`;
credential rotation within that destination is allowed. Pending activation and
legacy local-volume state block updates so they cannot silently redirect an
existing dataset. Resolve activation or perform a deliberate data migration
first. The script does not reset state, move data or publish controller releases.

After applying, it prints the appropriate `gh workflow run staging.yml --ref main`
command: `operation=deploy` for initialized staging or explicit `operation=refresh`
for first initialization. Run that separately once the reviewed change is on
`main` and the required private inputs/bucket are provisioned. Existing containers
keep their old credentials until redeployment; retain those credentials during
rotation until the new deployment passes readiness.

## Private account and API-key provisioning

Copy `staging.credentials.example.json` to private `credential-input.json` and
replace hashes using privately generated **unique staging** passwords/API secrets.
Never reuse production passwords/secrets, copy production users/JWKS, or put
secrets in `VITE_*` variables (those are public browser code). Generate Argon2id
hashes using `argon2.PasswordHasher().hash(getpass.getpass())` with the backend
venv, writing hashes directly to the private file rather than terminal/history.
The raw passwords/API secrets belong in your private credential distribution
channel, not the repository or CI logs.

| Account | Existing scopes |
| --- | --- |
| `staging-viewer` | `people-gator:browse` |
| `staging-annotator` | browse + `people-gator:annotate` |
| `staging-importer` | browse + `people-gator:ingest` |
| `staging-admin` | browse + annotate + ingest + `people-gator:admin` |

The three authentication objects live at the stable `peoplegator_api/` keys in
that same staging bucket. `JWK__USERS_PATH`, `API_KEYS__KEYS_PATH` and
`JWK__KEY_PATH` explicitly select them. Distinct ES256 signing keys are generated
once; issuer is `https://staging.peoplegator.dev`, audience is
`staging.peoplegator.dev`, and CORS is restricted to that HTTPS origin.
Production tokens and unconfigured production API secrets cannot authenticate.

Credential changes use complete atomic S3 object PUTs. Explicit initialization
adds missing example users without resetting existing hashes/scopes. The API-key
object is initialized **only if absent**, so removing a key stays revoked across
refreshes even if it remains in the input file. Add/rotate/revoke later keys by
privately replacing that bucket object under the host lock (or restore a private
versioned backup). Do not delete the credential objects to refresh the dataset.
Changing supplied defaults does not rotate an existing account or signing key.
API-key identifiers should start with `staging-`, belong to a staging user and
carry explicit scopes. First authenticated use registers associated actors
through application repository contracts. Historical production actors/key IDs
retain attribution FKs but receive inactive historical identities and no
production credentials. Input files are sent to operation-scoped workers through
stdin, never mounted in the running API or included in public logs/artifacts.

Open **https://staging.peoplegator.dev/staging-login.html**, choose an example
account and sign in with its privately supplied password. This staging-only
static page uses the existing token endpoint and stores access/refresh tokens in
that browser tab's session storage, which the existing app already consumes.
The requested scopes match the selected account. It contains no default password
or injected credential. Expired sessions after an API restart may need sign-in
again because refresh sessions are process-local. To switch accounts revisit
that page; to sign out close the tab or clear its session storage. If operators
reduce an account's scopes, use `/docs` with those permitted scopes; the predefined
page requests the documented default set. The app's existing demo auto-login
fallback is not a staging credential and fails if there is no valid session.

## Media classification and transformations

Copy `staging.media-policy.example.json` to private `media-policy.json`.
`permitted_page_ids` contains **source/page record UUIDs** (`pg_demo_pages.id`),
not archive `page_id`s. An empty allowlist imports **no** production scans, faces
or vectors. To retain a representative real vector graph, the operator must
explicitly permit the associated page pixels, face geometry and biometric
vectors for all staging users with browse scope. Staging does not implement
per-page access control: restrict host/network/accounts to the permitted dataset.

When any pages are allowed, separately configure private `media-source.json`
from `staging.media-source.example.json`. This is independent of the database
backup prefix/credentials. Only explicit preparation receives source readers.
`prefix` selects an optional source root and `page_image_prefix` defaults to
`images/ndk`; neither inherits the candidate generation prefix. Canonical source
scan keys are copied individually into a **new generation prefix in the staging bucket**;
no recursive bucket copy, production mount or read-through fallback exists.
A missing permitted image fails preparation. Removing production assets after
copy cannot break the independent copy. Account/credential paths can never be
selected by the importer. Source JPEG EXIF/comments are removed on re-encoding.
Existing derivatives are not copied; staging creates its own on demand.

Reviewed sanitization is deliberately conservative:

- Preserve entity/source/annotation UUIDs and attribution/verification FKs;
  pseudonymize user identity/email, entity names/descriptions/authority IDs,
  aliases, document names, library metadata, face identifiers and API-key labels.
  Unknown entity types are cleared. Non-page URLs become nonresolving `.invalid`
  placeholders; canonical page/document URLs use pseudonymous library names.
- All mention text becomes a redacted placeholder and contexts are cleared.
  All OCR layouts become valid empty layouts; private text never enters media.
- Only explicitly permitted pages retain pixels and their face/vector graph.
  Other pages get blank JPEGs in the staging bucket and lose image occurrences/faces/vectors
  through FK cascades. Their text annotations remain linked but redacted.
  Model registrations/dimensions remain; retained vectors are unchanged.
  Geometry is reduced to validated numeric boxes/keypoints and checked against
  imported image bounds. Face landmark labels retain their original coordinate
  mapping in any input order; unknown or duplicate labels fail preparation.
  Redacted pages never expose old originals/derivatives.
- An explicit schema/routine/table/column classification rejects unknown schema objects
  rather than allowing newly introduced text/auth columns through. Extend this
  reviewed sanitizer before using a new source contract. Candidate migrations
  run after sanitization and must also pass full schema/revision validation.

These transformations trade original text/OCR search for preserving historical
relational shape and permitted embedding queries; this is **not synthetic
reconstruction**. Source dump application provenance, source migration revision,
object identity/checksums and policy checksum live privately in generation
`provenance.json`. No raw data or credentials enter Actions summaries.

## Refresh, activation, persistence and recovery

Run `gh workflow run staging.yml --ref main -f operation=refresh`; optionally pass
`-f run_id=<successful-current-main-run>` and
`-f exact_key=production/db-backups/peoplegator-prod-YYYY-MM-DD.dump`.
This deliberately replaces staging-only database/media edits. Back up the active
pair and independent auth store first. Ordinary `operation=deploy`, main events,
retries and PR reconciliation never refresh. After runner downtime manually run
`operation=deploy` to deploy the latest successful current-main build. Stale
SHA/attempts are rejected before migration and again before application replacement;
an older run cannot overwrite a newer attempted build.

Each refresh uses `staging_<16-hex>` database/login and
`generations/<16-hex>/` in the configured staging bucket, with a fresh random
database password. Database CONNECT
is revoked from PUBLIC **before enabling connections**. PR roles have no access.
Preparation is unserved: private download → archive validation → restricted-role
restore → sanitize/import → auth initialization → candidate migration/data checks
→ runtime-configured full check → API lifespan/health → frontend/HTTPS readiness.
The stable Compose project `people-gator-staging` switches database and media in
the same configuration. Authentication uses stable keys in that same bucket.
Upload, replacement, deletion, derived media, entity merges and annotations use
staging credentials and generation prefixes exclusively. PR cleanup only handles `pr-N` directories,
projects, volumes and `preview_pr_N` databases/roles; staging is outside that tree.

`state.json` is the successful activation commit point. `compose.env` records the
active pair; `previous.json`/`previous.env` preserve prior metadata/config.
`activation.json` journals replacement. If refresh startup/readiness fails, the
controller restores the old pair/config and checks it; preparation failure never
replaces active services. Abandoned labelled preparation workers are removed under the host lock before a retry.
If interrupted during refresh activation, the next
invocation recovers the journal before doing other work. If success was already
committed, recovery reconstructs `compose.env` from committed state. Allow a brief
routing interruption during replacement/recovery; this is not zero-downtime
blue/green routing. A failed rollback remains a failed operation with journal and
private diagnostics for operator recovery.

Normal deployment migrates the retained database **in place**, preserving edits.
A migration transaction failure blocks startup and successful reporting. A later
check/startup/readiness failure may leave an already upgraded schema; there is
**no automatic image downgrade**. Retry a current compatible candidate or use a
reviewed database+media backup recovery. A pending normal-deploy journal permits
another normal deploy but blocks refresh until resolved. Never assume an older
backend is compatible with an upgraded store. Candidate diagnostics are private
`last-error.log`, `generation-*/candidate.json`, `candidate.env`, `worker.env` and
provenance; do not upload or paste these into public CI/issues.

Reserve capacity for **active + preparation + retained previous database/media**,
a compressed dump and PostgreSQL restore/index/WAL overhead. Source transfer has
provider egress/API cost proportional to the archive and permitted scans. Raise
capacity/timeouts deliberately for large collections. Dumps are deleted when an
operation exits normally or fails; a killed process may leave `snapshot-*` private
work directories. Failed/previous generation databases and S3 prefixes are retained
for inspection/recovery, never automatically garbage-collected. Under the shared
host lock, confirm the active and previous manifests, back up what is needed,
then remove only named unused staging databases, generation prefixes and work
directories. Preserve `peoplegator_api/` and the active/previous generation
prefixes. This retention costs host disk and bucket storage/API operations.

For backup/recovery, take a consistent private custom-format dump of the active
generation with its configured role, stop writes while archiving its S3 media
prefix and **separately** back up `peoplegator_api/` (signing keys/hashes) plus state
and reviewed release revision. Store encrypted outside releases/CI. Restore a
matched pair privately and use a reviewed compatible image, full migration/check
and readiness sequence before activation. Explicit refresh replaces DB/media,
not auth; account/credential rotation and shared infrastructure upgrades remain
independent operator actions.

## Validation

Standard-library suites: `test_preview.py`, `test_installation.py`,
`test_observability.py`, `test_staging.py`, `test_snapshot.py` in `tests/`.
The backend CI job additionally runs snapshot integration with its backend venv,
random test port and a disposable PostgreSQL service. That suite seeds twice,
creates a real historical-revision synthetic `pg_dump -Fc`, restores it, sanitizes
sensitive sentinels, checks relationships/media/vectors, migrates/checks twice and
retains staging edits. A permitted seeded face uses reversed landmark order to
verify that sanitization preserves label/coordinate pairs; unknown and duplicate
labels must fail preparation. No production dump is used by CI.

For candidate-image/lifespan/S3 checks, build the backend Dockerfile and set
`STAGING_TEST_IMAGE`, `STAGING_TEST_POSTGRES_CONTAINER`, `STAGING_TEST_NETWORK`,
`STAGING_TEST_DATABASE_PORT` (and optional `STAGING_TEST_DATABASE_USER/PASSWORD`).
Use a **dedicated disposable** pgvector/PG16 container with alias
`preview-postgres` on an internal test network. The host-side seed fixture also
needs its own mapped port. Run `test_staging_runtime.py` with the backend venv;
Docker Compose and OpenSSL are required. The suite starts separate disposable
TLS MinIO source/staging providers with unrelated credentials, private buckets,
a test CA and an isolated egress network; no real provider inputs are read.

The actual worker downloads a pinned synthetic dump, restores/sanitizes it,
imports a permitted seeded scan with vectors, and provisions the three auth
objects into one staging bucket. The actual staging Compose runs repeated
migration/check, full startup and restart gates. API requests verify S3 login,
API keys, scan reads/replacement and both cache types after the source scan is
deleted. Failed
refresh, repeated auth provisioning, scope edits and key revocation preserve
active S3 objects/signing keys. Drift/revision failures remain independent gates.
Resources use unique test projects, databases, buckets and networks, with Traefik
disabled; never point tests at shared preview, staging or production services.

Real S3-provider access, production classification/snapshot preparation, DNS/TLS,
main workflow scheduling and real HTTPS writable smoke checks require the private
operator inputs and a merged reviewed revision. Local synthetic passes do not
establish those live outcomes. The PR preview's automatic seed and its contracts
are unchanged; this explicit administrative snapshot path does not seed staging.
