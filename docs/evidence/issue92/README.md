# Issue #92 browser evidence

Actual Chromium captures of the local application with synthetic preview data.
Desktop uses 1440 × 900 CSS pixels; mobile uses 390 × 844 CSS pixels.

- `*-zero.png`: Faces maximum zero, Text mentions minimum three, descending mention sort. Mobile filters start collapsed with active tags visible.
- `*-range-control.png`: Faces range popover with exact-zero values, after checking inverted-range validation.
- `*-search-range.png`: scored “Counts” search with Faces 2–7, Text mentions maximum three, ascending combined-count sort. Mobile filters are expanded.
- `*-dark.png`: zero-face browse with descending mention sort in dark mode; mobile filters expanded.

Browser checks passed on both viewports: invalid-range rejection, exact-zero
submission, individual bound removal, Back/Forward restoration, clear-all retaining
query and sort, scored search, reload, no horizontal overflow, and no page errors.
Mobile additionally exercised Enter on the Collapsible toggle, `aria-expanded`,
and active-tag accessibility after collapsing. Captures show the implementation
and standard light/dark controls; they do not substitute for these interaction checks.
