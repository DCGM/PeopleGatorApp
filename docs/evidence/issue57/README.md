# Document table evidence

Real Chromium captures of this issue branch running with its isolated PostgreSQL
store and synthetic preview seed. Desktop: 1440 × 900 CSS pixels. Mobile:
390 × 844 CSS pixels. Full-page captures retain those viewport widths.

- `table-*`: default columns; all document-wide totals are visible by horizontal scrolling.
- `columns-*`: standard Columns popover with individually configurable fields.
- `sort-ascending-*` / `sort-descending-*`: clickable Document name header with its active direction and server-ordered rows.
- `first-page-*`: optional First page enabled, showing one thumbnail per document.
- `name-hidden-*`: document identity remains visible and linked with Document name hidden.
- `attribution-*`: user/key label columns enabled and horizontally scrolled into view.
- `loading-end-*`: all 14 pagination ledgers appended through the existing opaque cursor.
- `filters-mobile`: existing mobile settings expanded above the table. The default
  desktop captures show the corresponding always-available settings.

Browser checks passed at both sizes: one row per document, no per-row page/media
requests when First page is hidden, one image request with no page-list/name
requests when enabled, show/hide name and restore defaults, preserve field choices
while filtering and sorting, default and legacy presentation URLs rendering the
table, bounded page width, horizontal scroll plus automatic
cursor loading/exhaustion, keyboard horizontal scrolling when fields overflow,
click/Enter/Space sorting, direction reversal and history restoration, supported-only header actions,
and no browser runtime errors. The preview-table scenario has 2 registered pages,
9 annotations (3 automatic, 2 verified, 2 manual, 2 unassigned), and 2 distinct
linked entities. All data are synthetic; actor columns expose registry labels only.

The production build uses only TanStack v9's column visibility feature; Vue Query
and the existing route filters/sort still own the remote result sequence. There
is no client pagination, filtering or sorting; first-page media is the only
optional per-row request.
The table-only production build measures 825.53 kB minified JS (247.61 kB gzip).
The earlier base measurement was 790.75 kB (236.59 kB gzip); both builds exceed
Vite's 500 kB advisory. These are bundle measurements, not a runtime benchmark.
