# Issue #75 browser evidence

Captured from the issue branch's running Vite frontend and native API against a
new, migrated PostgreSQL database seeded twice with local synthetic media.
Desktop captures use 1440 × 900 CSS pixels; mobile uses 390 × 844 CSS pixels.

- `scan-*` and `gallery-*`: page archive link in the header, document archive
  link beside Document pages, and existing internal thumbnail navigation.
- `faces-*`: Profile photo / Search hit indicators and page archive links.
- `discover-*`: archive links on global face matches from both preview libraries.
- `*-selected-*`: links remain independently operable in selection mode.
- `faces-dark-*`: the same face evidence using the application's dark class.

Browser assertions checked no horizontal document overflow or nested anchors,
header target updates after thumbnail navigation, document targets without page
queries, and each face link against its source page's authenticated API response.
Tab-focus and Enter activation opened a new tab in both person tabs while
preserving the original route and selection toolbar. No page errors occurred.

Synthetic archive UUIDs have no corresponding external collection records.
External-tab activation and exact API targets were checked; successful rendering
of a real document on Digitální knihovna was not asserted.
