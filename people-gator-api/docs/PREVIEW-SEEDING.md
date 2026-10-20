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
[bootstrap adoption instructions](DATABASE-MIGRATIONS.md). Seeding validates the
migration head and schema before writing data. It does not create or migrate
schema itself. In a production-format backend container, use its `seed` command:

```sh
docker compose --env-file /path/to/pr/compose.env \
  -f deploy/people-gator-deploy/src/people_gator_deploy/assets/compose.pr.yaml run --rm --no-deps seed
```

The CLI prints IDs and clickable person/page URLs using the configured JWK issuer
as the application origin. PR deployments set this to their own preview hostname;
for local use, set it to your local application URL if you want matching links.
The public preview keeps its existing `test` / `test` login. Seed actors do not
add login accounts or usable API-key secrets.

The [staging database runtime test](../../deploy/people-gator-deploy/tests/test_staging_runtime.py)
reuses these synthetic fixtures: it runs the seed twice in a disposable source
database, creates a historical-revision local dump, restores original rows,
links and vectors, then checks migrations, retained edits and API startup.
There is no S3 service or media copy in that test. Staging storage/media/auth are
managed externally; missing objects do not invalidate the database snapshot.
This does not automatically seed the actual staging environment.

## What to explore

| Scenario | Example |
| --- | --- |
| Mobile filtering | Open the printed mobile-filters link on a narrow viewport; only search and the sliders toggle show until expanded |
| Identity editing and aliases | Ada Novak, alias A. Novak; six people in total |
| Faces and mentions together | Ada Novak across Portrait album and Research notes |
| Faces only | Emil Dvorak and the A. Novak duplicate candidate |
| Mentions only | Nora Svoboda across Research notes and Correspondence |
| No evidence | Lenka Vesela, ready for manual linking |
| Assigned-face selection and review | Open `person-face-review` (Irena Evidence): select automatic, manual and verified faces with checkboxes or Shift; Verify selected skips verified links, Unassign selected retains detection/media. Identity creation/import and Last processed start expanded. Use disposable data for mutations. |
| Identity discovery and merging | Open Ada Novak's Discover tab; A. Novak has nearby vectors |
| Unassigned face linking | Two unassigned album faces, including one close to Ada's vectors |
| Document/page/library filters | Original three two-page documents and grouped browsing examples across preview-mzk and preview-nlk |
| Page evidence filters | Mixed pages, a face-only page, a mention-only page and an empty page |
| Face geometry | Eight faces with pixel bounding boxes and all five alignment keypoints |
| OCR highlights | Six mentions with matching text, baselines and polygons in stored OCR layouts |
| Multiple embedding models | Deterministic, normalized 8D and 4D synthetic vectors with registered models |
| Processing filters and details | Reviewer activity without an API key, face-importer and OCR-linker attribution with different registered keys |

Open the people search page and try the assignment, document, user and API-key
filters. The CLI also prints a `mobile-filters` URL combining a Novak search with
assignment, document, user and API-key filters. On screens narrower than 640px,
filter controls are collapsed by default behind the search row's sliders
button, while active badges remain visible below. Opening it reveals every
filter; the sliders button collapses it without clearing the query. Desktop
shows all selectors in one wrapping flex panel. In a person's detail view, expand Last processed in the stats sidebar.
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
Run only one seeder per database/storage pair at a time; the deployment utility
already serializes preview deployments. The utility does not clear a database.

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

The trusted deployment utility removes the selected PR's old containers while
retaining its database and media volume, then runs `storage-init`, `migrate`, and
`seed` from the candidate backend image before starting backend/frontend. A
failing seed command stops startup and leaves the previous deployment
configuration/version intact for retry, but the preview stays stopped until a
successful retry. Repository writes may already have committed, so checkpoints are
used to resume; the seed is not one atomic database/filesystem transaction.

After one-time operator installation, the lifecycle workflow installs or reuses
the `people-gator-deploy` utility from its exact reviewed `main` revision, without
sudo, and runs that pinned version; see the
[utility guide](../../deploy/people-gator-deploy/README.md). No workflow checks out
and executes PR deployment scripts on that host. Installed versions are verified
against their recorded file digests, so a stale or modified installation cannot
bypass candidate seeding. PR code never supplies the host controller; the
candidate image supplies the fixture code.
Successful preview state includes a `seeded_version` marker; after a host upgrade,
rerunning the same deployment can seed previews created by older controllers.

