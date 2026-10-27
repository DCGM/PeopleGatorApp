# Document table evidence

Real Chromium captures of this issue branch running with its isolated PostgreSQL
store and synthetic preview seed. Desktop: 1440 × 900 CSS pixels. Mobile:
390 × 844 CSS pixels. Full-page captures retain those viewport widths; sticky-header captures show the scrolled viewport.

- `table-*`: default columns; all document-wide totals are visible by horizontal scrolling.
- `columns-*`: standard Columns popover with individually configurable fields.
- `sort-ascending-*` / `sort-descending-*`: clickable Document name header with its active direction and server-ordered rows.
- `first-page-*`: optional First page enabled separately from the default NDK source column.
- `first-page-dark-*`: the default NDK link and optional image in dark theme.
- `ndk-tooltip-*`: expanded Národní digitální knihovna tooltip on keyboard focus.
- `name-hidden-*`: document identity remains visible and linked with Document name hidden.
- `attribution-*`: user/key label columns enabled and horizontally scrolled into view.
- `loading-end-*`: all 14 pagination ledgers appended through the existing opaque cursor.
- `sticky-header-*`: headings pinned beneath page navigation during full-page scrolling, with First page enabled.
- `sticky-header-right-*`: pinned headings aligned with the final columns after horizontal scrolling and cursor loading.
- `sticky-header-dark-*`: pinned headings and sort direction in the dark theme.
- `unnamed-sort-ascending-*` / `unnamed-sort-descending-*`: unknown names compare as empty strings, appearing first ascending and last descending.
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
The table-only production build measures 827.15 kB minified JS (248.31 kB gzip).
The earlier base measurement was 790.75 kB (236.59 kB gzip); both builds exceed
Vite's 500 kB advisory. These are bundle measurements, not a runtime benchmark.

Sticky-header checks at both sizes verify header/navigation edge alignment after
full-page scrolling, header/body alignment at the rightmost columns, no separate vertical table scroll area, no premature cursor request before the
final row enters the viewport, loading the second batch at the far right, and keyboard sorting from the pinned header. Light and
dark screenshots use the same synthetic pagination documents and local media.

Unnamed-sort checks verify complete loaded name order and the legacy document's
position first ascending and last descending, at desktop and mobile sizes. In
`preview-mzk`, its positions are 1 of 17 ascending and 17 of 17 descending; the stored name remains null. Regression tests cover one-row cursor
batches and the same order in ordinary browsing and bounded text search.

Header scroll work was measured in Chromium on the Vite development instance
at 1440 × 900, with 14 loaded
synthetic pagination rows and First page enabled. The same 30 page-scroll steps
triggered 660 header-subtree component renders and 30 table layout reads before
the optimization, versus zero renders and zero table layout reads afterwards.
The header finished at 52px, aligned with navigation, in both runs. Measurements
instrumented Vue render functions and the table's `getBoundingClientRect` after
images/layout settled; consecutive steps advanced 15px and waited two animation frames.
These are work counts, not an FPS benchmark. See `header-scroll-work.json`.

NDK column checks at both sizes verify that the link follows Document name,
shows NDK with an external-link icon, expands its name on keyboard focus and
opens the stored source URL in a new tab. It is shown by default with no thumbnail
request. External navigation uses an intercepted synthetic response; no external
archive data is fetched. Enabling First page requests one image and leaves the
NDK link in its own column. The thumbnail has no overlay link. Light/dark captures
include this arrangement, with page width bounded and standard focus states.
