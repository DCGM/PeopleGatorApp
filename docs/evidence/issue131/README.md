# Issue #131 — bottom page-strip review

Captured from the local production build of this branch, backed by a new,
migrated PostgreSQL instance and disposable filesystem seeded twice. No external
images, inference services or project data were used. Browser: Chromium
156.0.8078.4 through Playwright; desktop 1440 × 900 and mobile 390 × 844 CSS pixels.

Reproduce from `people-gator-app` with the documented local instance, using the
manifest's `page-strip-review` fixture:

```sh
PAGE_STRIP_ORIGIN=http://127.0.0.1:5132 node scripts/check-page-strip.mjs
```

| State | Desktop | Mobile |
| --- | --- | --- |
| All 18 pages; pages 1 and 4 marked | [Capture](desktop-highlights.png) | [Capture](mobile-highlights.png) |
| Nora Page selected; 15 face-or-mention matches | [Capture](desktop-person-filter.png) | [Expanded settings](mobile-person-filter.png), [collapsed settings](mobile-person-collapsed.png) |
| Unknown person; empty strip and clearable tag | [Capture](desktop-empty.png) | [Capture](mobile-empty.png) |
| All pages in dark theme | [Capture](desktop-dark.png) | [Capture](mobile-dark.png) |

The browser script checks actual person search/selection, Enter to expand mobile
settings, active tags while collapsed, mention-only page navigation, filter
retention, reload, Back after clearing, unknown-person empty results, current
scan retention, no horizontal page overflow and no page errors. Screenshots wait
for thumbnails and closing animations. Backend tests cover page/library scoping,
15 matches across two cursor batches, independent unassigned-face counts, media,
face assignment/deletion and mention unlinking, and rerun preservation.

Validation recorded for this change:

- Frontend: `npm run build`; `npm run test:unit -- --run`: 76 files, 529 tests pass.
- Seed integration: new page-strip test, rerun/edit-preservation, all three
  interrupted-checkpoint cases, no-resurrection test and complete graph/media
  check: seven tests pass. Existing page-gallery integration also passes.
- Real migration → seed → seed on port 55531, separate `people_gator` development
  and `seed_tests` disposable databases and `/tmp/people-gator-issue131-storage`.
- Production browser script passes at both viewport sizes. No full backend suite
  run: production API/persistence code and schemas are unchanged.
