# Issue #52 browser evidence

Actual Chromium captures from the local application on `issue/52-unified-filters`,
using only the synthetic preview seed. Desktop: 1440 × 900 CSS pixels; mobile:
390 × 844 CSS pixels; device scale factor 1. The API uses an isolated migrated
PostgreSQL database and disposable local filesystem media. The real seed CLI
ran twice; its normal report supplies IDs and exploration links. No external
embedding/OCR service or real collection data was used.

## Checks performed

- Keyboard selection in the modifier combobox; mobile sliders toggle via Enter;
  expanded/collapsed values and visible removable tags.
- Documents → People → profile → People; identical user/key/date criteria in
  controls, URL and actual requests. Hana's own curator edit matches People,
  while her reviewer-edited face does not match the curator in her profile.
- Both directions with user + key + inclusive date range; individual key removal,
  reload, Back/Forward and onward navigation. Search text is kept by Clear all.
- People and Scans at widths 390, 639, 640, 768, 1024, 1440 and 1920 CSS pixels:
  no horizontal overflow, correct search share of the panel at/above 640px,
  mobile filters collapsed by default, and page scope survives text edits.
- Internal document source filtering in Scans includes the mirror's unannotated
  page and never borrows pages from the same archive UUID in another library.
  The explicit archive seed link resolves pages with no registered parent.
- Shared tags in the page workspace and Activity; annotation-day filtering uses
  the same canonical bounds. Legacy annotation actor criteria on People are
  dropped with a visible notice rather than changing meaning.
- Light/dark rendering and zero uncaught browser errors in both main journeys.

## Captures

### Documents — shared modifier

| Desktop — 1440 × 900 | Mobile — 390 × 844 |
| --- | --- |
| ![Desktop: Documents — shared modifier](documents-filters-desktop.png) | ![Mobile: Documents — shared modifier](documents-filters-mobile.png) |

### People/entities — the same modifier

| Desktop — 1440 × 900 | Mobile — 390 × 844 |
| --- | --- |
| ![Desktop: People/entities — the same modifier](people-filters-desktop.png) | ![Mobile: People/entities — the same modifier](people-filters-mobile.png) |

### Scans — internal document scope, including an unannotated page

| Desktop — 1440 × 900 | Mobile — 390 × 844 |
| --- | --- |
| ![Desktop: Scans — internal document scope, including an unannotated page](scans-filters-desktop.png) | ![Mobile: Scans — internal document scope, including an unannotated page](scans-filters-mobile.png) |

### Person Faces — identity matches, face does not

| Desktop — 1440 × 900 | Mobile — 390 × 844 |
| --- | --- |
| ![Desktop: Person Faces — identity matches, face does not](person-faces-desktop.png) | ![Mobile: Person Faces — identity matches, face does not](person-faces-mobile.png) |

### Person Mentions — own annotation modification

| Desktop — 1440 × 900 | Mobile — 390 × 844 |
| --- | --- |
| ![Desktop: Person Mentions — own annotation modification](person-mentions-desktop.png) | ![Mobile: Person Mentions — own annotation modification](person-mentions-mobile.png) |

### Person Discover — shared source scope

| Desktop — 1440 × 900 | Mobile — 390 × 844 |
| --- | --- |
| ![Desktop: Person Discover — shared source scope](person-discover-desktop.png) | ![Mobile: Person Discover — shared source scope](person-discover-mobile.png) |

### Page workspace

| Desktop — 1440 × 900 | Mobile — 390 × 844 |
| --- | --- |
| ![Desktop: Page workspace](scan-workspace-desktop.png) | ![Mobile: Page workspace](scan-workspace-mobile.png) |

### Page Activity — shared removable day bounds

| Desktop — 1440 × 900 | Mobile — 390 × 844 |
| --- | --- |
| ![Desktop: Page Activity — shared removable day bounds](scan-activity-desktop.png) | ![Mobile: Page Activity — shared removable day bounds](scan-activity-mobile.png) |

### Legacy copied URL notice

| Desktop — 1440 × 900 | Mobile — 390 × 844 |
| --- | --- |
| ![Desktop: Legacy copied URL notice](legacy-notice-desktop.png) | ![Mobile: Legacy copied URL notice](legacy-notice-mobile.png) |

### Documents in dark theme

| Desktop — 1440 × 900 | Mobile — 390 × 844 |
| --- | --- |
| ![Desktop: Documents in dark theme](documents-dark-desktop.png) | ![Mobile: Documents in dark theme](documents-dark-mobile.png) |

### Mobile collapsed settings

![Documents: search and active tags remain visible at 390 × 844](documents-collapsed-mobile.png)

![People/entities: search and active tags remain visible at 390 × 844](people-collapsed-mobile.png)

![Scans: search and active tags remain visible at 390 × 844](scans-collapsed-mobile.png)