## Grouped documents and scans

Open `/documents?library=preview-mzk` to explore **Named preview album** with two
scans and **Document awaiting scans** with no pages. **Album in another library**
in `preview-nlk` deliberately shares the album's document UUID; its single page
must stay in its own group. **Legacy unnamed document** has one scan and no stored
name, demonstrating the `Document <document_id>` heading fallback on fresh previews.
`/scans` also includes **Unregistered scan collection**,
which has local media but no registered document and is absent from Documents.
The seed CLI prints `grouped-documents` and `unregistered-scan` links.

Existing document identities are retained. New registrations receive their fixture
titles; documents already seeded without names keep their nullable name and use the
UI's `Document <document_id>` fallback. Reregistration never overwrites a name.
The added scenario keys demonstrate names even in retained preview databases.
Integration coverage checks names, empty groups, library isolation, page cursors,
scan-only media, repeat registration and legacy requests without a name.

### Entity link review (#6)

The **Link state review** document in `preview-mzk` adds two synthetic scans.
Each annotation kind has exactly one automatic, manual, verified and unassigned
record (four faces and four mentions across the document). Two additional people
keep the original face-only and mention-only scenarios unchanged. Page 1 links Ada Review
automatically and Emil Review manually; page 2 verifies Ada Review and leaves one face and
one mention unassigned. Ada Review's verified mention spans two OCR lines and counts
once. Verification is a PATCH attributed to the Preview reviewer, with a UTC
server timestamp. Existing fixtures and checkpoints are retained; reruns leave
review edits and verification metadata intact.

Open the document from Documents, try the scan's Link state controls and its
**Statistics** tab at the top of the scan pane (below the scan on mobile). It shows **This page** and **Whole document** counts
without covering the scan. The CLI prints a `page-statistics` link to page 2; the older `link-statistics` fragment remains supported,
where the page's verified/unassigned counts can be compared with all four states
across the document. Then follow Ada Review to the shared Faces /
Mentions filter. All includes unassigned annotations; selecting all three states
includes only assigned annotations. Filter Documents or People by Verified to
find the example even before loading its second scan. The existing Document
awaiting scans demonstrates zero statistics. Seed deployment order remains
storage initialization → migrations → seed → application startup.

### Inline scan toolbar (#14)

The CLI's `scan-toolbar` link opens **Link state review / page 2** with verified
and unassigned faces and mentions. The inline **Automatic**, **Manual** and
**Verified** multi-select toggles sit beside navigation, zoom, Names and translation.
Their icons stay directly available on mobile (labels appear at wide viewports);
each has an accessible name and a native title description. The toolbar wraps within the
viewer, including below 640px, without sliders, active-filter tags or a generic
clear-filters row. This scan-toolbar exception does not change the comboboxes,
tags or mobile collapse behavior of actual search/filter panels.

Compare `scan-toolbar-assigned` (all three toggles pressed, only the verified
face and mention on page 2) with **All** (no states selected, also includes the
unassigned face and mention). `scan-toolbar-union` opens page 1 with automatic
and manual evidence selected together. Toggle each state, reset, reload and use
browser back/forward to compare pressed states, URL and evidence. Check the
neighboring tools and keyboard arrow/Space operation at desktop and mobile sizes.
In light and dark themes, the toolbar container is transparent: the scan stays
visible in the gaps between the controls, including when they wrap on mobile.
Clickable tools use opaque neutral background/foreground theme colors in both
themes, with a neutral muted background for selected and hovered controls. Check
Names, translation, All and each link-state toggle; none uses a colored fill.
The existing linked records, deterministic local JPEGs and OCR layouts supply
this scenario; adding these links never resets reviewed assignments or timestamps.
Integration coverage queries faces and mentions for every state combination on
both pages, checks media/verified OCR spans, and repeats the seed after a review edit.

### Faces without OCR

