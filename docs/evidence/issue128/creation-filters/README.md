# Shared creation filters

Actual Chromium captures from the running synthetic application. Desktop uses
1440 × 900 CSS pixels; mobile uses 390 × 844 CSS pixels. Captures use the
Europe/Prague time zone. Mobile controls are expanded for the screenshots; the
script also checks their initial collapsed state and accessible toggle.

Each pair shows the same shared creation controls and an applied criterion:

- `documents`: document sidebar/mobile drawer.
- `people`: person search.
- `scans`: registered-page search with an inclusive date interval.
- `person-faces` and `person-mentions`: person evidence tabs.
- `sidebar-people`, `sidebar-faces`, `sidebar-mentions`: scan viewer panels.
- `creator-picker`: open creator multi-select.
- `date-picker`: open creation calendar/time control.

From a migrated, seeded disposable local instance, save the seed CLI's output
and run the browser check from `people-gator-app`:

```sh
CREATION_FILTER_SEED_LOG=/tmp/issue128-creation-filter-seed2.log \
CREATION_FILTER_ORIGIN=http://127.0.0.1:5128 \
CREATION_FILTER_EVIDENCE=../docs/evidence/issue128/creation-filters \
node scripts/check-creation-filters.mjs
```

The script resolves fixture links from the real CLI output and verifies all four
creation controls, URL restoration, creation parameters sent to the appropriate
backend resource, actual multi-select changes and individual tag removal. It
changes creation time through the picker and checks that resetting evidence
clears both creation and link-state criteria in one URL update. Both viewports
are checked for page-level overflow and browser errors. Physical touch devices
are not covered.
