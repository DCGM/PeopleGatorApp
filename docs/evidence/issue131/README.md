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
| Right-panel selection; Nora Page only enabled | [Capture](desktop-person-filter.png) | [Capture](mobile-person-filter.png) |
| Long selected-person name | [Capture](desktop-long-name.png) | [Capture](mobile-long-name.png) |
| Unknown selected person; empty results | [Capture](desktop-empty.png) | [Capture](mobile-empty.png) |
| Dark theme | [Capture](desktop-dark.png) | [Capture](mobile-dark.png) |

The one-line header shows the orange document name, NDK link, document-wide page
position, person-only toggle and Sort. Narrow panes scroll horizontally instead
of wrapping; controls use shorter labels on mobile. The strip has no person
selector, applied-filter tags or mobile expansion panel.

The browser script selects Nora Page and Otto Page through the right panel,
checks the keyboard-operated toggle and its changing scope, navigates to a
mention-only page, reloads and uses Back after toggling off. It measures unchanged
header height with filtering, empty results and a long name, checks stable strip
height for assigned-only and empty results, and verifies sort changes
and legacy URL restoration, checks current-scan
retention and page width, and captures light/dark states. The long-name check
renames a synthetic person through the API and restores the original name in
`finally`. Screenshots wait for thumbnail loading and disable closing animations.

Validation:

- `npm run build` (including type checking) passed; the complete frontend unit
  suite passed: **528 tests / 75 files**.
- Production browser script passes at both viewport sizes.
- Real migration → seed → seed on the isolated `compact_preview` database and
  `/tmp/people-gator-issue131-compact-storage`; schema tests use a separate store.
- All **94 preview-seed tests passed** against isolated migrated PostgreSQL.
  They cover page/library scope, face-or-mention matching across
  cursor batches, independent indicators, local thumbnails, mutations, review
  preservation and interrupted checkpoints. CI findings concerning added library
  options and Ada's existing gallery are covered by their regression tests; the
  new scene now uses a dedicated second person.
