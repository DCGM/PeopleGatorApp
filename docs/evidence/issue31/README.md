# Shared filters and document navigation — issue #31

Actual Chromium captures with the maintained synthetic PostgreSQL/local-media
preview. Linked-face colors, selection, identity and profile captures are refreshed
at `c67e6c0`; unchanged navigation/list/pane captures remain from `c5dd377`.
Desktop viewports are **1440 × 900** and mobile viewports **390 × 844 CSS pixels**.
Full-page captures retain those CSS widths. Obsolete captures have been removed.

## Verified interactions

- The document-pages preview finds **Příběhy archivářů**. Its heading opens all
  six registered pages, including the page with no face or mention annotations.
  The outgoing request has library/archive scope and no invented annotation
  document/library predicate. Browsing from a library-scoped document list also
  retains all six pages.
- Selecting the importer API key shows four pages; removing its tag restores six.
  Controls, tags, URL, API predicates and rendered results agree at both widths.
- People and profile controls share modification user/key/date and document/page
  criteria, library and assignment states. Mobile settings collapse without
  hiding active tags or changing selections. Creation/import and Last processed
  show separately recorded times and actors.
- Normal People breadcrumbs forward edited/cleared keys. Keyboard activation,
  Back, reload and old saved-return links preserve current filter state.
- Opening a scan leaves database assignment search available for Ada, whose
  evidence is outside the opened page. Explicit shared criteria still apply.
- Linked-face assignment rows use the shared state palette: Automatic blue,
  Manual amber, Verified green and Unassigned muted. In both themes and both
  viewports, browser checks compared actual foreground/background colors with
  the corresponding standard scan badges. All three assigned states are visibly
  distinct and remain colored during selection. The `linked-face-states` entry
  point reuses the existing synthetic profile and media.
- Space, Shift-range selection, click-to-add and Clear work for Faces. Green
  Verify and red Unassign actions remain available; compact Faces/Discover,
  source/editor rows, expanded creation/processing, Mentions empty state and
  Activity/Statistics were checked in the running app.
- Activity groups use actual annotation editors/dates. Selecting a reviewer
  constrains the Faces pane. Page/document statistics stay separately labeled.
- No JavaScript errors or horizontal overflow were observed. The affected
  profile/card states were checked in light and dark modes.

Screenshots show appearance; these interaction checks and the automated
regressions provide separate behavioral evidence. Fixtures, source identities,
review edits and media are synthetic and self-contained.

## Captures

### Linked faces — standard annotation-state colors (light)

| Desktop — 1440 × 900 CSS pixels | Mobile — 390 × 844 CSS pixels |
| --- | --- |
| ![Desktop: blue Automatic, amber Manual and green Verified linked faces](linked-face-state-colors-desktop.png) | ![Mobile: blue Automatic, amber Manual and green Verified linked faces](linked-face-state-colors-mobile.png) |

### Linked faces — standard annotation-state colors (dark)

| Desktop — 1440 × 900 CSS pixels | Mobile — 390 × 844 CSS pixels |
| --- | --- |
| ![Desktop: linked-face state colors in dark mode](linked-face-state-colors-dark-desktop.png) | ![Mobile: linked-face state colors in dark mode](linked-face-state-colors-dark-mobile.png) |

### Documents — shared criteria and separate processing settings

| Desktop — 1440 × 900 CSS pixels | Mobile — 390 × 844 CSS pixels |
| --- | --- |
| ![Desktop: Documents — shared criteria and separate processing settings](documents-desktop.png) | ![Mobile: Documents — shared criteria and separate processing settings](documents-mobile.png) |

### Document navigation — all six registered pages, including the unannotated page

| Desktop — 1440 × 900 CSS pixels | Mobile — 390 × 844 CSS pixels |
| --- | --- |
| ![Desktop: Document navigation — all six registered pages, including the unannotated page](document-pages-all-desktop.png) | ![Mobile: Document navigation — all six registered pages, including the unannotated page](document-pages-all-mobile.png) |

