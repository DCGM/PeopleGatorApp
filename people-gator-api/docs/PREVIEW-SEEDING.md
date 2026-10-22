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
| Default Documents landing | Open `default-documents` (the application root): Documents is current, with named document groups and linked page thumbnails. Find **Portrait album**, open a page, then use the PeopleGator logo or first breadcrumb to return. `default-documents-scans` opens the same album in explicit Scan search. |
| Mobile filtering | Open the printed mobile-filters link on a narrow viewport; only search and the sliders toggle show until expanded |
| Identity editing and aliases | Ada Novak, alias A. Novak; six people in total |
| Faces and mentions together | Ada Novak across Portrait album and Research notes |
| Faces only | Emil Dvorak and the A. Novak duplicate candidate |
| Mentions only | Nora Svoboda across Research notes and Correspondence |
| No evidence | Lenka Vesela, ready for manual linking |
| Assigned-face selection and review | Open `person-face-review` (Irena Evidence): select automatic, manual and verified faces with checkboxes or Shift; Verify selected skips verified links, Unassign selected retains detection/media. Identity creation/import and Last processed start expanded. Use disposable data for mutations. |
| Entity reference discovery (#58) | Open `entity-discovery`: **Zora Cartographer**, alias **Saffron Navigator**, has 15 linked faces: 12 usable vectors, one missing, one other-model and one zero vector. Choose `preview-discovery-8d-v1`; faces favor **Orion Portrait**, name favors **Zora Cartographer II**, aliases favor **Saffron Navigator**. An unassigned match and a zero-vector candidate exercise finite scoring and assignment recovery. All ten practice scans have local media. |
| Identity discovery and merging | Open Ada Novak's Discover tab; A. Novak has nearby vectors |
| Unassigned face linking | Two unassigned album faces, including one close to Ada's vectors |
| Document/page/library filters | Original three two-page documents and grouped browsing examples across preview-mzk and preview-nlk |
| Page evidence filters | Mixed pages, a face-only page, a mention-only page and an empty page |
| Face geometry | Eight faces with pixel bounding boxes and all five alignment keypoints |
| OCR highlights | Six mentions with matching text, baselines and polygons in stored OCR layouts |
| Multiple embedding models | Deterministic, normalized 8D and 4D synthetic vectors with registered models |
| Processing filters and details | Reviewer activity without an API key, face-importer and OCR-linker attribution with different registered keys |
| Scan document-page gallery | Open `document-page-gallery`: 14 evidence-free pages of **Page gallery navigation**, more than one 12-page gallery batch, one without media; `document-page-gallery-filtered` keeps all six Příběhy archivářů pages under an annotation filter |

Open the people search page and try the assignment, document, user and API-key
filters. The CLI also prints a `mobile-filters` URL combining a Novak search with
assignment, document, user and API-key filters. On screens narrower than 640px,
filter controls are collapsed by default behind the search row's sliders
button, while active badges remain visible below. Opening it reveals every
filter; the sliders button collapses it without clearing the query. Desktop
shows all selectors in one wrapping flex panel. In a person's detail view, the stats sidebar always shows **Last change**.
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
Explicit upgrades of existing seed records (such as the person portrait upgrade)
checkpoint their state in `peoplegator_api/preview-seed-upgrades.json`, so seed
code from an earlier commit can still read the identity checkpoint after a rollback.
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

## Scan document-page gallery (issue #40)

The scan workspace shows a **Document pages** strip below the viewer (beside
the transcription and sidebar on wide screens). It lists every registered page
of the route's exact library and document. Each item has a thumbnail, the first
eight characters of the archive page UUID and an accessible name with the full
UUID. The current page is marked with `aria-current="page"` and scrolled into
view inside the strip. Selecting an item pushes the canonical page URL, so
reload and Back/Forward restore it. Evidence, link-state and workspace settings
are kept. Face, person and line selections are dropped, and pan/zoom resets.

Pages appear in archive page-ID order by default, or by last change through the
strip's **Sort pages** control (#33), 12 per request. Neither order is the
physical page sequence: the archive does not record page numbers, so the gallery
shows no ordinal and its UUID labels are not page numbers. The gallery loads further batches until the current page
appears. After that it loads when the strip's end is reached or **More pages**
is activated. Evidence filters never apply to the gallery.

Open the seed report's `document-page-gallery` link, or find **Page gallery
navigation** in Documents (`preview-mzk`). It has 14 synthetic, evidence-free
pages with local JPEGs. Page 9 is registered without image or layout, so its
thumbnail shows *No preview* and its scan reports that it could not be loaded,
but navigation continues. Scroll or swipe the strip, open a distant page, switch
quickly, then reload and use Back/Forward. Tab through the page links: arrow keys
there do not move the face/line selection. Single-page documents such as
**Viewport focus practice** show one current item. The
`document-page-gallery-filtered` link opens a Příběhy archivářů scan with the
face importer's annotation filter. That filter matches four of the document's
six pages in Documents, yet the gallery still lists all six.

The fixture adds new stable keys only (document `page-gallery`, pages
`page-gallery-1` to `page-gallery-14`). Reruns add missing pages and media
without rewriting existing records. Integration tests check exact document
scoping, 12-page batching without duplicates, the repeated stable order,
thumbnails and the missing-media 404, the filtered example and twice-run
preservation.

## Shared annotation filters and edits (#31)

The `document-pages-without-annotations` example finds **Příběhy archivářů**.
Open its heading or +more link to browse all six registered pages, including
its page without faces or mentions. Navigation adds only the document's library
and archive ID; it does not invent annotation criteria. Explicit modification
user/key/date and link-state selections still carry through and narrow results.
The repository test paginates all six pages and checks that selecting the importer
reduces the list to four annotated pages. Twice-run preservation retains the
unannotated page and its source/processing metadata.

The `scan-assignment-search` example opens scans for Irena's annotation review ledger.
Open its page, select a face and search for **Ada Novak** in the assignment panel.
Ada has evidence elsewhere and must remain available as a database candidate:
opening the scan must not silently add an evidence-source filter. Explicitly
selected annotation filters still apply. Repository coverage checks candidate
lookup, reassignment, local media and twice-run preservation of the review edit.

The `shared-filter-navigation` example searches for Irena with the importer API
key selected. Open her profile, change that key or clear it, then use the normal
**People** breadcrumb. The destination must use the current filters rather than
restore the original key. Profiles use the standard breadcrumb hierarchy; no
custom source/return breadcrumb is shown, including for older URLs containing
`origin_return`. Seed tests check real key-filtered people/faces, changed-key
empty results, clearing and twice-run preservation of annotation metadata.

The `annotation-editor-filters` example opens Irena's profile with the importer
user and API key selected together, showing the three faces last changed by
that actor/key and excluding the separately verified face.

Search for **Irena Evidence**. This checkpointed synthetic identity has faces
and mentions in two libraries. **Annotation review ledger** (`preview-mzk`) has
an importer-created face and a reviewer-verified face; **Annotation review
correspondence** (`preview-nlk`) has a manual face and a verified mention.
Select a modification user, API key, date bound or document to follow the same
annotation criteria through Documents, People, profiles and scans. Combining
criteria from different annotations must not produce a match.

Creation/import times and actors remain separate from annotation changes and
person/document processing. The seed uses real actor contexts and actual server
event times. Reruns preserve recorded creation, edits, assignments and checkpoints.
Internal fixture keys are stable for retained preview compatibility. Integration
coverage checks equivalent repository matches, unchanged times on rerun and
identical verification, plus upgrades from the previously deployed revision.

The `page-activity` example opens the annotation review ledger directly with
`panel=activity`. Its two faces and one mention have two importer edits and one
later reviewer verification. In the scan sidebar, choose Activity, then By user:
selecting Preview reviewer shows the reviewer-verified face. By day groups the
recorded annotation edits in browser local time. The default Faces tab contains the gallery, current face and assignment candidates.
Faces, Activity and Statistics share the top-level pane navigation; Activity uses
the full remaining pane height and scrolls independently of the scan. The seed's activity link is additive and
does not rewrite reviewed fixture data.


The `linked-face-states` entry point opens Irena Evidence with Automatic, Manual
and Verified link states selected. The compact assignment row uses text colors from the same
shared palette as annotation badges elsewhere: blue for Automatic, amber for
Manual, green for Verified, and muted for Unassigned, with the standard light/dark
variants. State rows have no background tint. Face selection keeps its separate highlight. This scenario reuses the
existing linked faces and local media; its repository test checks the URL state
filter against actual detections, resolves their media and preserves them on rerun.

The `person-evidence-cards` entry point shows all four Irena Evidence faces,
including three assignment states, libraries and importer/reviewer attribution.
Faces uses the same compact card spacing, shape and library color as Discover:
the first row below the photo is assignment icon/state plus `conf` (detection
confidence), followed by library plus truncated document ID and last-change/user rows. Cards do not show
raw detection/page IDs, matching labels, image status badges or reserved
empty details blocks. Source links still open the correct page with its face
selected, and verification attribution remains available on the assignment row.
Editor names are plain text; a TODO in `AnnotationLastChange.vue` defers user links
until the user tab exists.
The additive `person-face-style-comparison` entry point opens the same identity's
Discover tab; switch to Faces to compare the card presentation and select faces
for verification/unassignment. Verify selected uses a green outline; Unassign
selected uses a red outline, with the same behavior in light/dark themes.
Existing source identities, records/media and
review edits are reused. The normal **People** breadcrumb forwards the current
shared evidence filters; it does not restore a saved source URL. Shared evidence criteria populate the
actual controls, while resource-specific processing and search settings remain
separate. These entry points reuse existing
stable records/media and never reset checkpoints or reviewer edits. Integration
coverage resolves every source/media link, checks attributed annotation records
and page/document statistics through repositories, and verifies an unchanged rerun.

### Selected-person OCR line highlights (issue #45)

Open the seed report's `person-mention-highlights` link to **Viewport focus
practice** with Ada Novak selected. Both OCR lines carry Ada's linked mentions
and receive orange outlines and tints. The current line keeps its accent
highlight and adds an orange ring, because it also mentions Ada; select the
other line to compare. Hovering an orange line deepens its tint, and each
mention line's accessible name ends with "(mentions the selected person)".
Remove `selectedPerson` from the URL to see the overlay without highlights.
Check the overlay in light and dark themes and on desktop and mobile.

Open `person-mention-highlights-multiline` for **Link state review / page 2**
with Ada Review selected. Her verified mention spans two OCR lines, and both
are orange. The **Emil Review** line has no linked identity and stays plain.

Highlights follow each mention's linked identity, not the line text. Span
resolution places a mention on every occurrence of its name on the page, so
both "Ada Novak" records on the focus page cover both lines. If a reviewer
reassigns one of them, for example to Lenka Vesela, both lines also become
Lenka's. Similarly, linking the Emil Review line to Ada Review makes that line
orange for her.

Both entry points reuse existing pages, local images and linked mentions. They
do not change checkpoint IDs, assignments or processing timestamps. The seed
integration tests resolve the lines through the media service. They check that
each identity covers exactly the lines of its own mention records, including
both fragments of the multi-line mention, and that reruns preserve reviewed
reassignments.

### Scan editor viewport focus (issue #34)

Open the seed report's `viewport-focus` link, or find **Viewport focus practice**
in Documents. Its page has two Ada Novak portraits in separated regions, a tiny
unassigned face near the upper right, and two distinct Ada Novak mentions at
heights 460 and 1000. Select each face in the gallery or overlay, use previous/next
or left/right arrows, and activate each name in the transcription with a mouse
or keyboard. Each occurrence focuses its own containing OCR line: precise mention
polygons are not exposed by the workspace span type, and character offsets are
not treated as image coordinates. An identity-level candidate preview does not
choose an arbitrary spatial occurrence.

Automatic focus uses the viewer's supported 55–350% range, with a named
`MAXIMUM_AUTOMATIC_ZOOM` of 3.5 (350%), 20% proportional context and a 24 CSS-pixel
gutter below the measured toolbar. Very large targets stop at the supported
minimum even when they cannot completely fit. Pan/zoom manually, then activate
the same evidence to recenter it. Data refreshes and resizing alone preserve
manual placement; pending focus waits for image readiness and usable bounds,
and page changes discard it. The added fixture has new stable keys and adds
missing records/media without rewriting existing reviewer edits or timestamps.

## Person sidebar statistics and Last change (#43)

The CLI's `person-last-change` link opens **Ada Review**, reusing the Link state
review fixtures. Her sidebar shows **Face annotations** and **Mention
annotations** as automatic/manual/verified icon-value pairs (1 / 0 / 1 each),
right to left, beside the existing Face detections, Document mentions and
Libraries totals. **Last change** is always visible with the editor under
**Modified by** and the API key (or **No API key**).

Under 24 hours the value reads `modified just now`, `modified N min ago` or
`modified N hour(s) ago`; from exactly 24 hours it reads `modified on yyyy-mm-dd`
in browser local time. The exact timestamp stays in the `<time datetime>` and
its title. The text ages on a local timer without refetching. Records without
change metadata show **Not recorded** and never substitute the owner. Seeded
timestamps are not reset on rerun, so a long-lived preview normally shows the
date form; edit Ada's short description to see the relative form and the
updated editor without reloading. No seed records or API contracts changed.


### Saved person portraits (#35)

Open `filter_examples.person-portrait-selection` (Irena Evidence). Her initial
manual portrait is the last UUID among her four synthetic linked faces, so it
differs from the first listed face. Select one face in the evidence grid, then
choose **Use as portrait** in the bottom bar (`person-portrait-selection`).
Select the face marked **Portrait** and choose **Use automatic** to reset. Change evidence
filters, reload, and compare People search, Discover people, and scan assignment
candidates. The portrait remains canonical while evidence cards show their own
faces. Ada Novak demonstrates a persisted automatic portrait: the first assigned
face stays selected through later assignments, identity edits and reseeding while
linked. Nora Svoboda has
no face and uses initials. All media comes from the existing local fixtures.

The `person-portrait-v1` manifest upgrade is additive and checkpointed. It preserves
existing manual choices, records the expected automatic choice and touch time
before applying the one-time reviewer selection, and never rewrites later choices
(including automatic resets). Recovery after a failed checkpoint compares those
preconditions before writing, so an intervening review is preserved. Deleted or
reassigned candidate faces are skipped. Existing entity/source/annotation keys,
UUIDs and checkpoints remain intact. PostgreSQL is required for saved portraits.


## Sorting and exact-appearance mentions (#33)

The `sorting` person (**Marta Řádková**) and two documents add a small,
self-contained sorting scenario with stable keys only:

| Fixture | Demonstrates |
| --- | --- |
| `sorting-ledger` (`preview-nlk`, "Řádková ledger", 3 pages, one evidence-free) and `sorting-notes` (`preview-mzk`, "radkova notes", 1 page) | Accent/case-insensitive name order ("Ř" folds to "r"), library order, uneven page counts and the most pages in `preview-nlk` |
| Faces `sorting-manual` (0.62), `sorting-automatic` (0.88, automatic), `sorting-verified` (0.75) and unassigned `sorting-similar` (0.91) | Confidence, assignment-state (verified, manual, automatic, unassigned last) and source order; a similar unassigned face in Discover |
| Mentions recorded as "Marta Řádková" (×3), "M. Řádková", "MARTA ŘÁDKOVÁ" and "Marta Radkova" | Exact appearance groups that never merge spelling, case or accent variants, with full counts |

Explore the seed report's `sorting-*` links: `sorting-documents` (Documents by
page count), `sorting-document-names` (search with an explicit name order),
`sorting-people`, `sorting-scans` (one document's pages by page ID descending),
`sorting-faces` (Marta's faces by confidence), `sorting-mention-groups`
(Mentions → Exact appearance by occurrence count; expand a group to see its
occurrences, sorted independently) and `sorting-similar-faces` (Discover). Choose
a strategy (field and direction, such as *Pages · Highest first*) in a panel's
single **Sort** select, reload, copy the link and use Back/Forward; each panel
keeps its own choice. Seeded edit times are recorded by
the repositories and are not reset on rerun; the preview has no historical
unknown times, so integration tests cover unknown-last ordering with disposable
records.

The upgrade is additive: new people, sources, faces and mentions are checkpointed
under new keys, and existing records, reviews and timestamps are untouched.
Integration tests check confidence/state order, exact groups and counts,
paged occurrences, accent-folded document names, page-count order, sorted
similarity candidates and rerun preservation of a reviewer unassignment.

### Entity reference discovery regression (#58)

The additive `discovery` fixture has its own registered synthetic 8D model, stable
keys and ten pages in **Entity discovery practice**. Existing records, timestamps,
reviewed aliases, assignments and checkpoints are retained on reruns. No retained
vectors or user edits are rewritten. Open the printed `entity-discovery` link,
choose individual **Reference inputs** or combinations, and compare both result
lists on desktop and mobile. Faces-only also finds `discovery-unassigned` for
manual linking. Zero embeddings remain stored as realistic degenerate fixtures;
search excludes undefined cosine contributions rather than assigning fake scores.

The seed integration regression queries each source through both repositories,
checks meaningful matches and finite scores, excludes zero-vector witnesses,
reads a real aligned crop, and preserves edited aliases/assignments on rerun.
Existing interrupted-checkpoint and edit-preservation checks cover the added keys.


PR #59 review follow-up: `entity-discovery-identifier` opens text-only discovery
for the existing unassigned face's `preview-seed/discovery-unassigned` identifier.
Its exact text hit has no invented face score and retains working local media.
The seeded integration regression exercises this indexed identifier path as well
as name/alias input selection and preserves reviewed assignments on two reruns.
Use `entity-discovery` to inspect the removable nondefault Face model tag with
mobile settings collapsed; Clear filters resets sources/model while preserving
search and evidence choices. On disposable data, failed assignment/merge requests
retain their selection and point to the corresponding action for recovery.
Face text candidate retrieval is bounded to 200 per term per indexed field;
apply migration `d34a021b0012` before seed/startup to install its identifier index.
