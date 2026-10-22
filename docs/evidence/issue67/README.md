# Issue #67 browser evidence

Captured from the running issue branch with synthetic seed data, local PostgreSQL
on port 55467, API on 8067 and Vite on 5167. Desktop viewport: 1440 × 900 CSS
pixels. Mobile viewport: 390 × 844 CSS pixels. Discover images are full-page
captures; scan images show the viewport at the panel top or scrolled to the
global candidate. Discover captures precede disposable assignment/merge checks.

- `discover-desktop.png` and `discover-mobile.png`: `global-discovery` seed link,
  with local library/document/page, modifier/key and Verified filters retained.
  Both global face and person requests omit those predicates. Matching faces in
  `preview-nlk` and Orion Portrait remain visible.
- `discover-mobile-expanded.png`: expanded Discovery search settings, activated
  using Enter on the mobile filter toggle; collapse retains the selected inputs.
- `scan-workspace-desktop.png` and `scan-workspace-mobile.png`: the revised
  right panel omits the shared workspace badges below the tabs.
- `scan-desktop.png` and `scan-mobile.png`: the revised candidate list shows
  Saffron Navigator with both removable badge groups omitted. Source filters
  remain in the URL and the candidate-source selector remains available. These
  captures use the retained synthetic data after the assignment/merge checks.

Browser checks exercised both candidate collections, responsive overflow, tabs,
reload, candidate navigation and Back, preserving the workspace query. API request
inspection verified global similarity predicates in both entry points. Actual UI
assignment and merge requests completed successfully against disposable data.

Frontend regression tests additionally cover exact request mapping, references,
model/text/sort choices, invalid surrounding filters, cache isolation, self-match
exclusion, action deduplication and retained ordinary evidence parameters. Existing
cursor tests cover restart on entity/reference selection changes.
