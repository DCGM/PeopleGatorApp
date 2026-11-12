# Preview seeding

The synthetic dataset makes a new PR preview immediately usable. Its database
operations use the public `persistence.contracts.Database` repositories and API
request schemas. Files use the configured `Filesystem` contract. No real archive
content, credentials, external downloads or embedding/OCR service are required.
The seeder currently requires PostgreSQL because its scenarios include the
API-key registry and transactional last-processing metadata.

## Unalignable stored face (#64)

The additive **Face alignment recovery** document (`alignment`, `preview-mzk`)
has one locally generated page (`alignment-1`) with two unassigned faces:

- `alignment-coincident` has all five required landmark types at the same
  finite, in-bounds point. Its aligned crop returns HTTP 422 with
  `detail.code: invalid_face_keypoints`.
- `alignment-valid` is the valid control and returns a decodable JPEG.

Open the CLI's `alignment-1` page link to inspect the synthetic detections.
The seed report includes each detection UUID and the `alignment-coincident-crop`
and `alignment-valid-crop` API paths. With browse authentication, request
`GET /api/v1/faces/{detection_id}/aligned_crop?max_width=256`; use the API origin
for these paths (the CLI prefixes printed links with the configured app origin).
See [aligned face crops](ALIGNED-FACE-CROPS.md) for the error and numerical limits.

