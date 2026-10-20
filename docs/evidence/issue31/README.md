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
| `cards-*`, `cards-detail-*` | Equal-sized cards, complete wrapped sources, matching/status image overlays, linked annotation editors; top-bar return link replaces the generic People breadcrumb |
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
keyboard tab activation, equal card dimensions and uncut source references at
both standard widths. The matching label remains within its image and cannot
change card height. The source breadcrumb retains enough mobile width to be
readable. Authorized users can select faces to verify their links using the API's actual `scopes` JWT
claim. Editor links navigate to an active annotation-user filter. The full
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
