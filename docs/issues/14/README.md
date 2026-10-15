# Issue 14: inline scan toolbar evidence

After captures use the running application source at `12cb8a0`, PostgreSQL 16
with pgvector, and disposable local storage. Captured on 2026-10-15 in headless
Chromium 153.0.8010.12 with device scale factor 1, after migration, two successful
seed CLI runs and schema validation. This refresh reuses the installed frontend
dependencies; type checking, all 131 unit tests and the production build passed.
No project data or external inference
service was used.

Desktop captures are **1440 × 900 CSS pixels**; mobile captures are
**390 × 844 CSS pixels**. The `all` and `verified` states use the maintained
`scan-toolbar` page (Link state review / page 2); `union` uses
`scan-toolbar-union` (page 1, automatic and manual selected). The dark captures
apply the application's `.dark` theme variant. Existing annotation badges remain
visible outside the toolbar. Before captures are embedded in
[issue #14](https://github.com/DCGM/PeopleGatorApp/issues/14).

| State | Desktop | Mobile |
| --- | --- | --- |
| All, including unassigned faces | [Desktop](after-desktop-all.png) | [Mobile](after-mobile-all.png) |
| Verified only | [Desktop](after-desktop-verified.png) | [Mobile](after-mobile-verified.png) |
| Automatic + Manual | [Desktop](after-desktop-union.png) | [Mobile](after-mobile-union.png) |
| Verified, dark theme | [Desktop](after-desktop-dark-verified.png) | [Mobile](after-mobile-dark-verified.png) |

Browser interaction checks exercised each state, unions, all three states versus
All, deselection, direct links, reload and back/forward. Assertions checked URL
values, pressed states, rendered face counts and assigned OCR mention fragments,
and the absence of toolbar comboboxes, filter badges or collapse controls.
Arrow keys moved focus between toggles; Space selected them without navigating
the scan. Keyboard focus had the standard visible ring. Pressed items retained their
`data-state=on` styling; native titles avoid tooltip-trigger state collisions.
The toolbar container has a transparent background in both themes, leaving the
scan visible between controls. Browser assertions checked its computed background
color in every captured state. Previous/next line and
face, zoom in/out/reset, Names and translation on/off controls responded.
Translation generation was not validated because no external service is configured.

Bounds checks at widths 320, 390, 639, 640, 641, 1024, 1280, 1440, 1536 and
1920 CSS pixels found no document overflow or tools outside the viewer; toggles
stayed directly visible. At 390px, reset stays with its state group, alongside
translation on the final naturally wrapped row. Screenshots were visually inspected
separately from these interaction checks.
