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
