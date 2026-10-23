# Document table evidence

Real Chromium captures of this issue branch running with its isolated PostgreSQL
store and synthetic preview seed. Desktop: 1440 × 900 CSS pixels. Mobile:
390 × 844 CSS pixels. Full-page captures retain those viewport widths.

- `table-*`: default columns; all document-wide totals are visible by horizontal scrolling.
- `columns-*`: standard Columns popover with individually configurable fields.
- `first-page-*`: optional First page enabled, showing one thumbnail per document.
- `name-hidden-*`: document identity remains visible and linked with Document name hidden.
- `attribution-*`: user/key label columns enabled and horizontally scrolled into view.
- `loading-end-*`: all 14 pagination ledgers appended through the existing opaque cursor.
- `filters-mobile`: existing mobile settings expanded above the table. The default
  desktop captures show the corresponding always-available settings.

Browser checks passed at both sizes: one row per document, no per-row page/media
requests when First page is hidden, one image request with no page-list/name
requests when enabled, show/hide name and restore defaults, preserve field choices
through Items/Table switches, bounded page width, horizontal scroll plus automatic
cursor loading/exhaustion, keyboard horizontal scrolling when fields overflow,
and no browser runtime errors. The preview-table scenario has 2 registered pages,
9 annotations (3 automatic, 2 verified, 2 manual, 2 unassigned), and 2 distinct
linked entities. All data are synthetic; actor columns expose registry labels only.

The production build uses only TanStack v9's column visibility feature; Vue Query
and the existing route filters/sort still own the remote result sequence. There
is no client pagination, filtering, sorting, or preview-image request cascade.
Against base `02dc110`, the same Vite installation measured minified JS increasing
from 790.75 kB (236.59 kB gzip) to 830.18 kB (248.75 kB gzip): +39.43 kB / +12.16 kB
gzip for the table, checkbox and integration. Both builds already exceed Vite's
500 kB advisory. These are bundle measurements, not a runtime benchmark.
