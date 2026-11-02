# People search merge (#107)

Actual Playwright Chromium captures from the implementation with the synthetic
**Rina Merge** scenario. Desktop uses a 1440 × 900 CSS viewport; mobile uses
390 × 844. Images capture the full document.

- `*-selection.png`: three explicitly selected people; last and first named merge
  actions, then Clear.
- `*-pending.png`: held batch request; selection and actions disabled.
- `*-error.png`: deliberately aborted request; selected people retained for retry.
- `*-dark.png`: the same selected state in dark mode.

Browser checks exercised Space and Shift+Space selection, forward/backward Shift
ranges, Clear, no horizontal overflow at both sizes, pending locking, a simulated
network failure and retry, and real API merges using both actions. The batch
last-selected action transferred two faces and two mentions to Rina Merge 3;
the single first-selected action transferred all three faces and mentions into a
new disposable Rina Merge 4. Results refreshed, source records disappeared,
search/sort URL parameters stayed intact, and no confirmation dialog appeared.
A further merge emptied the count-filtered result set safely while preserving
the search/filter/sort URL. Browse-only API tokens were rejected with 403 by both
merge endpoints.

All data and local portrait images are synthetic. The intercepted failure and
held request are browser-only test conditions, not application changes.
