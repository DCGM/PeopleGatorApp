# Workspace sidebar showcase — #60

Real Chromium captures of the running application with the existing synthetic
preview dataset. Desktop: 1440 × 900 CSS pixels. Mobile: 390 × 844 CSS pixels.

- `global-*`: initial Global mode.
- `local-*`: Local sample controls; mobile shows the open drawer.
- `local-dark-*`: the same Local controls in dark mode.
- `local-closed-*`: Local sample tags remain available with sidebar/drawer closed.

Browser checks passed at both sizes: synthetic document rendering; searchable
multi-select and individual tag removal; Local settings retained across navigation
and Global/Local changes; unchanged route query; theme switching; desktop keyboard
collapse; mobile drawer navigation and Escape dismissal; no horizontal overflow
or uncaught JavaScript errors. Sidebar examples are in-memory samples and do not
filter the underlying results. The account footer identifies the configured login,
not a new profile/authentication integration.

Latest filter-selector revision: **+ Add filter** names the opening action.
Escape dismisses the type, value or date selector and returns focus to the button,
without removing applied values or closing the mobile sidebar. There is no Cancel
button. `add-filter-*`, `filter-type-*`, `value-filter-*`, `date-filter-*`,
`local-*` and `local-dark-*` show this revision at the dimensions above.
These captures use the local frontend and the synthetic PR #70 preview API;
Chromium web security was disabled for this cross-origin browser check.
