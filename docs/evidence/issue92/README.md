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

State-count extension: captures were refreshed from the local running PR
application with the migrated, twice-seeded synthetic database. Desktop remains
1440 × 900 CSS pixels; mobile remains 390 × 844.

- `*-state-results.png`: mixed state ranges, verified combined sorting and the
  corresponding state counts on Mira Counts' card (collapsed mobile filters).
- `*-state-choices.png`: All, Verified, Manual and Automatic in the state picker;
  Unassigned is absent because ownerless evidence has no person.
- `*-state-range.png`: exact verified All annotations range in the standard popover.
- `*-state-dark.png`: dark, expanded controls with automatic-face ascending sort.
- `*-state-sort.png`: state-specific count strategies in the shared Sort control.

Chromium checks cover selected-state API/URL submission, exact combined bounds,
individual state-bound removal, Back/Forward, reload, clear-all retaining search
and sort, scored search and browse, both sort directions, mobile keyboard toggle,
parent-width overflow and light/dark rendering, with no page errors. The existing
total-count browser checks were repeated and their screenshots refreshed.
