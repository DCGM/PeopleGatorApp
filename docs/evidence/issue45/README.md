# Issue #45 browser evidence

Actual Chrome captures of this issue branch running against an isolated migrated
PostgreSQL database and synthetic local media. Open the seed CLI's
`person-mention-highlights` link: **Viewport focus practice**, with Ada Novak selected.
The fixtures already link Ada on two distinct OCR lines; no new records are needed.

Desktop captures use 1440 × 900 CSS pixels; mobile uses 390 × 844 CSS pixels.
Mobile uses the existing Zoom out control to reach 55% so both lines fit below
the toolbar. Each capture shows the full viewport. Dark captures enable the
application's existing `.dark` theme class. No screenshot changes application styles.

| State | Desktop | Mobile |
| --- | --- | --- |
| Light, upper line selected | ![Desktop: upper accent line and lower orange mention](desktop-light-upper.png) | ![Mobile: upper accent line and lower orange mention](mobile-light-upper.png) |
| Light, lower line selected | ![Desktop: upper orange mention and lower accent line](desktop-light-lower.png) | ![Mobile: upper orange mention and lower accent line](mobile-light-lower.png) |
| Dark, upper line selected | ![Desktop dark: upper accent line and lower orange mention](desktop-dark-upper.png) | ![Mobile dark: upper accent line and lower orange mention](mobile-dark-upper.png) |
| Dark, lower line selected | ![Desktop dark: upper orange mention and lower accent line](desktop-dark-lower.png) | ![Mobile dark: upper orange mention and lower accent line](mobile-dark-lower.png) |

Browser assertions checked accent precedence, orange mention lines, Enter
activation, line selection through click (desktop) and tap (mobile), line IDs in
the URL, no orange outlines with no selected identity or Lenka Vesela selected,
and restored mention highlighting after selecting Ada's face. Both OCR lines
were checked to be inside the viewer below the toolbar for every capture.
All four viewport/theme combinations completed without uncaught page errors.
Screenshots supplement the component and seed integration tests; these checks
are not exhaustive browser/accessibility coverage.
