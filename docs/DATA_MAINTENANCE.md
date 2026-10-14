# Reviewed data audits and repairs

Use this runbook when investigating schema drift, missing media, questionable
assignments or processing metadata. The repository has migration/check/seed
commands, but no general-purpose production audit-and-repair CLI. Maintenance
scripts should be reviewed as issue changes, not improvised against retained data.

## Audit before repair

1. Identify the exact database, storage root/bucket, application revision and
   environment. Record the issue, affected IDs, expected invariant and impact.
   Keep credentials and private document content out of issue/CI output.
2. Take a consistent database backup and matching storage backup before a write.
   Preserve migration history, face-model registrations, JWT keys and credential
   files securely. Verify restoration in an isolated environment before relying
   on that backup. The repository does not automate general PostgreSQL backups.
3. Use a read-only session or browse-scoped API to collect evidence. From the API
   project, run `uv run --locked python -m people_gator_api.cli.database check`
   against the selected store; it validates migration/schema readiness without
   repairing it. Use cursor pagination and requested totals to audit full scopes,
   not just the first response page.
4. Compare sources and annotations with stored assets. Resolve media through the
   canonical helpers and `Filesystem`, checking page image/layout retrieval and
   aligned crops. A failed HTTP fetch may indicate storage/access trouble rather
   than an orphaned database record.

Read-only SQL can help explain an anomaly. For example, with a reviewed
connection and no output of secrets:

```sql
BEGIN READ ONLY;
SELECT version_num FROM alembic_version;
SELECT count(*) AS unknown_entity_touch
FROM pg_demo_entities WHERE last_touched_at IS NULL;
SELECT count(*) AS unassigned_faces
FROM pg_demo_image_occurrences io
JOIN pg_demo_faces f ON f.id = io.id
WHERE io.entity_id IS NULL;
COMMIT;
```

Null historical touch metadata and unassigned evidence are valid states, not
automatic repair candidates. SQL cannot establish that an identity assignment
is correct; review the source evidence.

## Invariants to investigate

| Area | Expected behavior |
| --- | --- |
| Provenance | Faces/mentions reference existing sources; internal and archive IDs remain distinct |
| Source identity | Canonical URL and typed identity remain unique and immutable |
| Link state | Unassigned implies no link state/verifier; verified implies actor and UTC time |
| Actor attribution | Original owner is preserved; real changes update last-touch atomically; no-op writes preserve it |
| Embeddings | Registered model stub, finite vectors and matching fixed dimension |
| Media | Keys resolve inside the selected filesystem and agree with image/layout dimensions |
| Schema | Recognized migration history and validated extensions/structure |

Constraints prevent many SQL integrity failures, but do not prove correct
provenance, image geometry or historical identity resolution. The startup checker
also does not comprehensively validate every constraint, function body, privilege
or dynamic HNSW index; use the corresponding integration tests and targeted audit.

## Prepare and execute a repair

Reproduce the anomaly in a disposable copy. Define an explicit target set and
preconditions, produce a read-only/dry-run report, and review before/after examples
with the issue's owner. Specify rollback or a tested restore path and schedule
writes so normal annotation work cannot race the repair.

Prefer typed API mutations or `Database` repositories with a real `GenericActor`
or `AuthContext`. Preserve source UUIDs and model identities; use omission versus
null deliberately. Unlink/reassign/verify through the link transition contract so
verification and processing metadata stay consistent. For actual merge/delete,
pass `context=` and validate the cascade scope first. A merge is not a cosmetic
rename: it transfers evidence and can invalidate transferred verification.

If a schema change or historical backfill is needed, implement a narrowly scoped
reviewed migration with preconditions and tests. Do not fabricate past actors,
timestamps or verification. Do not bypass model dimension validation, manually
stamp `head`, recreate retained tables or disable assertions to make a check pass.
Portable batch operations are not universally atomic; account for partial progress
and retry behavior. PostgreSQL repository transactions protect its supported
operations, while storage writes still need separate recovery planning.

After repair, repeat the original audit, run schema validation and representative
API/media reads, and compare counts, identities, review state and touch metadata.
Record the approved action and measured result without storing private data in
the repository. Extend regression coverage and relevant synthetic fixtures.

## Preview and migration recovery

The seed is additive and preserves review edits and checkpoints. It is not a
reset or cleanup tool; do not delete checkpoints to force arbitrary rewrites.
Follow [preview seeding](../people-gator-api/docs/preview-seeding.md) for supported
upgrades. Closing a preview deliberately deletes that PR's data; never use preview
cleanup as a retained-data repair mechanism.

For bootstrap adoption, back up first and use the checked
[`migrate --adopt-bootstrap` procedure](../people-gator-api/docs/database-migrations.md).
Unknown or partially matching schemas must be investigated before retrying.
A failed deployment can retain a previous running API while migrations have
changed its store; there is no automatic schema rollback. Preserve logs and the
candidate configuration and choose a compatible forward fix or verified restore.

