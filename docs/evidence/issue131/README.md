# Issue #131 — compact bottom page strip

Captured from this branch's running local application, backed by a new migrated
PostgreSQL database and disposable filesystem seeded twice. All data/media are
synthetic. Chromium 156.0.8078.4 via Playwright; desktop **1440 × 900**, mobile
**390 × 844** CSS pixels.

Reproduce from `people-gator-app` with the documented local instance:

```sh
PAGE_STRIP_ORIGIN=http://127.0.0.1:5231 PAGE_STRIP_API=http://127.0.0.1:8231 node scripts/check-page-strip.mjs
```

| State | Desktop | Mobile |
| --- | --- | --- |
| No selected person; no annotation statistics | [Capture](desktop-highlights.png) | [Capture](mobile-highlights.png) |
| Nora selected; matches highlighted while all pages remain | [Capture](desktop-person-highlights.png) | [Capture](mobile-person-highlights.png) |
| Nora selected; person-only enabled | [Capture](desktop-person-filter.png) | [Capture](mobile-person-filter.png) |
| Current page with a person match: double border retained | [Capture](desktop-current-assigned.png), [strip](desktop-current-assigned-strip.png) | [Capture](mobile-current-assigned.png), [strip](mobile-current-assigned-strip.png) |
| Long selected-person name | [Capture](desktop-long-name.png) | [Capture](mobile-long-name.png) |
| Unknown selected person; empty results | [Capture](desktop-empty.png) | [Capture](mobile-empty.png) |
| Dark theme | [Capture](desktop-dark.png) | [Capture](mobile-dark.png) |

The strip shows no face/mention statistics. Noncurrent pages containing the
selected person have a single orange outer border; the current page keeps its
double orange border. Membership uses assigned faces OR linked text mentions,
with the person-only toggle on or off.

The one-line header shows the orange document name, NDK link, document-wide page
position, person-only toggle and Sort. Narrow panes scroll horizontally instead
of wrapping; controls use shorter labels on mobile. The strip has no person
selector, applied-filter tags or mobile expansion panel.

The browser script selects Nora Page and Otto Page through the right panel and
checks highlights with the filter off, the keyboard toggle, mention-only page
navigation, reload and history. It checks the absence of annotation badges, outer-only
person-match strokes, the current page's double border, stable geometry for long
names/empty results, sorting, legacy URLs, light/dark themes and page width. The
long-name check renames a synthetic person through the API and restores its name
in `finally`. Screenshots wait for thumbnails and disable closing animations.

Validation:

- `npm run build` (including type checking) passed; the complete frontend unit
  suite passed: **549 tests / 76 files**.
- Playwright browser checks passed at both viewport sizes against the current
  main integration, including People defaults and source tags.
- Real migration → seed → seed → schema check passed on the isolated
  `issue131_merge_preview` database with disposable filesystem storage.
- **10 focused seed integration tests passed** on the separate
  `issue131_merge_schema` database. These exercise graph/vector integrity,
  review-edit preservation, interrupted checkpoint recovery, page-strip
  highlights, source tags, People defaults and additive column-layout fixtures.
- The full backend suite is delegated to PR CI; local checks above do not
  replace its result.
