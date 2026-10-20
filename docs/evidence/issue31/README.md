# Issue 31 browser evidence

Actual local application captures using the synthetic PostgreSQL preview seed,
with API/Vite running from this issue branch. No private data or credentials are
shown. Desktop viewport: **1440 × 900 CSS pixels**. Mobile viewport:
**390 × 844 CSS pixels**. Screenshots capture the full page at those viewport
widths; their image heights vary with content. `*-expanded-mobile.png` shows the
below-640px Collapsible opened in list/profile/discovery panels; unsuffixed mobile states show collapsed filters.

| Capture | State |
| --- | --- |
| `people-*` | Shared evidence filters in people search; origin text retained |
| `documents-*` | Documents containing the same Verified, Authority evidence; separate document processing bound |
| `scans-*` | Matching registered page scope and preserved processing context |
| `profile-*` | One matching face of four overall, with one clear-all action, active evidence controls and a named return breadcrumb |
| `provenance-*` | Recorded identity provenance and compact face last-change attribution |
| `mentions-empty-*` | Accessible Mentions tab, filtered zero and recovery |
| `activity-time-*`, `activity-user-*` | Sidebar Activity tab groups faces/mentions by annotation edit day or last user; clicking groups filters the scan |
| `cards-*`, `cards-detail-*` | Compact cards: assignment icon/state and confidence below the photo, colored library/document row and adjacent change/user rows; source navigation and plain editor names |
| `statistics-*` | Dedicated Statistics tab with page/document totals, no disclosure |
| `page-*` | Same annotation highlighted in its source workspace; URL criteria retained without a filter panel |
| `discovery-*` | Assigned-elsewhere discovery choice, independent of assigned-evidence state |
| `people-dark-*` | Standard controls and active tags in dark theme |

Executed browser checks in Chromium at both widths:

- People → profile → source page → profile, and Documents → matching scans →
  source page → profile retain active evidence criteria and correct scope.
- Source processing bounds remain in the saved return URL; shared annotation criteria populate the actual profile controls. Raw origin metadata is not rendered as chips.
- The scan workspace has no added filter panel/tags; it keeps the existing compact toolbar, with shared criteria applied and forwarded through its URL.
- Reload, Back/Forward and direct URLs reproduce the selections/results.
- Individual evidence-tag removal updates the URL; one clear-all button is
  rendered alongside active criteria and preserves originating text/return URL.
- Mobile filter toggles start collapsed, expose `aria-expanded`, open via Enter
  and retain selected tags while collapsed. Expanded controls remain usable.
- Discovery assignment changes are serialized separately from annotation states.
- No document-level horizontal overflow or browser JavaScript errors occurred.

The fixture authority is synthetic and its reference uses `preview.invalid`;
no external authority was contacted. Inference services are not required.

Additional Activity checks at both viewports: day/user group selection updates
annotation URL predicates and the scan’s visible annotations; groups retain all
page records, copied URLs restore the Activity/By user tabs, and clearing removes
only time/user selection. Recorded editor attribution is independent of owner,
verifier and page/document processing metadata.

PR #37 review follow-up captures also check top-level pane tabs, independently
scrollable Activity in a 1440 × 450 CSS viewport, copied Activity/Statistics URLs,
keyboard tab activation and equal card dimensions at both standard widths.
Cards now use the compact Discover presentation; source navigation still
selects the correct face without rendering raw IDs or matching labels. The source breadcrumb retains enough mobile width to be
readable. Authorized users can select faces to verify their links using the API's actual `scopes` JWT
claim. Editor names are plain text pending a future user tab. The full
people/profile/scan and documents/scan/profile journeys were repeated after
removing origin chips; browser checks report no JavaScript errors or horizontal
overflow. All captures use disposable migrated PostgreSQL/local storage.

The latest PR #37 selection follow-up adds `faces-selection-*`,
`discover-selection-*` and `identity-expanded-*` at the same desktop/mobile CSS
viewports. Faces and Discover now share checkbox and floating action-panel
components. Faces moves verification into that panel alongside unassignment;
identity creation/import and Last processed open by default. Profile, card,
provenance and mention empty-state captures were also refreshed from this revision.

Chromium checks passed at both widths: Space activation, Shift ranges,
click-to-add mode, Clear, source-link restoration and selection reset when
switching tabs; the floating panel remains within the viewport with no
horizontal overflow or JavaScript errors. Against a separately migrated,
twice-seeded disposable PostgreSQL/local-media instance, browser Verify and
Unassign actions persisted correct states, recorded verifier attribution,
cleared verification on unassignment, refreshed profile totals and retained
origin, source and downloadable face media. Frontend tests additionally cover
view-only permissions, failed/partially missing batches, retry, pending-action
disabling, pagination and filter/navigation reset. Identity disclosures retain
their collapse controls.


The compact-card revision adds `compact-faces-{light,dark}-*`,
`compact-faces-selected-{light,dark}-*` and
`compact-discover-{light,dark}-*` comparisons, all at the standard desktop/mobile
CSS viewport dimensions. Faces and Discover use the same square corners,
8px padding, grid gaps, library color and theme-aware assignment text. Faces
shows its state icon/label and `conf` detection confidence directly below the
photo, then library plus truncated document ID, last-change time and plain editor name. Fixed-height source and
footer blocks, image status badges, matching-detection labels and visible detection/page IDs are removed. Loading skeletons follow the same compact structure.

Chromium checks passed in light/dark at both widths: assignment precedes library;
change/user starts within 8px of the library/document row; card heights are equal; library
colors, padding and corner styles match Discover; visible card text omits detection IDs; Space/Shift selection, Clear and source-link restoration still work.
Selection and filtered profile screenshots were refreshed from this revision.
No horizontal overflow or browser JavaScript errors occurred. Earlier before
captures remain available in commit `a9f5022` for comparison.


Editor-name follow-up: annotation editors render as plain truncated text with
full-name tooltips, with no link or underline. A source TODO defers linking to
the editor's user tab until that tab is implemented. The source row now includes
library plus a truncated document ID, matching the Discover row layout; its
full reference remains available in a tooltip. Desktop/mobile light/dark and
selected/filtered screenshots were refreshed for this revision.

Selected-face action colors: Verify selected is a green outline Button;
Unassign selected is a red outline Button. The selected-state captures at both
standard viewport sizes show the requested colors in light/dark. Chromium
checks confirmed text/border colors, a 1px outline, keyboard focus, hover,
selection/Clear behavior and action-panel bounds, with no overflow or JavaScript
errors. Standard Button focus and disabled behavior remain in place.