### Document navigation — explicit importer API key narrows results to four pages

| Desktop — 1440 × 900 CSS pixels | Mobile — 390 × 844 CSS pixels |
| --- | --- |
| ![Desktop: Document navigation — explicit importer API key narrows results to four pages](document-pages-filtered-desktop.png) | ![Mobile: Document navigation — explicit importer API key narrows results to four pages](document-pages-filtered-mobile.png) |

### Scans — expanded shared settings within document scope

| Desktop — 1440 × 900 CSS pixels | Mobile — 390 × 844 CSS pixels |
| --- | --- |
| ![Desktop: Scans — expanded shared settings within document scope](scans-desktop.png) | ![Mobile: Scans — expanded shared settings within document scope](scans-mobile.png) |

### People — shared API-key filter; mobile settings collapsed

| Desktop — 1440 × 900 CSS pixels | Mobile — 390 × 844 CSS pixels |
| --- | --- |
| ![Desktop: People — shared API-key filter; mobile settings collapsed](people-desktop.png) | ![Mobile: People — shared API-key filter; mobile settings collapsed](people-mobile.png) |

### People — shared settings expanded

| Desktop — 1440 × 900 CSS pixels | Mobile — 390 × 844 CSS pixels |
| --- | --- |
| ![Desktop: People — shared settings expanded](people-expanded-desktop.png) | ![Mobile: People — shared settings expanded](people-expanded-mobile.png) |

### Profile — modification user and API key selected together

| Desktop — 1440 × 900 CSS pixels | Mobile — 390 × 844 CSS pixels |
| --- | --- |
| ![Desktop: Profile — modification user and API key selected together](profile-filters-desktop.png) | ![Mobile: Profile — modification user and API key selected together](profile-filters-mobile.png) |

### Identity creation/import and Last processed — expanded by default

| Desktop — 1440 × 900 CSS pixels | Mobile — 390 × 844 CSS pixels |
| --- | --- |
| ![Desktop: Identity creation/import and Last processed — expanded by default](identity-expanded-desktop.png) | ![Mobile: Identity creation/import and Last processed — expanded by default](identity-expanded-mobile.png) |

### Faces — compact cards in light mode

| Desktop — 1440 × 900 CSS pixels | Mobile — 390 × 844 CSS pixels |
| --- | --- |
| ![Desktop: Faces — compact cards in light mode](compact-faces-light-desktop.png) | ![Mobile: Faces — compact cards in light mode](compact-faces-light-mobile.png) |

### Faces — compact cards in dark mode

| Desktop — 1440 × 900 CSS pixels | Mobile — 390 × 844 CSS pixels |
| --- | --- |
| ![Desktop: Faces — compact cards in dark mode](compact-faces-dark-desktop.png) | ![Mobile: Faces — compact cards in dark mode](compact-faces-dark-mobile.png) |

### Faces — Verify and Unassign selection actions in light mode

| Desktop — 1440 × 900 CSS pixels | Mobile — 390 × 844 CSS pixels |
| --- | --- |
| ![Desktop: Faces — Verify and Unassign selection actions in light mode](compact-faces-selected-light-desktop.png) | ![Mobile: Faces — Verify and Unassign selection actions in light mode](compact-faces-selected-light-mobile.png) |

### Faces — Verify and Unassign selection actions in dark mode

| Desktop — 1440 × 900 CSS pixels | Mobile — 390 × 844 CSS pixels |
| --- | --- |
| ![Desktop: Faces — Verify and Unassign selection actions in dark mode](compact-faces-selected-dark-desktop.png) | ![Mobile: Faces — Verify and Unassign selection actions in dark mode](compact-faces-selected-dark-mobile.png) |

### Discover — matching compact cards in light mode

| Desktop — 1440 × 900 CSS pixels | Mobile — 390 × 844 CSS pixels |
| --- | --- |
| ![Desktop: Discover — matching compact cards in light mode](compact-discover-light-desktop.png) | ![Mobile: Discover — matching compact cards in light mode](compact-discover-light-mobile.png) |

