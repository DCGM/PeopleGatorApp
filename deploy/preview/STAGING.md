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
The default bucket is `peoplegator-ingest`, prefix `production/db-backups/`.
Change the leading prefix for the real bucket layout as necessary. This layout
is a contract, **not evidence that a production backup already exists**.

The publisher creates consistent PostgreSQL custom-format `pg_dump -Fc` archives
named exactly `peoplegator-prod-YYYY-MM-DD.dump`, e.g.
`s3://peoplegator-ingest/production/db-backups/peoplegator-prod-2026-10-15.dump`.
Use UTC dates. Complete uploads under a temporary nonmatching key or as an
uncompleted multipart upload; publish the final matching key only when complete.
Published dated backups are immutable. Retain data, model registrations/vectors,
relationships and Alembic history. Do not include cluster roles. Publish SHA-256
in object metadata `sha256` and source Git SHA in `application-revision`.
Backup creation/scheduling is a separate production operator responsibility;
staging never connects to the live production database to create a dump.

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

The auth volume defaults to `people-gator-staging-auth` (optional private config
`auth_volume`, restricted to a `people-gator-staging-*` name). Its mode-700
`peoplegator_api` directory holds mode-600 `users.json`, `api-keys.json` and
`jwks.json`, owned by container UID/GID **10001:10001**. It is mounted read-only
in the running backend at `/data/peoplegator_api`, separate from the media volume.
`JWK__USERS_PATH`, `API_KEYS__KEYS_PATH`, `JWK__KEY_PATH` explicitly select these
files. Neither frontend nor media routes mount or serve this directory. Distinct
ES256 signing keys are generated once; issuer is `https://staging.peoplegator.dev`,
audience `staging.peoplegator.dev`, CORS is restricted to that HTTPS origin.
Production tokens and unconfigured production API secrets cannot authenticate.

Credential file replacements are atomic and retain UID/GID 10001 before publication.
Explicit initialization adds missing example users without resetting existing
hashes/scopes. The API-key file is initialized **only if absent**, so removing a
key stays revoked across repeated refreshes even if it remains in the input
file. Add/rotate/revoke later keys by editing the staging-owned file privately
under the host lock (or replace it from a private backup). Do not delete/recreate
the auth volume. Changing supplied defaults does not rotate an existing account
or signing key. API-key identifiers should start with `staging-`, belong to a
staging user and carry explicit scopes; first authenticated use registers the
associated user/key through the application's repository contracts. Historical
production actors/key IDs retain attribution FKs but receive inactive,
unmatchable historical identities with no production credentials.

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
backup prefix/credentials. Only explicit preparation mounts source readers.
Canonical source scan keys are copied individually into a **new staging volume**;
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
  Other pages get blank local JPEGs and lose image occurrences/faces/vectors
  through FK cascades. Their text annotations remain linked but redacted.
  Model registrations/dimensions remain; retained vectors are unchanged.
  Geometry is reduced to validated numeric boxes/keypoints and checked against
  imported image bounds. Redacted pages never expose old originals/derivatives.
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
`people-gator-staging-<16-hex>-media`, with a fresh random password. Database CONNECT
is revoked from PUBLIC **before enabling connections**. PR roles have no access.
Preparation is unserved: private download → archive validation → restricted-role
restore → sanitize/import → auth initialization → candidate migration/data checks
→ runtime-configured full check → API lifespan/health → frontend/HTTPS readiness.
The stable Compose project `people-gator-staging` switches database and media in
the same configuration. Authentication is a separate retained volume. Upload,
replacement, deletion, derived media, entity merges and annotations use staging
credentials/volumes exclusively. PR cleanup only handles `pr-N` directories,
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
work directories. Failed/previous generation databases and volumes are retained
for inspection/recovery, never automatically garbage-collected. Under the shared
host lock, confirm the active and previous manifests, back up what is needed,
then remove only named unused staging generations/work directories. Never run
broad Docker volume prune or remove the auth volume. This retention costs disk.

For backup/recovery, take a consistent private custom-format dump of the active
generation with its configured role, stop writes while archiving its media and
**separately** archive the auth volume (contains signing keys/hashes) plus state
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
retains staging edits. No production dump is used by CI.

For candidate-image/lifespan checks, build the backend Dockerfile locally and set
`STAGING_TEST_IMAGE`, `STAGING_TEST_POSTGRES_CONTAINER`, `STAGING_TEST_NETWORK`,
`STAGING_TEST_DATABASE_PORT` (and optional `STAGING_TEST_DATABASE_USER/PASSWORD`).
Use a **dedicated disposable** pgvector/PG16 container/network with alias
`preview-postgres`, then run `test_staging_runtime.py` with the backend venv.
It restores/sanitizes through the actual worker, migrates/checks through the same
image/runtime role, rejects stale revision/schema drift/wrong database, and checks
healthy startup and invalid-revision rejection on restart. It creates/drops test
stores/volumes; never point it at shared preview, staging or production.

Real S3-provider access, production classification/snapshot preparation, DNS/TLS,
main workflow scheduling and real HTTPS writable smoke checks require the private
operator inputs and a merged reviewed revision. Local synthetic passes do not
establish those live outcomes. The PR preview's automatic seed and its contracts
are unchanged; this explicit administrative snapshot path does not seed staging.