The **Faces without OCR** document adds a synthetic scan with two unassigned
faces, a local JPEG, and deliberately no OCR layout. Open the CLI's
`faces-without-ocr` link. Both face boxes must appear over the scan and support
selection, zoom, and pan even though no transcription is available. The viewer
uses the original image's pixel dimensions for these boxes; a resized image's
dimensions would put them in the wrong place. Original fixtures and review edits
remain unchanged on seed reruns. Integration coverage checks the missing layout,
face statistics, local page image, and aligned face crops through media services
and repositories. The dataset now has nine registered documents, fourteen pages,
fourteen faces, and ten mentions.

## Document processing (issue #8)

The additive `issue8-*` fixtures register **Příběhy archivářů** in `preview-mzk`
and a separate mirror with the same archive UUID in `preview-nlk`. Six pages
include automatic and verified faces; the linked Ada Novak / A. Novak identity
occurs on five pages, including pages beyond a four-page preview. The first page
and the mirror stay untouched. OCR linking uses the registered synthetic OCR
key; verification uses the reviewer without a key. No historical timestamps are
invented for old records.

`issue8-orphan-1` demonstrates processing a page without a registered document.
The image `https://preview.invalid/issue8/portrait.png` has a local PNG stored
under `image_content_key` and an unassigned face, demonstrating the same generic
source processing on images. The URL is a synthetic identity; no network download
is needed. Repeating the seed preserves processing times, assignments and edits.

Explore `/documents?q=pribehy`, or open **Direct annotation ledger** in
`preview-nlk`: its manual mention of Emil Review demonstrates a document match
without any matching scan. Select Libraries independently of loaded results;
options come from registered documents across the database. Try the verified link
state with no unassigned faces to find Příběhy archivářů, or verified with
unassigned faces to find Link state review. **Document awaiting scans** and the
unnamed legacy document remain usable without processing history.

The seed output's `compact-document-filters` link selects both libraries,
automatic/verified states, no unassigned faces and the reviewer while preserving
the title search. Use it to check content-sized selectors in a single wrapping
flex panel: search occupies two thirds of the first line from 640px, and later
filter rows span the full panel. On mobile, expand filters with the sliders
button. The underlined document title, bold orange library and archive ID form
one link to its scans; each preview links to its exact page without repeating
library information. The `outline-filter-badges` link searches by archive UUID
with two libraries and link states selected: check that active filters use
standard outline badges with small labels, and that the link-state combobox
matches the height of the Libraries and Unassigned faces comboboxes. The
printed `mobile-filters` link also demonstrates the Assigned faces combobox
alongside link state and document filters on People. The result counter appears
at the right end of the search input group, after the clear-search button. Remove a badge with its X button
to update both the URL and results. The `rounded-filter-removal` link demonstrates
circular X buttons for library, link-state and unassigned-face badges. Hover or
keyboard-focus one, then remove its filter while preserving the search text.
In the document information, registered
page count precedes processing time, user and API key (each on its own line),
followed by face and mention statistics. A `+N` link with a right chevron follows
the last preview and opens the remaining scans in the same document scope.
The `document-preview-remainder` link shows six registered pages with four
previews and `+2` (two previews and `+4` on mobile). Hover the `+N` link to see
its underline and small rightward chevron movement, without a background
change. `+N` is orange and the chevron uses the standard text color. Page labels show standard UUIDs with an ellipsis when needed; hover
the label to read the full UUID.

The document API accepts `filter.last_touched_from` and `filter.last_touched_to`
(inclusive, timezone-aware), repeated `filter.last_touched_by_user_id`,
`filter.last_touched_by_api_key_id`, `filter.library` and
`filter.entity_link_state`, plus `filter.has_unassigned_faces=true|false`.
The same processing fields are available on source/page/image lists and existing
page/document search. A page's filters use that page's own stored history.
Search totals describe bounded candidates (200 per direct identity/name/entity
candidate path), while list totals count all matching registered documents.

To regenerate the frontend contract locally, run the API's
`scripts/export_openapi.py openapi.json` with local settings, then
`npm run openapi-ts` from `people-gator-app`. `PEOPLE_GATOR_OPENAPI` can override
that local input path. The exported JSON is ignored; generated SDK files are
committed.

