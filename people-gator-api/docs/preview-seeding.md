# Preview seeding

The synthetic dataset makes a new PR preview immediately usable. Its database
operations use the public `persistence.contracts.Database` repositories and API
request schemas. Files use the configured `Filesystem` contract. No real archive
content, credentials, external downloads or embedding/OCR service are required.
The seeder currently requires PostgreSQL because its scenarios include the
API-key registry and transactional last-processing metadata.

## Run it

From `people-gator-api`, with PostgreSQL and filesystem settings configured for
your development or preview environment:

```sh
uv run python -m people_gator_api.cli.database migrate
uv run python -m people_gator_api.cli.seed
```

If an older database was created in bootstrap mode, first follow the
[bootstrap adoption instructions](database-migrations.md). Seeding validates the
migration head and schema before writing data. It does not create or migrate
schema itself. In a production-format backend container, use its `seed` command:

```sh
docker compose --env-file /path/to/pr/compose.env -f deploy/preview/compose.pr.yaml run --rm --no-deps seed
```

The CLI prints IDs and clickable person/page URLs using the configured JWK issuer
as the application origin. PR deployments set this to their own preview hostname;
for local use, set it to your local application URL if you want matching links.
The public preview keeps its existing `test` / `test` login. Seed actors do not
add login accounts or usable API-key secrets.

## What to explore

| Scenario | Example |
| --- | --- |
| Mobile filtering | Open the printed mobile-filters link on a narrow viewport; only search and the sliders toggle show until expanded |
| Identity editing and aliases | Ada Novak, alias A. Novak; six people in total |
| Faces and mentions together | Ada Novak across Portrait album and Research notes |
| Faces only | Emil Dvorak and the A. Novak duplicate candidate |
| Mentions only | Nora Svoboda across Research notes and Correspondence |
| No evidence | Lenka Vesela, ready for manual linking |
| Identity discovery and merging | Open Ada Novak's Discover tab; A. Novak has nearby vectors |
| Unassigned face linking | Two unassigned album faces, including one close to Ada's vectors |
| Document/page/library filters | Three documents, two pages each, across preview-mzk and preview-nlk |
| Page evidence filters | Mixed pages, a face-only page, a mention-only page and an empty page |
| Face geometry | Eight faces with pixel bounding boxes and all five alignment keypoints |
| OCR highlights | Six mentions with matching text, baselines and polygons in stored OCR layouts |
| Multiple embedding models | Deterministic, normalized 8D and 4D synthetic vectors with registered models |
| Processing filters and details | Reviewer activity without an API key, face-importer and OCR-linker attribution with different registered keys |

Open the people search page and try the assignment, document, user and API-key
filters. The CLI also prints a `mobile-filters` URL combining a Novak search with
assignment, document, user and API-key filters. On screens narrower than 640px,
all filter controls and chips are collapsed by default behind the search row's
sliders button. Opening it reveals every filter; X collapses it without clearing
the query. Desktop keeps Assignment and Document visible, with additional filters
expandable separately. In a person's detail view, expand Last processed in the stats sidebar.
Edit a profile or assign a face to see processing attribution change. The two
synthetic API-key registry entries demonstrate historical filtering and attribution;
they cannot authenticate requests because no secret configuration is installed.

Document/page URLs follow the normal canonical source contract and internal
application links open working preview pages. Their `preview-*` libraries and
UUIDs are synthetic: the external Digitalni Knihovna links are identifiers, not
real archive records. Page JPEGs contain clearly labelled illustrated faces;
originals, resized images, aligned crops, OCR overlays and mention highlights
use the normal media services. The two vector models are deliberately named
synthetic models and their vectors demonstrate similarity, not real recognition.

## Reruns and changes

`peoplegator_api/preview-seed.json` in the configured storage records seeded entity,
face and mention IDs. Users, API-key registry entries and source identities use
repository get-or-create methods. Existing seeded records and media are retained:
review edits, reassigned evidence and processing timestamps survive a redeployment.
New fixture keys are added on the next run. Checkpointed identities removed by a
reviewer (including merged people and deleted evidence) stay removed; their saved
IDs act as tombstones, and the CLI prints links only for surviving records. Keep
the database and seed checkpoint together; to create a completely fresh dataset,
use a fresh database and storage pair.
Repository lookups recover entities/faces/mentions created just before a failed
checkpoint; a corrupt checkpoint is rejected rather than silently discarded.
Run only one seeder per database/storage pair at a time; the preview controller
already serializes deployments. The utility does not clear a database.

Fixture definitions live in `seeding/fixtures.py`, media generation in
`seeding/media.py`, and interface-based orchestration in `seeding/preview.py`.
When adding behavior to an existing fixture, account for preserved records and
media; add a new stable scenario key or a targeted additive upgrade when needed.
The root [agent guidelines](../../AGENTS.md) require every future feature change
to keep seed compatibility and add representative examples in the same change.

## CI and deployment

PR CI migrates a separate `ci_seed` database, executes the actual seed CLI twice,
and validates the result before the ordinary backend test suite. It uses
throwaway local storage. Seed integration tests also run in isolated schemas on
`PEOPLE_GATOR_SCHEMA_TEST_URL`, checking filters, vector discovery, OCR highlights,
face crops, reruns, review edits, merges/deletions and checkpoint recovery.

The trusted preview controller runs `storage-init`, `migrate`, then `seed` from the
candidate backend image before starting backend/frontend. A failing seed command
stops startup and leaves the previous deployment configuration/version intact,
allowing retry. Repository writes may already have committed, so checkpoints are
used to resume; the seed is not one atomic database/filesystem transaction.

Updating the installed preview host's controller and Compose template is an
operator step after review/merge; see [preview deployment](../../deploy/preview/README.md).
No workflow checks out and executes PR deployment scripts directly on that host.
