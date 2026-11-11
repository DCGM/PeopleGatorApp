# Page panel visibility evidence (#139 / PR #146)

Actual Chromium screenshots from the running local application at frontend
revision `81f963dc`, using the migrated, twice-seeded synthetic
`page-panel-layout` scenario. Desktop: **1440 × 900** CSS pixels. Mobile:
**390 × 844** CSS pixels. Captures include current main's People defaults,
source tags and expanded page browser.

The desktop transcription hide action is at the right end of its header; the
People hide action is at the left end, beside the viewer. Hidden desktop panels
reopen from their corresponding viewer-header controls. On mobile, People stays
visible and has no hide action. Transcription collapses upward into a single
labelled **Transcription** bar, with a vertical reopen action.

| State | Desktop | Mobile |
| --- | --- | --- |
| Panels open | [Capture](desktop-panels-open.png) | [Capture](mobile-panels-open.png) |
| Transcription hidden / collapsed | [Capture](desktop-left-hidden.png) | [Labelled bar](mobile-left-hidden.png) |
| People hidden on desktop / always available on mobile | [Capture](desktop-right-hidden.png) | [Visible People section](mobile-people-visible.png) |
| Both desktop panels hidden | [Capture](desktop-both-hidden.png) | [Transcription collapsed; People remains below](mobile-left-hidden.png) |
| Reopened | [Capture](desktop-reopened.png) | [Capture](mobile-reopened.png) |
| Keyboard resized | [Capture](desktop-resized.png) | [Capture](mobile-resized.png) |
| Expanded page browser with reopen controls | [Capture](desktop-expanded.png) | [Capture](mobile-expanded.png) |
| Dark theme after reopening | [Capture](desktop-dark-reopened.png) | [People section](mobile-dark-reopened.png) |

Run from `people-gator-app` with the synthetic application listening locally:

```sh
PANEL_LAYOUT_ORIGIN=http://localhost:5139 \
PANEL_LAYOUT_SEED=../people-gator-api/.cache/issue139-review-seed.json \
node scripts/check-panel-layout.mjs
```

`PANEL_LAYOUT_SEED` is the JSON result object printed by the seed CLI, without
its following exploration-link lines. The script uses its stable scene links
and does not assume store-specific face UUIDs. `page-panel-layout-expanded`
opens the same linked evidence beside the expanded browser.

Validation completed:

- Production build/type checking passed; **530 frontend tests / 75 files passed**.
  Focused workspace, transcription and view tests passed **74 tests**.
- Actual browser checks passed at both viewport sizes: viewer-adjacent desktop
  buttons, labelled mobile bar, independent desktop collapse, keyboard focus,
  retained pan/zoom nodes and URL/settings, restored expanded dimensions,
  keyboard resizing, face Search reopening/focusing People, responsive round
  trips preserving desktop visibility/width while keeping mobile People
  available, expanded-grid collapse/reopen, dark theme and no page errors or
  horizontal overflow.
- Real migration → seed → seed → schema validation passed on isolated
  PostgreSQL `issue139` and disposable local filesystem storage. **Seven focused
  seed tests passed** against separate `issue139_schema_tests`, covering scene
  links/evidence/media, graph/vector integrity, review edits, interrupted
  recovery and document navigation.
- Full backend execution remains with PR CI; local checks above do not replace
  its result. Existing bundle-size/Vite configuration advisories remain.

All fixtures and local media are synthetic. No external inference service or
private collection data was used.
