# Issue #41 browser evidence

Captured from this branch's running Vite/API application against a migrated,
synthetic PostgreSQL store after running the real seed CLI twice. Desktop uses
1440 × 900 CSS pixels; mobile uses 390 × 844 CSS pixels. Images contain synthetic
illustrations and no private collection data.

Each viewport includes:

- `*-compact.png`: assigned identity and compact workspace cards.
- `*-assigned-open.png`: the current identity's first six reference faces.
- `*-candidate-more.png`: a candidate's eleven linked faces loaded, scrolled to
  the end inside the bounded gallery.
- `*-empty.png`: mention-only Nora Svoboda's explicit empty state.
- `*-dark.png`: the expanded candidate gallery in dark mode.

Browser checks exercised mouse hover/leave, click pinning, touch opening,
Enter/Space, arrow-key isolation, Escape with focus return, outside dismissal,
progressive loading, scroll overflow, reopening cached evidence, empty states,
light/dark rendering and viewport width. Gallery requests used only the exact
identity with six-item batches; inherited library/link-state filters were absent.
No mutation requests occurred; the scan URL, selection and pan/zoom transform
remained unchanged through reference browsing.