### Discover — matching compact cards in dark mode

| Desktop — 1440 × 900 CSS pixels | Mobile — 390 × 844 CSS pixels |
| --- | --- |
| ![Desktop: Discover — matching compact cards in dark mode](compact-discover-dark-desktop.png) | ![Mobile: Discover — matching compact cards in dark mode](compact-discover-dark-mobile.png) |

### Mentions — filtered empty state and recovery

| Desktop — 1440 × 900 CSS pixels | Mobile — 390 × 844 CSS pixels |
| --- | --- |
| ![Desktop: Mentions — filtered empty state and recovery](mentions-current-filters-desktop.png) | ![Mobile: Mentions — filtered empty state and recovery](mentions-current-filters-mobile.png) |

### Scan Activity — annotation changes grouped by local day

| Desktop — 1440 × 900 CSS pixels | Mobile — 390 × 844 CSS pixels |
| --- | --- |
| ![Desktop: Scan Activity — annotation changes grouped by local day](activity-time-desktop.png) | ![Mobile: Scan Activity — annotation changes grouped by local day](activity-time-mobile.png) |

### Scan Activity — annotation changes grouped by editor

| Desktop — 1440 × 900 CSS pixels | Mobile — 390 × 844 CSS pixels |
| --- | --- |
| ![Desktop: Scan Activity — annotation changes grouped by editor](activity-user-desktop.png) | ![Mobile: Scan Activity — annotation changes grouped by editor](activity-user-mobile.png) |

### Scan Statistics — separate page and document totals

| Desktop — 1440 × 900 CSS pixels | Mobile — 390 × 844 CSS pixels |
| --- | --- |
| ![Desktop: Scan Statistics — separate page and document totals](statistics-desktop.png) | ![Mobile: Scan Statistics — separate page and document totals](statistics-mobile.png) |

### Scan assignment — database search finds Ada outside the opened page

| Desktop — 1440 × 900 CSS pixels | Mobile — 390 × 844 CSS pixels |
| --- | --- |
| ![Desktop: Scan assignment — database search finds Ada outside the opened page](scan-assignment-navigation-desktop.png) | ![Mobile: Scan assignment — database search finds Ada outside the opened page](scan-assignment-navigation-mobile.png) |

### Profile — edited API key and expanded shared controls

| Desktop — 1440 × 900 CSS pixels | Mobile — 390 × 844 CSS pixels |
| --- | --- |
| ![Desktop: Profile — edited API key and expanded shared controls](profile-expanded-current-filters-desktop.png) | ![Mobile: Profile — edited API key and expanded shared controls](profile-expanded-current-filters-mobile.png) |

### Profile — normal breadcrumbs with current filters

| Desktop — 1440 × 900 CSS pixels | Mobile — 390 × 844 CSS pixels |
| --- | --- |
| ![Desktop: Profile — normal breadcrumbs with current filters](profile-standard-breadcrumb-desktop.png) | ![Mobile: Profile — normal breadcrumbs with current filters](profile-standard-breadcrumb-mobile.png) |

### Profile — normal breadcrumbs in dark mode

| Desktop — 1440 × 900 CSS pixels | Mobile — 390 × 844 CSS pixels |
| --- | --- |
| ![Desktop: Profile — normal breadcrumbs in dark mode](profile-standard-breadcrumb-dark-desktop.png) | ![Mobile: Profile — normal breadcrumbs in dark mode](profile-standard-breadcrumb-dark-mobile.png) |

### People — edited profile API key remains active after navigation

| Desktop — 1440 × 900 CSS pixels | Mobile — 390 × 844 CSS pixels |
| --- | --- |
| ![Desktop: People — edited profile API key remains active after navigation](people-updated-filters-desktop.png) | ![Mobile: People — edited profile API key remains active after navigation](people-updated-filters-mobile.png) |
