# Issue #131 — compact bottom page strip

Captured from this branch's local production build, backed by a new migrated
PostgreSQL database and disposable filesystem seeded twice. All data/media are
synthetic. Chromium 156.0.8078.4 via Playwright; desktop **1440 × 900**, mobile
**390 × 844** CSS pixels.

Reproduce from `people-gator-app` with the documented local instance:

```sh
PAGE_STRIP_ORIGIN=http://127.0.0.1:5132 node scripts/check-page-strip.mjs
```

| State | Desktop | Mobile |
| --- | --- | --- |
| No selected person; indicators on pages 1 and 4 | [Capture](desktop-highlights.png) | [Capture](mobile-highlights.png) |
| Nora selected; matches highlighted while all pages remain | [Capture](desktop-person-highlights.png) | [Capture](mobile-person-highlights.png) |
| Nora selected; person-only enabled | [Capture](desktop-person-filter.png) | [Capture](mobile-person-filter.png) |
| Current page with a person match: double border retained | [Capture](desktop-current-assigned.png), [strip](desktop-current-assigned-strip.png) | [Capture](mobile-current-assigned.png), [strip](mobile-current-assigned-strip.png) |
| Long selected-person name | [Capture](desktop-long-name.png) | [Capture](mobile-long-name.png) |
| Unknown selected person; empty results | [Capture](desktop-empty.png) | [Capture](mobile-empty.png) |
| Dark theme | [Capture](desktop-dark.png) | [Capture](mobile-dark.png) |

Unassigned-face counters sit inside their thumbnails. Pages containing the
selected person have a single outer stroke; the actual current page retains its
double border, including when it is also a person match. Highlight membership
uses the same face-or-mention predicate with the person-only toggle on or off.

The one-line header shows the orange document name, NDK link, document-wide page
position, person-only toggle and Sort. Narrow panes scroll horizontally instead
of wrapping; controls use shorter labels on mobile. The strip has no person
selector, applied-filter tags or mobile expansion panel.

The browser script selects Nora Page and Otto Page through the right panel and
checks highlights with the filter off, the keyboard toggle, mention-only page
navigation, reload and history. It checks counters inside thumbnails, outer-only
person-match strokes, the current page's double border, stable geometry for long
names/empty results, sorting, legacy URLs, light/dark themes and page width. The
long-name check renames a synthetic person through the API and restores its name
in `finally`. Screenshots wait for thumbnails and disable closing animations.

Validation:

- `npm run build` (including type checking) passed; the complete frontend unit
  suite passed: **529 tests / 75 files**.
- Production browser script passes at both viewport sizes.
- Real migration → seed → seed on the isolated `compact_preview` database and
  `/tmp/people-gator-issue131-compact-storage`; schema tests use a separate store.
- Current focused page-strip seed integration test passed, including batched
  source-ID membership and new current/assigned exploration links. The previous
  revision passed all 94 seed tests and GitHub backend/frontend/image CI. These
  checks cover page/library scope, face-or-mention matching across
  cursor batches, independent indicators, local thumbnails, mutations, review
  preservation and interrupted checkpoints. CI findings concerning added library
  options and Ada's existing gallery are covered by their regression tests; the
  new scene now uses a dedicated second person.
