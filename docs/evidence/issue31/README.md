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
| `profile-*` | One matching face of four overall, with one clear-all action and retained origin context |
| `provenance-*` | Expanded recorded identity and face provenance, original importer/key and later JWT reviewer |
| `mentions-empty-*` | Accessible Mentions tab, filtered zero and recovery |
| `activity-time-*`, `activity-user-*` | Sidebar Activity tab groups faces/mentions by annotation edit day or last user; clicking groups filters the scan |
| `page-*` | Same annotation highlighted in its source workspace; URL criteria retained without a filter panel |
| `discovery-*` | Assigned-elsewhere discovery choice, independent of assigned-evidence state |
| `people-dark-*` | Standard controls and active tags in dark theme |

Executed browser checks in Chromium at both widths:

- People → profile → source page → profile, and Documents → matching scans →
  source page → profile retain active evidence criteria and correct scope.
- Source processing bounds remain scoped origin criteria on profiles.
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