New stable fixture/checkpoint keys add this scenario to retained previews without
rewriting existing faces, assignments, media or modification times. Reruns keep
reviewer evidence assignments and processing timestamps. Integration
tests read real media and repository records, exercise the crop HTTP endpoint,
verify failed requests leave processing times unchanged, and preserve an
assignment on rerun. Interrupted-checkpoint recovery covers both
new detection keys.

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
| Default Documents landing | Open `default-documents` (the application root): Documents is current, with named document rows. Find **Portrait album**, click its name to browse pages, then use the PeopleGator logo or first breadcrumb to return. `default-documents-scans` opens the same album in explicit Scan search. |
| Mobile filtering | Open the printed mobile-filters link on a narrow viewport; only search and the sliders toggle show until expanded |
| Identity editing and aliases | Ada Novak, alias A. Novak; six people in total |
| Faces and mentions together | Ada Novak across Portrait album and Research notes |
| Faces only | Emil Dvorak and the A. Novak duplicate candidate |
| Mentions only | Nora Svoboda across Research notes and Correspondence |
| No evidence | Lenka Vesela, ready for manual linking |
| Assigned-face selection and review | Open `person-face-review` (Irena Evidence): select automatic, manual and verified faces with checkboxes or Shift; Verify selected skips verified links, Unassign selected retains detection/media. Identity creation/import and Last processed start expanded. Use disposable data for mutations. |
| Entity reference discovery (#58) | Open `entity-discovery`: **Zora Cartographer**, alias **Saffron Navigator**, has 15 linked faces: 12 usable vectors, two without embeddings, and one other-model vector. Choose `preview-discovery-8d-v1`; faces favor **Orion Portrait**, name favors **Zora Cartographer II**, aliases favor **Saffron Navigator**. An unassigned match and a candidate without an embedding exercise finite scoring and assignment recovery. All ten practice scans have local media. |
| Identity discovery and merging | Open Ada Novak's Faces tab; A. Novak appears under Similar people |
| Unassigned face linking | Two unassigned album faces, including one close to Ada's vectors |
| Document/page/library filters | Original three two-page documents and grouped browsing examples across preview-mzk and preview-nlk |
| Page evidence filters | Mixed pages, a face-only page, a mention-only page and an empty page |
| Page and document verification (#149) | Open `document-verification`: **Verification: all pages verified** (2 / 2) and **Verification: in progress** (1 / 3) in `preview-verification`. See [Page verification](#page-verification-149). |
| Deactivated reviewer attribution (#66) | Open `deactivated-reviewer`: **Olga Expiry** matches **Modified by: Preview former reviewer**, an inactive user |
| Face geometry | Eight faces with pixel bounding boxes and all five alignment keypoints |
| OCR highlights | Six mentions with matching text, baselines and polygons in stored OCR layouts |
| Multiple embedding models | Deterministic, normalized 8D and 4D synthetic vectors with registered models |
| Processing filters and details | Reviewer activity without an API key, face-importer and OCR-linker attribution with different registered keys |
| Teleprompter focus modes (#36) | Open `teleprompter-person`: Ada's lines of the 40-line **Teleprompter reading practice** page, with GitHub-style gap expansion, Custom line sets and the page minimap. See [Teleprompter reading practice](#teleprompter-reading-practice-36). |
| Scan document-page gallery | Open `document-page-gallery`: 14 evidence-free pages of **Page gallery navigation**, more than one 12-page gallery batch, one without media; `document-page-gallery-filtered` keeps all six Příběhy archivářů pages under an annotation filter |

Open the people search page and try the assignment, document, user and API-key
filters. The CLI also prints a `mobile-filters` URL combining a Novak search with
assignment, document, user and API-key filters. On screens narrower than 640px,
filter controls are collapsed by default behind the search row's sliders
button, while active badges remain visible below. Opening it reveals every
filter; the sliders button collapses it without clearing the query. Desktop
shows all selectors in one wrapping flex panel. In a person's detail view, Statistics shows **Last change**.
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

The CI workflow migrates a separate `ci_seed` database, executes the actual seed
CLI twice, and validates the result before the ordinary backend test suite. It
uses throwaway local storage. Seed integration tests also run in isolated schemas on
`PEOPLE_GATOR_SCHEMA_TEST_URL`, checking filters, vector discovery, OCR highlights,
face crops, reruns, review edits, merges/deletions and checkpoint recovery.

The same run's `deploy-preview` job runs the deployment utility from the PR's
checkout. It removes the selected PR's old containers while retaining its
database and media volume, then runs `storage-init`, `migrate`, and `seed` from
the candidate backend image before starting backend/frontend. A failing seed
command fails the deploy job and leaves the previous deployment
configuration/version intact for retry, but the preview stays stopped until a
successful retry. Repository writes may already have committed, so checkpoints are
used to resume; the seed is not one atomic database/filesystem transaction.

The candidate image supplies the fixture code and the PR branch supplies the
deploy code; see the [utility guide](../../deploy/people-gator-deploy/README.md).
Successful preview state includes a `seeded_version` marker, so rerunning the
workflow seeds a preview whose earlier deployment did not complete seeding.

## Documents and scans

Open `/documents?library=preview-mzk` to explore **Named preview album** with two
scans and **Document awaiting scans** with no pages. **Album in another library**
in `preview-nlk` deliberately shares the album's document UUID; its single page
must stay scoped to its own document row. **Legacy unnamed document** has one scan and no stored
name, demonstrating the `Document <document_id>` name fallback on fresh previews.
`/scans` also includes **Unregistered scan collection**,
which has local media but no registered document and is absent from Documents.
The seed CLI prints `grouped-documents` and `unregistered-scan` links.

Existing document identities are retained. New registrations receive their fixture
titles; documents already seeded without names keep their nullable name and use the
UI's `Document <document_id>` fallback. Reregistration never overwrites a name.
The added scenario keys demonstrate names even in retained preview databases.
Integration coverage checks names, empty documents, library isolation, page cursors,
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
browser back/forward to compare pressed states, the page-specific
`page_link_state` URL setting and evidence. Workspace `link_state` is retained separately. Check the
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
The document table shows registered page counts, modification metadata and
annotation statistics in configurable columns. Click a document name to open its
scan list. The existing `document-preview-remainder` link now demonstrates a
six-page document through its Pages total; First page provides one
thumbnail, or open the name link to browse all six scans.

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

Pages appear in stored page-number order by default (#53), unknown numbers last,
or by page ID or last change through the strip's **Sort pages** control (#33),
12 per request. Pages without a stored number show the first eight characters of
their UUID, which are not page numbers. Links saved before #53 that relied on the
old page-ID default now open in page-number order. The gallery loads further batches until the current page
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
and archive ID; it does not invent annotation criteria. Source-view modification
user/key/date and link-state selections do not carry through (#109).
The repository test paginates all six pages and checks that selecting the importer
reduces the list to four annotated pages. Twice-run preservation retains the
unannotated page and its source/processing metadata.

The `scan-assignment-search` example opens scans for Irena's annotation review ledger.
Open its page, select a face and search for **Ada Novak** in the assignment panel.
Ada has evidence elsewhere and must remain available as a database candidate:
opening the scan must not silently add an evidence-source filter. Explicitly
selected annotation filters still apply. Repository coverage checks candidate
lookup, reassignment, local media and twice-run preservation of the review edit.

The stable `shared-filter-navigation` example searches for Irena within
preview-mzk. Opening her profile drops that library filter and shows her evidence
in both libraries. The **People** breadcrumb opens default People, including after
editing a profile filter. Explicit filtered profile links still apply locally;
reload and browser Back/Forward reproduce their URL state. Older `origin_return`
values never introduce a custom return link.

The `annotation-editor-filters` example opens Irena's profile with the importer
user and API key selected together, showing the three faces last changed by
that actor/key and excluding the separately verified face.

Search for **Irena Evidence**. This checkpointed synthetic identity has faces
and mentions in two libraries. **Annotation review ledger** (`preview-mzk`) has
an importer-created face and a reviewer-verified face; **Annotation review
correspondence** (`preview-nlk`) has a manual face and a verified mention.
Select a modification user, API key, date bound or document to follow the same
annotation criteria through Documents, People, profiles and scan lists. Opened scan pages retain
these criteria for navigation but show their complete page entities. Combining
criteria from different annotations must not produce a match.

Creation/import times and actors remain separate from annotation changes and
person/document processing. The seed uses real actor contexts and actual server
event times. Reruns preserve recorded creation, edits, assignments and checkpoints.
Internal fixture keys are stable for retained preview compatibility. Integration
coverage checks equivalent repository matches, unchanged times on rerun and
identical verification, plus upgrades from the previously deployed revision.

The `scan-annotation-hover` example opens the same ledger with all annotations
visible. Move between the automatic and verified face regions, transcription
mentions and Page faces badges: no annotation status/type tooltip should cover
content. State icons, accessible annotation names and selection remain available.
Check Enter/Space selection and mobile touch selection; use the link-state scan
examples for manual and unassigned faces. This entry point reuses existing local
media and stable records and leaves review edits and timestamps unchanged.

The `page-activity` example opens the annotation review ledger directly with
`panel=activity`. Its two faces and one mention have two importer edits and one
later reviewer verification. In the scan sidebar, choose Activity, then By user:
Preview reviewer summarizes the reviewer-verified face. These group headings
are informational and do not edit workspace filters. By day groups the recorded
annotation edits in browser local time. The default Faces tab contains the gallery, current face and assignment candidates.
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
Faces tab; compare Found faces below the linked overview and select linked faces
for verification/unassignment. Verify selected uses a green outline; Unassign
selected uses a red outline, with the same behavior in light/dark themes.
Existing source identities, records/media and
review edits are reused. The normal **People** breadcrumb opens the default list. Explicit copied filter
URLs populate the local controls; application links do not forward those filters. These entry points reuse existing
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

### Dragging from scan boxes (#112)

Open `scan-box-drag` (the **Viewport focus practice** page), zoom in, then press
inside a face box or OCR-line box and drag: the scan pans as it does from an
uncovered area, and releasing selects nothing, opens no actions and does not
refocus. Drag out of a box, or cancel a touch drag, with the same result. A click or
tap that moves less than 6 CSS pixels still selects the box, a face click still
opens its actions, and Enter/Space still activate a focused box.
`scan-box-drag-selected` opens the same page with the upper Ada Novak face selected
and its actions open. Dragging from the other faces or a line keeps that selection
and the actions, including when the toolbar is used after a touch drag.

These are report entry points to the existing fixture's three faces and two OCR
lines; no records, media, assignments or timestamps change. Integration coverage
checks that both links resolve to that page, that every face and line box has area
inside the stored page image and that reruns keep the links and face records.
From `people-gator-app`, `node scripts/check-box-drag.mjs` runs the browser checks
and captures desktop/mobile evidence against a running, twice-seeded instance;
set `BOX_DRAG_ORIGIN` and `BOX_DRAG_SEED_LOG` (the second seed run's output).

## Person sidebar statistics and Last change (#43)

The CLI's `person-last-change` link opens **Ada Review**, reusing the Link state
review fixtures. Her Statistics tab shows **Face annotations** and **Mention
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
(Mentions → Mention by occurrence count; expanded groups show their
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
choose individual **Modalities** or combinations in Similar people, and compare
its results on desktop and mobile. Found faces always uses faces and also finds `discovery-unassigned` for
manual linking. `discovery-zero-reference` and `discovery-zero-candidate` have no
embedding: since #134 the API and database refuse all-zero vectors, migration
`d34a021b0015` deletes stored ones, and that case is covered only by tests.

The seed integration regression queries each source through both repositories,
checks meaningful matches and finite scores, excludes faces without vectors as witnesses,
reads a real aligned crop, and preserves edited aliases/assignments on rerun.
Existing interrupted-checkpoint and edit-preservation checks cover the added keys.


PR #59 review follow-up: `entity-discovery-identifier` opens text-only discovery
for the existing unassigned face's `preview-seed/discovery-unassigned` identifier.
Its exact text hit has no invented face score and retains working local media.
The API still supports this indexed text query, but the person page now searches
Found faces only by face vectors. Legacy text/modality URL choices seed Similar
people and do not filter Found faces.
The seeded integration regression exercises this indexed identifier path as well
as name/alias input selection and preserves reviewed assignments on two reruns.
Use `entity-discovery` to inspect the removable nondefault Face model tag with
mobile settings collapsed; Clear filters resets sources/model while preserving
search and evidence choices. On disposable data, failed assignment/merge requests
retain their selection and point to the corresponding action for recovery.
Face text candidate retrieval is bounded to 200 per term per indexed field;
apply migration `d34a021b0012` before seed/startup to install its identifier index.



## View-local source and modification filters (#52, #109)

The stable `shared-filters-*` report links continue to demonstrate each view's
own-record predicates through explicit URLs:

1. `shared-filters-documents` finds **Shared filter ledger** last modified by
   **Preview curator**. Top-level People opens its default list. Open the separate
   `shared-filters-people` link to select the curator explicitly: **Ivo Ledger**
   and **Hana Ledger** match their own latest edits.
2. `shared-filters-api-key` also selects the curator key: Ivo remains; Hana's edit
   used bearer authentication. Removing the key changes only that view.
3. `shared-filters-person-faces` opens Hana under the curator selection. Her
   reviewer-edited face is absent until the modifier tag is removed. Changing to
   Mentions resets the filters rather than applying face criteria to mentions.
4. `shared-filters-page` selects only the ledger's first page. Top-level People
   and Documents reset that selection. `shared-filters-page-people` explicitly
   applies the page filter to People and finds Hana through her face.
5. A document's name link selects only its internal document UUID in Scans.
   **Shared filter mirror** in preview-nlk has a separate identity despite reusing
   the ledger's archive UUID; its unannotated page remains browsable.
6. Copy/reload a filtered URL and use Back/Forward to restore actual URL state.
   Ordinary application links always start fresh; mobile collapse preserves the
   current view's filters.

## Fresh destination navigation (#109)

Open `reset-navigation-documents`, `reset-navigation-scans` or
`reset-navigation-people`. Each explicitly selects preview-mzk. Click each
Documents, Scans and People navigation control, including the active section:
there must be no filter tags or inherited URL criteria at the destination.
Default Documents/Scans include **Shared filter mirror** and its local scan in
preview-nlk; default People includes **Lenka Vesela**, who has no linked evidence
and therefore does not match a library selection. Those examples are excluded by the source links' library filter.
Return through application navigation and check that old selections stay cleared.
The logo and People breadcrumb also reset; explicit document/page/person links
retain only their requested context. Capture desktop and collapsed-filter mobile
states, and inspect requests/counts as well as the URL.

This additive scenario reuses existing stable records and local media, adds only
report entry points and never rewrites assignments or processing timestamps.
Integration coverage compares default and scoped repository results for all three
collections, resolves the excluded page image and checks repeatable report links.

New fixtures and the `shared-filters-own-edit-v1` upgrade use stable keys. Before
editing Hana once, the manifest records her expected touch time; recovery checks
it and the reviewer actor. Reruns preserve intervening reviewer changes, evidence
assignments and modification times, even after an interrupted checkpoint.
Integration coverage checks own entity versus annotation actors, key distinctions,
source isolation, strict page-only source selection, non-page UUID exclusion,
unannotated pages, counts, reruns and interrupted recovery. The page examples
reuse existing linked synthetic records and local media; adding their report
links changes no persisted fixture IDs or review edits.

## Automatic list pagination (#62)

The additive `pagination-1` through `pagination-14` fixtures provide fourteen
people, registered documents and scans, linked by OCR mentions with generated
local images/layouts in `preview-pagination`. Existing fixture IDs, checkpoint
keys, assignments and reviewed media remain intact on rerun.

Open the CLI's `pagination-people`, `pagination-scans` and `pagination-documents`
links. Each searches **Pagination** across the twelve-item cursor boundary.
Clear search to try ordinary browsing; the library scope on scans/documents
keeps those lists at fourteen records. `pagination-scoped-scans` opens the
existing fourteen-page **Page gallery navigation** document.

The `pagination-browse-people` and `pagination-browse-scans` links reuse the
same fourteen linked records without text search. To check mobile spare-space
loading, open either link or its search counterpart at **390 × 12000** CSS
pixels. Both batches must load at scroll position zero, even though the results
section retains a minimum height of one viewport. The pagination marker follows
the cards inside that section, before its unused space. Repeat by opening at
**390 × 844** and increasing only the viewport height to 12000.

On desktop and mobile, scroll to the loaded list's end to append the remaining
results automatically. Increase viewport height to leave the end visible: the
next batch loads without scrolling. Resize or expand/collapse settings to check
layout re-evaluation. The manual Load more buttons remain available; after a
failed continuation, retry explicitly. Search, filters and sorting keep their
existing cursor reset and URL behavior.

Integration tests query both list and text-search repositories in twelve-item
batches, check distinct IDs, order, totals, exhausted cursors and document scope,
read a real page image, and preserve an edited person/unassigned mention on
rerun. Existing interrupted-checkpoint recovery covers the new fixture keys.

## Global Discover from a filtered URL (#67, #109)

Open the seed report's `global-discovery` link for **Zora Cartographer**.
The URL retains `preview-mzk`, **Entity discovery practice**, its first page,
Verified, Preview reviewer and the OCR API key. Discover still shows **Orion
Portrait** and two matching faces from **Discovery beyond the workspace** in
`preview-nlk`, including one unassigned face. Modalities starts at Faces
with the synthetic 8D model; name, aliases, text and sorting remain available.

The copied URL applies local criteria to the initial linked overview; switching
between Faces and Mentions resets those criteria (#109).
Found faces and Similar people below the overview search globally. On disposable
data, assign the outside unassigned face or merge the duplicate person. Candidate
navigation opens destinations without the original filters. All searches retain
normal API authorization. No optional face-scope control is introduced.

The `global-discovery-scan` link opens the reference page in face-similarity mode.
The right panel never inherits workspace predicates or renders workspace tags.
It shows entities on the current page, or searches text and face candidates across
all accessible data. Source, actor, API key, assignment and date settings remain
in a copied URL only; application links do not transfer them. Invalid workspace values do not
block the scan. The page toolbar's explicit annotation display setting uses
`page_link_state`, independently of the workspace's `link_state`.

Open `scan-page-entities`: Zora and her reference faces remain visible despite
retained Verified/reviewer/OCR-key criteria. Open `scan-global-text`: searching
**Orion** finds **Orion Portrait** in `preview-nlk` without selecting a face.
Clear the search to return to page identities. The stable
`global-discovery-scan-excluded` link retains attribution that would exclude its
reference in workspace browsing; the scan now shows that reference normally.
Adding `page=invalid` keeps the page panel and global search usable.

The additive document/page and two faces have new stable keys and generated local
media, reusing the existing reference model and duplicate identity. Reruns preserve
reviewed assignments, identity edits, processing times and checkpoints. Integration
coverage resolves both crops, finds the global candidates through repositories,
shows how source predicates exclude them, and verifies a second seed preserves edits.

## Deactivated reviewer attribution (#66)

Bearer requests authorize from signed token claims, including the persisted
user UUID (`uid`). Disabling a user stops login and refresh. An access token
already issued keeps writing as that user until it expires. The
**Deactivated reviewer ledger** (`preview-mzk`) shows the result: its OCR mention
links **Olga Expiry** and is attributed to **Preview former reviewer**. This user
is persisted inactive, has no API key and holds no usable credentials.

Open the `deactivated-reviewer` link. **Modified by: Preview former reviewer**
finds Olga through that mention. The editor filter still offers the
inactive user, and the mention stays attributed after a reviewer verifies it.

The seed creates the user inactive with stable fixture keys and no checkpoint
upgrade. Identity resolution never changes `is_active`, so reruns preserve an
administrator's later reactivation or deactivation. Reruns also keep reviewer
edits, assignments and modification times. Integration tests check the
attribution, the user and touch filters, edit preservation and both
`is_active` states across reruns. A separate HTTP test against migrated
PostgreSQL runs login, JWT-only requests, a mutation, deactivation, use of the
existing token, rejected login/refresh and expiry. Authentication must enter no
database context after login.

### Archive links (#75)

Open `filter_examples.archive-links-scan`: the header's **NDK**
link targets this exact page; the link beside **Document pages** targets its
containing document. Navigate a thumbnail and check that the header target changes.
Open `archive-links-faces` (Irena Evidence) for **Profile photo** and **Search hit**
indicators and a page link on each face. Open `archive-links-discover` (Zora
Cartographer, synthetic discovery model) for page links on assigned and unassigned
matches, including the `preview-nlk` document outside her reference library.
Links remain available while faces are selected. All targets come from canonical
source responses; synthetic archive UUIDs demonstrate target structure and do not
represent documents hosted by the external archive. These entry points reuse
existing local media, stable source identities and portrait choices without
rewriting any records on retained previews.

Archive badges read **NDK**, with **Digitální knihovna** in the hover tooltip.
On phones, the header badge shows only its external-link icon.
On Faces and Discover, the badge overlays the top-left of the thumbnail with a
nearly opaque theme background; selection remains at the top-right.

## Document table (#57)

Open `/documents?library=preview-table` (the `document-table` manifest
entry). **Document table ledger** has two registered pages, four faces and five
mentions including one direct document mention: three automatic, two verified,
two manual and two unassigned annotations, linked to just two distinct entities.
Its synthetic subjects are Tereza Columns and Oskar Rows. Its last change is
attributed to Preview face importer and its registered key.
The same archive ID in `preview-table-mirror` has no pages or evidence; Document
awaiting scans also demonstrates zero counts and unknown modification history.
Direct annotation ledger demonstrates a user-only modification without a key.

Documents uses the table only; the Items listing and view switch are removed.
Existing links with `view=items` or `view=table` also open the table. Search,
filters and server sorting retain their existing behavior. Each data field, including Document name, can be moved or removed from its header (click the chevron-marked name, then **Move left**/**Move right** or **Remove column**), added back from the last **Add column** column and reordered by dragging its header's top handle or pressing ←/→ on it. **Restore default columns** in the Add column menu resets fields, order and widths. Document
name follows First page in the default columns and opens its first registered page in the viewer/editor. There is no
separate Open column. With the name hidden, Document ID links to the same page;
when both are hidden, a compact library/ID link keeps navigation available.
The `document-table-unnamed` manifest link demonstrates the document-ID fallback
using the existing unnamed legacy document and its registered page.
The table uses document-wide counts even when evidence filters select matching documents. Scroll horizontally to reach
all fields and vertically to append cursor batches automatically; Retry remains
keyboard accessible after a failed batch. The **First page** column is shown by default, with a single thumbnail and a link to that registered page in the viewer/editor. The document response supplies its source
UUID in the same batched projection as the page total; enabling the column adds
only thumbnail requests, without page-list or annotation/name queries. Hidden
previews make no media requests. First means the first registered numbered page, with unknown numbers last and
source UUIDs breaking ties, independent of evidence filters.
No pages and unavailable media have short fallbacks. The
`document-table-first-page` manifest link opens the seeded two-page example;
both local page images are usable and repository/media tests verify its first page.


Sortable table headers (Document name, Library, Document ID, Pages and Last
modified), plus supported annotation counts, use the same server sort as the Sort selector. The separate icon button to the left of each label cycles no explicit sort → ascending → descending → no explicit sort. Clearing restores name ascending for browsing or relevance for text search. An arrow, action name and table sort semantics identify the active heading. The `document-table-sort` manifest link
opens the 14 pagination ledgers by name descending; reverse Document name and
scroll to verify ascending order across the cursor boundary. Relevance remains
available in the selector during text search. Unsupported metadata headings have no sort action.

The `document-table-scroll` link opens the 14 pagination ledgers. Scroll the
bounded table region: its header stays visible, and the horizontal scrollbar
belongs to the same region. Reaching its last row appends the next cursor batch
at any horizontal position. The earlier `document-table-page-header`,
`document-table-sticky-header` and `document-table-scroll-performance` links
remain aliases for this scenario.

The `document-table-unknown-names` link (also available as the older
`document-table-name-fallback` link) sorts `preview-mzk` by Document name.
The unnamed legacy document displays `Document 1c0b07a3-f413-518d-b5a2-1116ab58df00`
but its unknown name compares as an empty string: first ascending and last
descending, including across cursor batches and during search. The UUID label is
display-only. Its stored name remains null; reruns preserve this fixture and its
stable identity. Multiple unknown names tie-break by source UUID ascending.


Open `document-table-ndk-column` (the earlier `document-table-ndk-link` alias
still works). **NDK** is a default column after Document name (re-add it from **Add column** after removing it): a compact
source link with an external-link icon. Hover or keyboard-focus it for
**Národní digitální knihovna**; it opens the stored source URL in a new tab. It is
independent of the First page thumbnail, which links to the first scan. The
document-name column still opens the application's document page. The canonical
source and optional image belong to the same archive document, and reruns retain
existing identities and edits.

Open `document-table-annotation-groups` for the ledger and its empty same-ID
mirror in another library. The **Add column** menu groups counts under **Annotations**,
**Faces** and **Mentions**, each with All, Automatic, Manual, Verified and
Unassigned. Each count header shows its title with the mode in small text below,
for example **Faces** / *Manual*. The default columns show the three totals as Annotations / All, Faces / All and Mentions / All; choose additional state fields to compare them. Each header names its count independently.
The ledger has faces 4/1/1/1/1 and mentions 5/2/1/1/1 in that order, giving
combined counts 9/3/2/2/2. Counts include direct document mentions and every
registered page, even when evidence filters select the document. The mirror
has zero in every field. Switching columns adds no requests or local sorting.

### Detection actions (#49)

Open the seed summary’s `detection-actions` link, or **Detection action practice**
in `preview-mzk`. Its first page has an
unverified face linked to Lina Actions and an obvious **NOT A FACE** false positive.
Select either box to use the icon button group; hover an icon for its tooltip.
Link/Reassign, Unlink and Verify match the current-face card actions, which also
offer Delete. Amber identifies
Link/Reassign, emerald identifies Verify, and red identifies Unlink/Delete, as in the
card. Delete is available only with the
existing `people-gator:admin` scope and requires confirmation. Deleted fixtures
stay deleted on rerun; verifying or reassigning the linked face is also preserved.
Deleting a selected person portrait uses the existing automatic portrait fallback.

Scan and card Verify share one mutation and pending state. To check coordination,
throttle requests in browser developer tools, then verify the linked face from
either surface. Both action groups and candidate assignment buttons stay disabled
until the request settles; an error appears in both places and permits retry.
Assignment, new-person creation and deletion use the same pending guard.

Detection actions stay open while a face is selected, including while dragging
or zooming the scan; they stay inside the viewer even when the face moves offscreen.
A click outside closes them and keeps the face selected; click the box to reopen.
Escape clears the face selection. Selecting another face moves the actions to that
face. Arrow keys keep moving between faces and lines from a box or its actions.

### Person review (#80)

Open **Lina Archivist** (`person-review-faces` in the seed summary). Forty-two
linked faces span three documents; expand **Show all faces**, then inspect
**Found faces** and **Similar people** with `preview-synthetic-8d-v1` selected.
The candidate collection includes an unassigned face and Lina A.'s linked face.
Details retains aliases and the full description; Statistics holds review totals
and last-change information.

In Mentions, switch between **Flat**, **Document**, **Page** and **Mention**.
The 27 occurrences of `Lina Archivist` cover nine pages with automatic, manual
and verified links. Two documents deliberately share `Review ledger` as a title;
their source identities keep them separate. Select the exact-text group to verify
or unlink all filtered occurrences, including those beyond its first 20 children.
Found faces searches only by face vectors: face model precedes the assignment
filter, with no modality selector or text filter. Similar people has its own search, modalities and face model; its settings
stay independent from Found faces. Local evidence filters do not restrict either
global discovery search.

Unlink preserves the OCR mention. This page lists linked evidence only; assigning
an unlinked OCR mention remains available in the existing scan workspace.
New fixtures are additive and checkpointed independently, preserving reviewed
assignments and timestamps when the seed runs again.

The twelve `review-overflow-*` pages add 24 portraits to existing previews without
replacing earlier pages or annotations. At 1440px, Lina's collapsed overview shows
13 of 42 faces plus the **Show all faces** card in two rows; expansion shows all
42 faces. At 390px it shows three faces and the same action card. The last card
contains the matching-face count; `person-review-overflow-card` opens this scenario. Existing review edits and interrupted upgrades survive reruns.


### Found-face pagination (#80)

Open `person-review-found-faces` for Lina Archivist; the link explicitly keeps
all Similar people modalities while Found faces uses only face vectors. Found faces uses the same
portrait/card size as the linked overview: two initial rows, with **Show more**
as the final plus tile. Each activation reveals two additional rows and fetches
another cursor page when needed. The synthetic 8D model has more than one
14-record candidate page, including assigned and unassigned faces outside the
reference documents. Assignment filtering applies before pagination, so the
match count and loaded pages agree. Change the model or assignment to restart
the overview; previously loaded choices are not left selected out of view.

The seed integration regression walks assigned and unassigned cursor pages,
checks disjoint complete coverage and confirms the reference person's own faces
stay excluded. It reuses existing local media, models and checkpoint identities.

### Expanded and compact mentions (#80)

Open `person-review-mentions` for Lina Archivist's 27 occurrences, expanded by
default, or `person-review-compact` for the collapsed view. **Expand / Compact**
applies to the whole view and survives reload; group headings have no individual
expand controls. Expanded occurrences retain their separators except for the last item,
where only the outer group separator remains. Document, Page and Mention group
checkboxes select every matching occurrence, including the seven beyond the
first page. Deselect one child to see the group become indeterminate; selecting
the group again selects all children. Switching density retains selection.

Document headings include their library and stable source identity. Occurrence
context uses the application's newspaper-style serif font and orange underline, and the info icon opens the shared
two-line relative last-change/user display. These records already carry synthetic
actors and timestamps; the scenario adds a named link without replacing evidence
or resetting existing review edits. Seed coverage checks both cursor batches,
source/library labels, attribution and reseed preservation through repositories.

Select an occurrence or a compact group to open the same floating bottom action
bar used for Faces. It shows the selected mention count, **Clear**, **Unlink**
and **Verify**; grouped actions retain their complete filtered scope. The same
bar is available in Flat, Document, Page and Mention views. These interactions
reuse the existing 27-occurrence scenario and do not change seed identities.

### Shift-select mention ranges (#80)

Open `person-review-shift-selection` for nine page groups with three occurrences
each. Select a checkbox, then Shift-click another to add the inclusive range in
display order. Expanded ranges can span document/page groups and loaded cursor
pages; compact group ranges select every occurrence in those groups. Existing
selections remain selected. Clear, person/filter/grouping and sorting changes
reset the anchor; a Shift-click without an anchor selects just that item. The
same behavior works in Flat and Mention views, and updates tri-state parents
and the shared action bar. This scenario reuses stable records and local media.

### Mention loading layouts (#80)

Open `person-review-loading` with browser network throttling to inspect three
placeholder groups. **Expand** shows a checkbox/name/count header and two nested
source/context/info rows in each group; **Compact** shows only the headers.
Document/Page headings also reserve library/source space. Flat view and nested
occurrence requests use three matching row placeholders. Fetching another cursor
page keeps loaded records and appends two placeholders until the new records
arrive. Skeletons follow density changes during a pending request and expose one
loading status per list without interactive dummy controls. The existing three
documents, nine pages and 27 occurrences demonstrate all states with local data;
the seed adds a named link without modifying evidence or review edits.

## In-place identity face references (#41)

Open `identity-reference-faces` for **Reference appearances** in `preview-nlk`.
Hover **View faces** on Ada Novak's candidate card, or click/tap to keep it open.
The same control is available on the currently assigned identity. Only one
gallery is shown at a time: clicking another **View faces** replaces it, and
hovering other cards never replaces a clicked gallery. The shadcn
popover contains just a compact grid of faces with small margins; it has no
close button, title or count. Reaching the end of the bounded
scroll area automatically loads the next six-face batch, without a loading button.
Dismiss with Escape, a click outside or the View faces trigger, including after
clicking or scrolling inside the gallery.
Keyboard users can open with Enter/Space, Tab to the scroll area and scroll with
arrow keys. A failed continuation keeps the loaded faces and offers **Retry**.
Open `identity-reference-scroll` for **Zora Cartographer**: her 15 existing local
face crops exercise three cursor batches as the end sentinel comes into view.
The compact gallery stays free of titles and counters as batches append. This report link
reuses stable fixtures and does not alter embeddings, reviews or timestamps.

Ada has more than six appearances across pages, documents and libraries, with
manual, automatic and verified links. Reference membership uses only her exact
identity, independently of workspace filters and candidate search. Emil's faces
and similar unassigned faces stay excluded. `identity-reference-empty` finds
mention-only Nora Svoboda and demonstrates **No linked faces**. Browsing crops
preserves the selected scan annotation, viewer position and assignments.

The additive `reference-faces` document/page and three linked faces reuse the
existing synthetic identities, deterministic geometry and generated local media.
The added faces need no embeddings, so existing similarity-ranking examples stay
unchanged. Stable keys and checkpoints preserve earlier examples, review edits,
assignments and processing timestamps. Integration coverage traverses six-item cursor batches,
checks exact membership and cross-library sources, reads every aligned crop,
checks Nora's empty gallery and preserves a reviewed assignment on rerun.


`identity-reference-faces` also selects an assigned manual face for checking the
card's compact footer: **View faces** stays on the left, and icon-only
**Reassign**/**Link**, **New**, **Unlink**, **Verify** and (for admins)
**Delete detection** buttons are grouped on the right, each with a hover tooltip.
They follow the scan action bar's order, with the card-only New beside Link.
The row keeps one line, so linking a face does not change the card height. Verification errors appear inside the
card below the actions; verified attribution stays available on the state badge.

Action colors: sky for face references, green for verification/save, amber for
reassignment/linking, violet for a new identity, and red for unlink/cancel. Only button text, icons and borders
carry those colors; every action keeps the standard shadcn outline background.
Check both light and dark themes.

## OpenObserve RUM exploration (#94)

RUM is configured independently of fixture data; never store client tokens or
exporter credentials in the seed. Existing synthetic Documents, Ada Novak and
page/media navigation provide the linked requests for the
[trace-correlation walkthrough](../../docs/OPENOBSERVE-RUM.md#rollout-and-verification).
Filter OpenObserve by `env=preview`, commit version and `pr_number`, then inspect
an API resource and its backend trace ID. RUM introduces no database records,
relationships or media changes; fixture identities/checkpoints and rerun/edit
preservation remain unchanged. No external telemetry service is required to seed.

For session replay (#98), use the seed result's `openobserve-replay-person`
(Ada Novak) then `openobserve-replay-page` (her linked reference-faces page).
With RUM enabled and both backend sampling rates at 100, inspect the resulting
session replay in OpenObserve; page content remains masked. The journey reuses
existing synthetic linked face records and local page media. Repository/media
coverage verifies these links and rerun preservation after a review edit; no
additional records, credentials or external services are introduced by the seed.
See the RUM guide for backend configuration, new-session sampling and rollout.

### Annotation count controls (#78)

The additive `preview-counts` library contains Count study: faces (two pages),
Count study: tied faces, Count study: mentions and Count study: empty. It covers
all four link states, numeric ties, empty resources and faces-only/mentions-only
pages. Existing `preview-table` includes direct document mentions and two pages;
`preview-table-mirror` shares its archive document ID with zero annotations in a
separate library. Existing stable fixture keys and reviewed annotations are kept.

Open the manifest's `annotation-count-documents` example to combine manual-face
and total-mention minima and sort by verified All annotations. Open
`annotation-count-pages` to select pages with an unassigned face and order total
faces ascending. Inspect **Minimum annotations**, individual tags, document
count-column headers and sort selectors. Try zero, multiple minima, clear search,
clear all and Back/Forward; on mobile expand the filter toggle (Documents opens
its filter drawer). Assignment,
verification, unassignment and deletion update counts and matching results.

The count matrix integration test compares independent expected counts against
all fifteen sorts and minima on browse/search for both resources, traverses
cursors with ties and zeros, and checks response scope and constant query counts.
The recovery test edits/deletes these fixtures, reruns the seed, and recovers a
lost face checkpoint without replacing reviewed state, timestamps or identities.

### Page numbers (#53)

Open the page-gallery document: its 14 synthetic pages use stored positions
1–14 except page 9, which stays unknown. UUID order differs from numeric order;
the gallery loads multiple batches, placing the unknown page last. Cards,
document previews and scan detail show `n/total` with a dash for unknown values.
`total` counts registered pages in exactly the same library/document, regardless
of evidence filters. It does not assert the original archive document length;
gaps or partial imports can therefore show, for example, `10/3`.

Existing unnumbered synthetic pages receive a one-time additive numbering
upgrade, checkpointed before writing and guarded by their annotation timestamp.
The upgrade leaves last-touched time and modifier unchanged, as a fresh seed
would. Reruns preserve changed numbers and explicit clears, including after
interrupted writes. Page 9 remains a usable legacy/unknown example.

### People count ranges and sorting (#92)

The seed exposes `people-zero-faces`, `people-count-range` and
`people-count-scope` links. These reuse stable synthetic identities and local
media without modifying retained assignments: Lenka Vesela has zero evidence,
Emil Dvorak has faces only, Nora Svoboda has mentions only, and Mira Counts has
seven faces and three mentions across documents, with mixed assignment states.
The pagination people provide tied counts spanning several cursor batches.

Open **People**, set **Faces** minimum and maximum to `0`, and sort by
**Text mentions · Highest first**. Nora appears ahead of the tied one-mention
people; Lenka has explicit zeros. Try Faces `2` through `7` with Text mentions
maximum `3`, then **All annotations** in both directions. Choose Mira's
**Count study: faces** document and Faces minimum `7` plus Text mentions minimum
`3`: she still matches because totals cover the person, including other documents.
The mobile sliders button reveals both range controls; active tags remain visible
while collapsed. Repository tests traverse tied count orders, check exact/open
ranges and document-wide membership versus person-wide totals, repeat seeding,
and exercise evidence transitions. Existing edit-preservation and interrupted
checkpoint tests continue to protect retained previews.

### Stable document column widths (#93)

Open the `document-table-widths` manifest link. It combines 14 unchanged
pagination ledgers and the two-page annotated table ledger with two additive
fixtures: `table-width-short` (title **A**, no pages) and `table-width-long`
(a long title with an uninterrupted archive reference, a long library label,
and a local page image with an Ada mention). Existing identities, checkpoints,
reviewed assignments and last-processing timestamps are preserved on reruns.

Sort Document name in both directions, then enable Modified by,
API key and the face/text-mention count groups. At desktop and mobile sizes,
column boundaries have vertical separators and widths stay constant while full titles and other long values wrap
inside their cells; row heights grow with the text. The title width is 320 CSS
pixels. All widths use the same fixed pixel policy at every viewport; unused
parent space is left blank and excess columns scroll inside the keyboard-focusable
table region. Hiding/restoring fields preserves every column's configured width.
Drag the grip at a leaf header's right edge to resize that column with mouse or
touch. Focus the grip and use Left/Right (10px), Shift+Left/Right (40px),
Home/End (bounds), or Enter (that column's default); double-click also restores
one column. Titles can range from 200 to 720px. Other columns retain readable
header minima and purpose-specific maxima. There is no bulk width-reset action; use each header grip to restore its width. Width choices survive row changes
and hidden/restored columns. Column visibility, order and resized widths persist in localStorage across reloads and browser sessions on the same origin. Existing tab settings migrate once when no durable setting exists; malformed or unavailable storage falls back safely without disabling controls.

Scroll horizontally to the middle/far right and vertically to the final row to
load the second cursor batch automatically; keyboard scrolling of the focused
table reaches it too. Search/filter/sort URLs and counts retain their existing semantics.

### People count states

Open `people-count-states` for Mira Counts with at least three manual faces and
one verified mention, sorted by verified annotations. Her seven faces comprise
two automatic, three manual and two verified links; her three mentions include
one of each state. The combined verified count is three. Switch each range's
state selector between All, Verified, Manual and Automatic, combine bounds and
remove tags. `people-zero-verified` demonstrates exact zero verified evidence
and automatic-face sorting, including people without evidence.

These links reuse preserved mixed-state fixtures and local media. State-count
repository tests traverse all twelve orders in both directions and cursor batches,
compare exact ranges to batched statistics, retain person-wide counts under
source/state membership filters, and verify that reviewed assignments survive a
second seed run. No preview edits or checkpoint identities are reset.


## Teleprompter reading practice (#36)

The additive **Teleprompter reading practice** document (`teleprompter`,
`preview-mzk`) has a 40-line page (`teleprompter-1`) and an additive wrapped-line page (`teleprompter-wrap-2`). Ada Novak's automatic
mention repeats on L3, L16 and L29 and spans L33–L34. Viktor Marek's verified
mention is on L10 and L25 and Nora Svoboda's manual mention is on L20. The other
lines stay unannotated. One unembedded Ada face sits beside the text.

- Open `teleprompter` for full text. Select **Annotated** to collapse the
  unannotated lines. Each hidden gap is a band showing its line count. Its
  gutter buttons reveal 5 lines below the passage above or above the passage
  below. A gap of 5 lines or fewer has one button that reveals it all.
  Revealing lines switches to **Custom**, which keeps exactly the shown lines;
  choose **Annotated** again to collapse them.
- Open `teleprompter-person` for Ada's lines (L3, L16, L29, L33–L34) with
  original numbers. Select Viktor's mention or the Ada face to change the person.
  Arrow keys step through visible lines only. Reveal 5 lines below L8 (the view
  becomes **Custom**), then select Viktor's mention on L10: the lines and scroll
  position stay put. Choose **Person** to see Viktor's lines (L10, L25).
- Open `teleprompter-annotated` (Annotated with **Verified**): only Viktor's
  verified lines L10 and L25 are shown. Add **Manual** to include Nora's L20; with
  no state chosen (**All**), every annotated line returns. In Person mode the
  states narrow the person's own mentions, so Ada with **Verified** is empty.
- The page-scoped minimap on the right grays hidden lines and colors highlighted
  mentions. Click a gray gap to center the nearest passages without revealing it.

The layout uses its own ordered lines with compact geometry inside the page,
which leaves existing fixtures unchanged. New stable keys add the page, face and
three mentions to retained previews. Reruns keep reviewer reassignments and page
processing times. Integration tests resolve each identity's lines through the
media services, including the two-line Ada span. They also check face and line
geometry, preserve a reviewed reassignment across reruns and recover an
interrupted upgrade checkpoint.


### Teleprompter review regressions (#36 / #101)

Open `teleprompter-wrapped` for a second page of the reading-practice document.
Its first OCR line is deliberately long enough to wrap across several rows on
phones. Reduce the vertical split to about 20% with the resize handle to make
that line exceed the text viewport. Page Down and Page Up traverse every visual
portion before moving to another original line. L2 links Ada Novak, and all original line IDs are retained.
The local scan fits the synthetic text inside its OCR polygon without external
media or inference. The scenario is additive: reruns preserve the existing
practice page, identity links, processing metadata and reviewer edits.

On either practice page, resize the workspace through 1024px and back several
times. The same scan stays mounted, pan/zoom continues working without reloading,
and each orientation restores its own chosen split. A genuinely replaced scan
gets fresh element-owned resources while retaining the view for the same page;
new pages and Reset return to the default view. Mentions have tighter padding and
thin outlines while keeping the blue selected/orange person states and state
underlines. Test both a phone-sized panel and a wide panel, including wrapped names.

### People search merge (#107)

Search People for **Rina Merge** to find three synthetic duplicate records, each
with an alias, a local portrait and a text mention on **Search merge practice**
(`preview-merge`). With admin permission, select two or three records and use
**Last selected (name)** or **First selected (name)** to merge immediately. The named
person survives and receives the sources' faces, mentions and aliases under the
existing API rules. Try each action on a fresh disposable preview.

For stale-record recovery, open `people-search-merge-paginated` from the seed
manifest and load more people until the Rina Merge records appear. Select all
three, delete one source in another tab, then try merging into a remaining Rina.
The failure refreshes all loaded pages and removes the missing selection while
keeping the other Rina records selected in their original order for retry.

Selection includes only explicitly selected, loaded results. Loading more adds no
selection. Shift appends an inclusive range in display order, retaining the order
of already selected IDs (even for a backward range). Sorting retains that order
for records still in the loaded results; unavailable records drop out. Search,
filter or cursor changes clear selection. Deselect/reselect appends a person to
the end; Clear resets the order. Pending requests freeze selection and use a
snapshot. Failed requests preserve available selections for retry. Seed reruns
keep merged source IDs as tombstones and preserve evidence reassignment and edits.

The selected-person toolbar floats at the bottom like the person-detail face
and people toolbars. Scroll the Rina Merge results on desktop and mobile to
check that the count, merge actions, Clear and pending/error feedback stay visible.
This layout uses the existing scenario; no fixture or persistence upgrade is needed.

Rina Merge cards share the person-detail corner checkbox and selected border/fill.
Start with a checkbox, then click cards to add people. Clicking a selected card
keeps it selected; only its checkbox removes it. Shift-click either control to add
a range, and Clear restores card navigation. Existing linked fixtures demonstrate
these interactions without a fixture or persistence upgrade.

### Documents navigation and column defaults (#111)

Open `document-table-navigation`. It combines the existing table ledger (2 pages,
2 distinct linked people, 9 annotations = 4 faces + 5 mentions), width examples and
14 pagination ledgers with two additive `preview-table-navigation` documents:
**Navigation: no pages** and **Navigation: missing preview**. The latter has a
registered page without stored image media; its first-page link still opens the
scan result. No existing fixture, assignment, timestamp or checkpoint is reset.

A fresh tab shows First page, Document name, NDK, Library, Pages, Linked entities,
Annotations, Faces and Mentions in that order. The Library link opens Documents
filtered to that library; the document name opens its first page; First page and the document name open the viewer/editor on the canonical first-page source. Documents with no registered pages still open their empty scan listing. The last column is **Add column**:
it fills the remaining table width (at least 160px), its sticky header stays readable while rows
scroll, and clicking any of its cells opens the header menu of hidden fields, grouped by Document
fields, Annotations, Faces and Mentions. Choosing a field appends that one column last
and closes the menu. Drag a header's centered top handle to reorder columns (touch works on mobile); ←/→
on the focused handle moves one position. Clicking a header's chevron-marked name opens a menu
with **Move left**, **Move right** and **Remove column**; Escape closes it without removing. The document-link fallback that
replaces a removed name cannot be removed. Visible fields, order and widths persist in localStorage,
including reload/navigation back and new browser sessions. **Restore default columns** restores the nine fields, order and widths; unavailable/invalid storage recovers
safely. Widths remain fixed at every viewport: title 320px, preview 120px,
library 200px, Pages 120px, Linked entities 144px, All annotations columns 168px, Mentions columns 144px, Faces columns 128px and
optional NDK 80px. Each header has a full-height sort strip on its left with a centered
icon; the move handle is centered at the top of the remaining width with the content-width
name centered below it, and the resize grip spans the full height on the right.

The Documents view uses the available content width. It has no footer, page title or subtitle; only the small **Documents index** label precedes the search panel. On desktop (1024px and wider), the table fills the entire remaining viewport height below the filters. On mobile, the table section occupies the viewport below the sticky top bar, so the bar never covers the table header; the label and filters are reachable by page scrolling. There is no Load more button: reaching the last row loads the next batch. The standard shadcn-vue ScrollArea provides both scrollbars around the sticky table header without growing page width.
Choose extra fields and scroll vertically at left, middle and right positions;
the loading sentinel remains visible across the horizontal content. Counts retain
full-document semantics, including unassigned and direct document evidence.

Use the separate header icon buttons with mouse or keyboard to cycle no explicit
sort → ascending → descending → no explicit sort. The shared selector, URL and
Back/Forward follow the same server order. Clearing returns to name ascending
for browse and relevance for search. The new seed integration scenario checks
cursor batches, totals, media/link identities and additive rerun/edit preservation.


The `document-table-first-page-editor` example links directly by the first page's
stable source UUID. The application resolves its archive identifiers on navigation
and opens the existing viewer/editor without listing all pages or prefetching
page metadata per document row. Document name/ID/fallback links and First page
use the same destination; missing image media does not prevent opening the editor.
A failed metadata lookup offers Retry page and a Documents link.

While the next document batch is loading, a standard shadcn Skeleton row appears
after the loaded rows, aligned with the visible columns. Existing rows remain
usable; the skeleton disappears after success or failure, and the existing retry
control handles failed requests. Loading, error and empty states appear inside
the table's scroll area.

### Documents filter sidebar and count ranges (#111)

Documents shows only the **Documents index** label, search and Sort above the
table. Filters are in a left sidebar from 1024px; below that, the sliders button
beside search opens them in a left drawer (Escape or × closes it and keeps the
selections). Applied-filter tags and **Clear all filters** follow the selectors in the
sidebar; on mobile they stay under search so they remain visible with the drawer
closed. The filters are Libraries, Modified by, Modified via key, Modified
from/to, and **All annotations**, **Faces**, **Text mentions** and **People**.
Each count button opens State (All, Automatic, Manual, Verified, Unassigned),
Min, Max and Apply; People has Min and Max for distinct linked people. Links
that still carry Documents, Pages, link-state or Unassigned faces parameters
apply them and show removable tags.

Open `document-filter-ranges`: faces 1–4 and exactly two people leave only
**Document table ledger** (4 faces, 2 linked people). Open
`document-filter-no-people`: People ≤ 0 lists the mirror and both navigation
documents, which have no evidence and therefore count as zero. The links reuse
existing fixtures; no record is added or reset. The seed integration test checks
both links through repository list and search queries, inclusive bounds and the
count-sorted path.

### Top-bar document and page breadcrumbs (#114)

The seed result and CLI provide five direct page links: `breadcrumb-named`
(Page gallery navigation, Page 1), `breadcrumb-missing-number` (the same named
document with an unknown page number and a deliberately missing scan), `breadcrumb-unnamed` (document UUID,
Page 1), `breadcrumb-unregistered` (unregistered parent UUID, Page 1), and
`breadcrumb-long-name` (the long synthetic catalogue title, Page 1).
`breadcrumb-person` also opens Ada Novak's profile, whose last breadcrumb shows
her name instead of the person UUID.
These reuse stable linked fixtures and local page images; no records are reset.

Open each link to inspect the persistent top bar. Available names and numbers
replace their UUID labels and tooltips independently. Follow the document
breadcrumb to its scoped scan list, switch pages and use Back/Forward.
On disposable data, edit a page number or rename Ada and verify that the
breadcrumb updates. Reseeding keeps such edits, and other scenarios use Ada.
At narrow widths the full document name remains available through the link's
accessible text and title while the visible label truncates. The seed integration
test resolves every link through repositories, checks metadata and local media,
checks the intentional missing-scan response, then reruns the seed and verifies preservation of an edited number and timestamp
and a renamed person.

## Scan sidebar practice (#103, #137)

The additive **Scan sidebar practice** document (`scan-sidebar`, `preview-mzk`)
has four pages. Page 1 (`scan-sidebar-1`) holds two of Hana Sidebar's faces, one
unassigned face, Hana's repeated phrase (automatic, verified and one unlinked
occurrence), a four-line mention of Hana with long context (#121) and a
text-only mention of Tomas Lettered. Pages 2–4 hold 36 small
faces of Karel Crowd (every fourth unassigned), Rosa Elsewhere's single face and
21 further Hana occurrences, so document scope exceeds the 30-face and
20-occurrence sidebar batches. Dora Document has one direct document mention
(`sidebar-direct-mention`) and no page evidence.

- Open `scan-sidebar-people`. Empty People search defaults to **This document**:
  Hana and Tomas (this page), then Dora, Karel and Rosa (the rest of this document).
  Dora demonstrates direct document membership; Tomas is mention-only.
- Type **Hana** (or open `scan-sidebar-global-text`) to switch automatically to
  **All people / Similarity**, including Hana Ledger outside this document.
  Clear the final text/face input to restore document-only contextual browsing.
  An explicit scope/sort choice remains in effect while refining an active search;
  `scan-sidebar-document-only` demonstrates a copied, explicitly document-scoped search.
- Open `scan-sidebar-card` to see Hana's tag expanded into the details card.
  Choose **Search** (magnifier): the face is attached to People search, Similarity
  sorting and **All people** are selected, even from a locally scoped search. Remove the face with its ×.
  `scan-sidebar-face-search` opens that state directly.
- Open `scan-sidebar-faces` for document faces grouped by person, with
  **Unassigned** last. Scroll to load the next batch; faces on other pages open
  their page with the face selected.
- Open `scan-sidebar-mentions` for document mentions grouped by phrase. Hana's
  group lists 25 occurrences, including the unlinked one, and loads further
  occurrences while scrolling. Switch **View** to **Group by person** for Hana, Tomas and
  **Unlinked**, or to **Flat** for one list.
  Select a mention's text to select it in the transcription and on the scan;
  one on another page opens there. The unlinked caption selects its line.
- Open `scan-sidebar-info` for this page's statistics, last change and the
  latest recorded change of each face and mention.

New stable keys add the sidebar people, document, pages, faces and mentions to
retained previews. Reruns keep reviewer reassignments and timestamps.
Integration tests check page/document membership through faces or mentions,
person-grouped face batches, phrase groups with unlinked occurrences, face and
combined name/face search, global relevance pagination, direct-document-only
membership and unlink preservation, local media and aligned crops,
additive upgrade with an interrupted checkpoint, and review preservation.

## Resizable scan sidebar and wrapping mention context (#121)

`scan-sidebar-1` also holds `sidebar-hana-long`: an automatic mention of Hana
Sidebar whose context spans four OCR lines and ends with the unbroken token
`ParishLedgerBaptismMarginNoteGodparentsCeremony1888`.

- Open `scan-sidebar-mentions` on a screen at least 1024px wide and choose
  **This page**. The long context wraps over several lines, and the long token
  breaks instead of overflowing the panel. Select the text to select Hana's line
  in the transcription.
- Drag the handle between the workspace and the sidebar, or focus it with Tab
  and use the arrow keys. The sidebar is 400px wide by default, between 320px
  and 800px, and the workspace keeps at least half the width. The width is
  remembered in this browser. The transcription/scan handle still works.
- Below 1024px the sidebar stays below the workspace without a handle.

Retained previews gain the mention through its stable key. Their stored
`scan-sidebar-1` image and layout are replaced only while they exactly match the
media generated before #121, so the new lines appear on the scan and in the
transcription; replaced media is kept. Integration tests check the stored
context, its layout lines, Hana's highlight, the media upgrade, preservation of
replaced media and rerun stability.

### Page panel layout (#139)

Open **page-panel-layout** to review the existing synthetic scan-sidebar page,
Hana's linked face and text, local media, selected-person transcription mode and
document-scoped Mentions. On desktop, hide buttons sit on the edges facing the
viewer: transcription on the right of its header, People on the left. Reopen
from the corresponding viewer-header control. Panels retain settings and saved
expanded sizes; Link/Reassign and face Search reveal People when needed.

Below 1024px, People remains visible below the viewer. Transcription collapses
upward into a single **Transcription** bar, which also reopens it. Try a desktop
→ mobile → desktop round trip with People hidden: the mobile section remains
available and returning to desktop retains its previous visibility and width.
Open **page-panel-layout-expanded** to repeat the same checks beside the
expanded page browser, then collapse the browser to restore the live viewer.

Hidden/open state is local to the mounted workspace. Both links reuse stable
existing evidence and local media; the seed test checks those relationships,
media access, exploration URLs and preservation of a reviewed face edit on rerun.

### Bottom page-strip review (#131)

Open `page-strip-review`, or **Page strip review practice** in
`preview-page-strip`. Its 18 pages include Nora Page's assigned face (2), her
mention alone (3), mixed assigned/unassigned faces (4), Otto Page's face (5), an
empty page (6), and more Nora mentions (7–18). Pages 1 and 4 contain unassigned
faces for review practice. Every page has deterministic local scan/layout media.

Select **Nora Page** in the right panel, or open `page-strip-selected-person`.
Her pages get a single orange outer border while all pages remain visible.
Enable **Nora Page only**, or open `page-strip-person`, for 15 matching pages
across two batches. Turn it off to restore all 18 pages. The current scan stays
open when excluded by the filter. The compact strip shows no annotation counts.

Open `page-strip-current-assigned` (page 2) to compare the current page's double
orange border with the single outer border on Nora's other pages. Page 3 matches
through a linked mention alone. The same document UUID in
`preview-page-strip-mirror` demonstrates library isolation.

On disposable data, assign page 1's face, unlink page 3's mention, or delete page
2's face and inspect highlight/filter membership. Seed tests exercise repository
queries bounded by loaded source IDs, local thumbnails and rerun preservation of
assignments, unlinked mentions, deleted faces, source timestamps and stable IDs.
Existing interrupted-checkpoint recovery coverage remains in place. These are
additive examples and retain older page-gallery media and records.


## Expanded document-page browser (issue #140)

Open `document-page-browser` from the seed report, or choose **Expand pages**
in the bottom strip. The central viewer area becomes a vertically scrolling
thumbnail grid, ordered left to right and then down. **Collapse pages** restores
the viewer; opening a thumbnail also returns to that page's viewer. The side
panels keep their state. `pages_view=expanded` restores this mode after reload
and through Back/Forward, including links through `/pages/:pageSourceId`.

The scenario reuses the stable 18-page **Page strip review practice** document
from #131. `document-page-browser-person` starts with Nora Page's person-only
filter: face-only and mention-only matches remain highlighted/filterable across
two cursor batches while the excluded current page stays open. Sort, selected
person and person-only state carry into the selected page. Source membership and
current-page outlines retain the strip's single/double orange distinction;
there are no annotation counters.

`document-page-browser-missing-media` opens the existing registered page without
media in expanded mode, to check the **No preview** fallback and navigation.
The new links add no records or checkpoint identities. Seed integration tests
resolve their source/page targets, inspect cross-batch membership and local
thumbnail media, and preserve a reviewer's page-number edit on rerun.


### Document-first entry and retired Scans search (#141)

Use `document-browse` to open the expanded page browser for the existing 14-page
navigation document. `document-browse-empty` opens a registered document with no
pages, showing its actual title and a Documents link. `document-browse-unregistered`
resolves a source archive containing a stored page even when no parent document
record exists. Every example uses deterministic existing records and local media.
No fake first page is created for an empty or unavailable document.
The empty-document link is added only when its fixture is present, so upgrading
an older preview without that example remains valid.

The standalone Scans screen and cross-document scan-search UI are retired.
Documents and People are the top-level destinations. Page breadcrumbs return to
that document's expanded browser; person mention document groups retain the
selected person. Direct page URLs remain valid. Existing `/scans` fixture links
are retained as compatibility examples: a single document resolves to its browser,
a single page resolves to the viewer, and global/ambiguous queries return to
Documents without transferring retired search/filter criteria. They no longer
load a Scans component. The backend search API remains unchanged.

Repository/media tests verify document identity, all 14 registered pages, the
empty count, orphan page media and stable entries/source metadata on rerun.

### Page, document and database source tags (#138)

Open `scan-source-tags`. Hana Sidebar has linked faces and mentions on the
current page, while Tomas Lettered has only a linked text mention: both use the
double-orange **Page** tag. Rosa Elsewhere and Karel Crowd belong to sibling
pages and show a single-orange **Document** tag. People from other documents
show the neutral gray **DB** tag. The tag sits directly below each portrait;
selecting a person is still indicated separately by the card's selection outline.

Open `scan-source-tags-text`, `scan-source-tags-face` and
`scan-source-tags-combined` to compare text-only, face-only and combined scores
below the source tag. Face scores are cosine similarity expressed as a
percentage (not probability), converted from the existing cosine distance; text
scores keep their existing scale and are labeled separately. A pending or
unavailable membership lookup shows **Unknown**, never a premature DB label.
Membership is checked in bounded page/document queries independently of loaded
or filtered face/mention batches. Existing portrait browsing, preview, profile
and assignment actions remain independent.

The seed test checks face-or-mention membership through repositories, sibling
versus outside-document context, local page/crop media and preservation of a
reviewed unlink and page metadata on rerun. These links reuse stable existing
fixtures without modifying their reviewed evidence.

### Persistent document layout (#142)

Open the `document-table-persistence` manifest link. It reuses the stable width
fixtures: short/long document titles, a document with a registered page and local
image/mention evidence, empty documents and enough rows for cursor loading. Add a
column, remove another, reorder the headers and resize Document name with its
right-edge grip (keyboard arrows also work). Reload, open another tab or restart
the browser on the same origin: visibility, order and widths remain. Sorting,
filters and pagination do not reset them. **Restore default columns** resets all
three and the reset survives reload. Blocked/full storage keeps the controls
usable for the current view. Existing sessionStorage choices migrate only when
there is no corresponding localStorage preference; browser-local layout is not
stored per account or shared between browsers/origins.

The parametrized width/persistence integration scenario checks both manifest
entries through repository queries, multi-batch traversal and actual page media,
then confirms reviewed document/mention state survives reseeding. Browser
layout storage is exercised separately by frontend tests and the maintained
`check-document-persistence.mjs` browser check.

## Page verification (#149)

Two synthetic documents in `preview-verification` show page verification and
the document state derived from it. The reviewer verifies three pages once:

| Document | Pages | Derived state |
| --- | --- | --- |
| Verification: all pages verified | page 1 (with an unassigned face), page 2 | Verified, 2 / 2 |
| Verification: in progress | page 1 verified; pages 2 and 3 not verified | Not verified, 1 / 3 |

- Open `document-verification`, then show the **Verification** (green
  Verified / grey Not verified label) and **Verified pages** (progress ring and
  count) columns. `document-verification-not-verified` applies the
  **Verification: Not verified** filter.
- Open `page-verification`: page 2 of the in-progress document with the info
  panel open and the page strip set to **Not verified**. The top bar shows the
  document's progress ring (1/3), **Verify** and previous/next page. Verify,
  press next, verify page 3: the ring reaches 3/3 and the document becomes
  Verified. The green **Verified** button's menu shows who verified the page
  and offers **Remove verification**.
- Page 1 of the first document is verified while its face stays unassigned:
  page verification never changes evidence link states.

Reruns add missing pages and verify each listed page only once. A checkpoint is
saved before each write, so an interrupted run resumes without re-verifying a
page a reviewer has since changed. Integration tests check the derived states,
counts, filters, the example links, rerun preservation of a removed verification
and checkpoint recovery.