The standalone portrait is an actual PNG with a visible synthetic face. An exact
match to the original issue #8 JPEG fixture at that PNG key receives a narrowly
scoped format upgrade. Reviewed or replaced image bytes remain untouched; the
upgrade does not change source identities, annotations or processing timestamps.

## Media upload sandbox (issue #10)

The additive **Media upload sandbox** document in `preview-mzk` has two
synthetic pages, each with a local JPEG and valid OCR layout. Both are free of
faces and mentions so replacing their media cannot invalidate annotation
geometry. The seed CLI prints a `media-upload` link to the first page. Open the
document from Documents to inspect both scans; authenticated ingest clients can
PUT a multipart `file` to `/api/v1/pages/{source_id}/image` or a validated layout
to `/api/v1/pages/{source_id}/page-layout`. Use the page's source UUID returned
by `/api/v1/pages/lookup`, rather than its archive page UUID in the browser URL.
GET the same resource to verify the result and its upload receipt's byte size.
There is no upload control in the page viewer.

Reruns add missing sandbox records/media, retain stable source identities, and
preserve replaced scans, layouts and processing metadata. Integration tests
exercise repositories and real local media services, including image replacement,
derivative refresh, layout replacement and twice-run preservation. Slow success,
S3 denial, SDK timeout, pool saturation and same-page synchronization are covered
by gated regression tests, not by introducing failures into preview data. See
[media concurrency](MEDIA-UPLOAD-CONCURRENCY.md) for the isolated HTTP diagnostic.

## Evidence provenance and annotation edits (#31)

Search for **Irena Evidence**. This new, checkpointed synthetic identity was
imported from a synthetic authority; its reference is deliberately under
`preview.invalid`. Its faces in **Evidence provenance ledger** (`preview-mzk`)
have Automatic and Authority origins. The authority face has a Verified link:
verification preserves its origin and original importer/API key, while the
annotation's last editor is the reviewer without an API key. **Evidence
provenance correspondence** (`preview-nlk`) contains Manual and Unknown origins
and a separately verified mention. Existing fixtures retain unknown historical
origins; the seed does not infer provenance from identifiers or link states.

Select Authority origin + Manual/Verified link states + `preview-mzk` to explore
the same evidence through Documents, People, a profile and its source page.
Selecting Manual origin in that document must return no match; the manual face
in the other library cannot satisfy part of the predicate. Annotation edit dates
and actors are distinct from identity creation and person/document processing.
The seed uses real actor contexts and records actual server event times; it does
not fabricate fixed historical timestamps. New fixture keys are additive and
reruns preserve provenance, edits, attribution and checkpoints. Integration
coverage asserts equivalent repository matches and unchanged annotation times
on rerun and identical verification.

The `page-activity` example opens the provenance ledger directly with
`panel=activity`. Its two faces and one mention have two importer edits and one
later reviewer verification. In the scan sidebar, choose Activity, then By user:
selecting Preview reviewer shows the verified authority face. By day groups the
recorded annotation edits in browser local time. The default Faces tab contains the gallery, current face and assignment candidates.
Faces, Activity and Statistics share the top-level pane navigation; Activity uses
the full remaining pane height and scrolls independently of the scan. The seed's activity link is additive and
does not rewrite reviewed fixture data.


The `person-evidence-cards` entry point shows all four Irena Evidence faces,
including a matching-detection overlay, three assignment states, two complete
library/document/page references and the importer/reviewer attribution. The
cards have equal dimensions, a bottom-right status overlay and an always-visible
last-change row; editor links open people search filtered by that annotation
editor. Detection origin is retained in data/filtering but has no disclosure on
the card. The top-bar **Back to People search · “Irena”** link restores the saved
search; raw origin metadata is not rendered as filter tags. Shared evidence
criteria populate the actual controls, while resource-specific processing and
search settings stay in their saved return URL. These entry points reuse existing
stable records/media and never reset checkpoints or reviewer edits. Integration
coverage resolves every source/media link, checks attributed annotation records
and page/document statistics through repositories, and verifies an unchanged rerun.
