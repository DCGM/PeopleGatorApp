# Issue #62 browser evidence

Actual Chromium captures from the issue branch with the migrated synthetic
PostgreSQL/local-media instance. `desktop-*.png` use **1440 × 900** CSS pixels;
`mobile-*.png` use **390 × 844**. The plain filenames show the top of each list
after continuation; `*-appended.png` show its end after the second batch, with
no remaining load-more button. These images complement the interaction checks.

Executed browser checks:

- On People, Scans and Documents at 1440 × 600 and 390 × 844, search Pagination,
  scroll the list end into view, and observe 12 → 14 rows in exactly two requests.
- Repeat ordinary browsing scoped to `preview-pagination`, using descending name
  order (People/Documents) or page ID (Scans). Delay the cursor request by 700 ms
  and dispatch repeated resize signals: exactly one continuation runs, and the
  rendered IDs/names match server order without duplicates.
- At 1440 × 12000, search Pagination: all fourteen results load without scrolling.
  Reload at height 600 and then resize to height 12000: the remaining batch loads.
- At 1440 × 26000, unfiltered People (30 records), Scans (72) and Documents (36)
  complete in three, six and three sequential batches, respectively, without
  scrolling or requiring another intersection transition.
- Open `pagination-scoped-scans`: the canonical registered-document scope loads
  all fourteen gallery pages across its cursor boundary.
- Fail each list's cursor request with HTTP 503. The query's existing four bounded
  attempts finish, twelve rows remain, and repeated resize/scroll events cause
  no further retries. Focus the manual load/retry button and press Enter after
  restoring the API: the remaining two rows append.

No browser JavaScript errors occurred in the desktop/mobile screenshot checks.
Mobile Scans measures a one-CSS-pixel scroll-width rounding difference; no layout
changes were included. Firefox/Safari were not exercised. Unit tests additionally
cover criteria changes while a request is delayed, clipping scroll containers,
background refetch guards, missing observers, empty results and unmount cleanup.
