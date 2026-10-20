# Issue #40 browser evidence

These are real Chromium captures of the running application. They use migrated,
twice-seeded PostgreSQL and local synthetic media. Desktop is 1440 × 900 CSS
pixels; mobile is 390 × 844 CSS pixels. The dev-only Vue devtools button is
hidden. The captures show the **Document pages** gallery in the scan workspace.

| State | Desktop | Mobile |
| --- | --- | --- |
| Gallery, page outside the first batch is current (`document-page-gallery`) | ![Desktop gallery with 14 pages and the current page outlined](desktop-gallery.png) | ![Mobile gallery below the scan with the current page outlined](mobile-gallery.png) |
| Registered page without media | ![Desktop: "Could not load scan" with a "No preview" current thumbnail](desktop-missing-media.png) | ![Mobile: "Could not load scan" with a "No preview" current thumbnail](mobile-missing-media.png) |
| Annotation filter active (`document-page-gallery-filtered`) | ![Desktop: importer filter keeps all six gallery pages](desktop-evidence-filter.png) | ![Mobile: importer filter keeps all six gallery pages](mobile-evidence-filter.png) |
| Keyboard focus on a page link | ![Desktop: focus ring on a non-current page link](desktop-keyboard-focus.png) | ![Mobile: focus ring on a non-current page link](mobile-keyboard-focus.png) |
| Single-page document | ![Desktop: one current page](desktop-single-page.png) | ![Mobile: one current page](mobile-single-page.png) |
| Dark theme | ![Desktop dark gallery](desktop-dark.png) | ![Mobile dark gallery](mobile-dark.png) |

At both viewports, browser assertions checked the following:

- Direct entry marks the URL page and scrolls it into view.
- All 14 pages are reachable, with no duplicates.
- Selecting a distant page loads its scan.
- Three rapid selections settle on the last one.
- Back, Forward and reload keep the URL, marker and scan consistent.
- The page does not overflow horizontally.
- The evidence filter keeps all six pages and survives navigation.
- There are no uncaught page errors.

Desktop also checked that arrow keys on a focused page link leave the
face/line selection unchanged and that Enter activates the link. Mobile checked
that a touch swipe scrolls only the strip, leaving the URL, page scroll and scan
pan/zoom transform unchanged.

These screenshots supplement the regression tests. They do not establish
exhaustive accessibility or touch coverage.
