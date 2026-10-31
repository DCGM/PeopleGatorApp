# Document widths and header resizing (#93)

Captured in headless Chromium with synthetic data only, using the actual API and
Vite application at `ad2258c` plus this issue's implementation. All desktop images
use **1440 × 900** CSS pixels; all mobile images use **390 × 844** CSS pixels.

The before images use the original `main` table and the same additive fixture
store as the after images. At each viewport, sorting Document name from A–Z to
Z–A changed its measured width from **160px to 1,171px**, and Library from
**149px to 269px**. With the fix, Document name stays **320px** and Library
**224px** across those sorts. The complete title wraps visibly within its cell,
including the uninterrupted archive reference; row height adapts to its content.

- `before-*-ascending.png` / `before-*-descending.png`: original width jump.
- `after-*-ascending.png` / `after-*-descending.png`: stable defaults, header grips
  and the wrapped long title after sorting.
- `after-*-resized-media.png`: title adjusted to 330px using its header, optional
  First page and attribution/count fields enabled, local preview media loaded.
- `after-*-dark.png`: dark appearance and the rightmost count headers/fields,
  reached inside the bounded table scroll region.

Reproduce with `npm run test:document-widths` from `people-gator-app`; setup and
environment overrides are documented in [the testing guide](../../TEST.md).
The script checks real geometry and interactions in addition to taking captures.
It verifies pointer dragging, browser TouchEvents, keyboard adjustment/bounds/reset,
column restoration, grouped headers and media, loading/empty/error recovery,
shared/header sorting/history, horizontal keyboard access, and single-request
cursor loading from middle/far-right scroll positions. Physical-device touch
and browsers other than Chromium were not exercised.

Widths are session-only state in the mounted Documents table. No stored
preferences, table redesign, API schema change or migration is included.
