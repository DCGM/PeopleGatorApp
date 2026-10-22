# Issue #58 discovery evidence

Captured from the production Vite build against an isolated, migrated PostgreSQL
store and synthetic local media. The migration → seed → seed → schema-check CLI
sequence passed before starting the API and frontend. No external inference or
private dataset was used.

Each state has desktop **1440 × 900** and mobile **390 × 844** captures:

- `all-inputs`: compact entity discovery with all reference inputs; mobile settings
  start collapsed while search remains available.
- `input-choices`: open Reference inputs combobox; mobile settings expanded.
- `faces-only`: selected source tag, compatible matches and finite face scores.
- `aliases-only`: recorded-alias inputs and text matches, without fake cosine scores.
- `no-signal`: real API 422 from a faces-only model without compatible reference
  embeddings, with source controls and Retry available.

Real Chromium checks at both viewports covered keyboard opening of the settings
and source chooser, selection of faces/aliases/name and combinations, selected
values in URLs and API requests, mobile collapse preserving source values/tags,
individual tag removal, empty-input guidance, clearing sources while retaining
search and evidence state, and retry/recovery from the no-signal error. Every
observed discovery request used the entity contract without enumerated face IDs.
The rendered pages had no horizontal overflow or browser JavaScript errors.

Automated component tests additionally cover assignment/merge selection, source
removal/reset and error retry; query tests check cursor/cache reset when changing
or revisiting source choices and entity IDs. Browser captures supplement those
checks and do not assert visual equivalence to the unavailable reported dataset.

The [numerical reproduction](numerical-reproduction.md) records actual before/after
HTTP results for both endpoints using the reviewed main scoring/routes and the
synthetic zero-vector fixture.

## PR #59 review follow-up and main integration

All screenshots were refreshed from the production build after merging `main`
`7597415`. The original five states retain desktop **1440 × 900** and mobile
**390 × 844** captures; the current shared evidence controls are included.

Additional matching desktop/mobile pairs:

- `model-tag`: all reference sources selected, a nondefault Face model visible
  as an active tag; mobile settings remain collapsed.
- `assignment-failure`: the selected unassigned face remains selected, with
  assignment-specific recovery text and the Assign action available.
- `merge-failure`: a temporary synthetic person remains selected, with
  merge-specific recovery text and the Merge action available.

The two failure states use one browser-intercepted HTTP 503 response per action.
The second click goes through to the real local API and succeeds; the action's
error clears. The unassigned face is restored after the check; merge uses a
new temporary synthetic person rather than deleting a maintained seed fixture.
These captures demonstrate recovery behavior, not a spontaneously failing server.
No screenshot uses mocked rendering or private data.

Chromium checks at both sizes passed: keyboard model-tag removal updates the URL
and requests, the model tag is visible with all sources selected/mobile settings
collapsed, Clear filters removes source/model overrides in one navigation while
retaining text/library/assignment settings, failed actions preserve selections,
and actual second assignment/merge requests succeed without a search-retry alert.
The original compact-request/source-choice/no-signal checks also passed after the
merge. No browser JavaScript errors or horizontal overflow were observed.

Backend review coverage checks a catalogue with more than 200 faces for each text
path, filters before candidate limits, unassigned identifier-only matches, and
real PostgreSQL query plans using all three GIN indexes (sequential/ordinary
index scans disabled for the tiny plan fixture). Final scoring and aggregation
remain unchanged. Migration `d34a021b0012` supplies the identifier index. The new
`entity-discovery-identifier` seed link exercises that path with existing local
media and survives reviewed assignment/alias edits on rerun.
