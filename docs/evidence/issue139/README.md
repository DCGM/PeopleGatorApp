# Page panel visibility evidence (#139)

Actual Chromium screenshots from the local synthetic `page-panel-layout` seed
scenario, captured from frontend revision `bbb6e5c2` on 10 November 2026.
Desktop uses 1440 × 900 CSS pixels; mobile uses 390 × 844 CSS pixels.

Each viewport includes panels open, left hidden, right hidden, both hidden,
reopened, keyboard-resized and dark reopened states. On mobile the side panel is
stacked below the viewer; the dark capture scrolls to its reopened People tab.

The browser check exercised independent hide/reopen using pointer and keyboard,
focus transfer to the matching reopen button, unchanged source URL/settings,
retained pan/zoom nodes, restored expanded dimensions, keyboard resize, the
unchanged saved sidebar width through hiding, explicit face Search revealing and
focusing People, and desktop/mobile round trips while the panel remains hidden.
It also checked zero application page errors and no horizontal page overflow.
The scan toolbar scrolls horizontally inside its header on narrow screens.

The fixtures and local media are synthetic. No external inference service or
private collection data was used.
