# Issue #41 browser evidence

Real browser captures from the running Vite/API application with a migrated,
synthetic PostgreSQL store and disposable local media. Desktop uses 1440 × 900
CSS pixels; mobile uses 390 × 844. Images contain synthetic illustrations.

The face popover is a compact 256px-wide grid with 8px outer padding, 4px gaps,
a bounded 160px scroll area. There is no close button, title, count or normal
loading button. Clicking outside, pressing Escape or toggling View faces dismisses
the gallery. The identity retains an accessible name.

Each viewport includes:

- `*-assigned-open.png`: reference faces from the currently assigned card.
- `*-candidate-more.png`: a candidate's eleven linked faces loaded and scrolled.
- `*-empty.png`: mention-only Nora Svoboda's explicit empty state.
- `*-dark.png`: the compact candidate gallery in dark mode.
- `*-sentinel-start.png`, `*-sentinel-end.png`, `*-sentinel-dark.png`: Zora
  Cartographer's 15 existing faces, automatically loaded in three batches.
- `*-compact.png`, `*-actions.png`, `*-actions-dark.png`: compact workspace cards
  and the aligned action row in both themes.
- `*-create.png`, `*-verification-error.png`, `*-verified.png`: creation/cancel,
  a failed verification inside the card and the already-verified state. The error
  capture uses an intercepted synthetic 503; no verification is persisted.

Gallery checks cover lazy opening, mouse hover/leave, click/touch pinning,
Enter/Space, keyboard scrolling, Escape/focus return, outside dismissal, cached
reopening, empty states, light/dark rendering and viewport width. A visible end
sentinel loads 6→12; scrolling loads the final batch to 15. Three distinct
cursors, no requests after exhaustion, no manual loading button, no title/counter,
no mutations and unchanged scan route/selection/pan/zoom were verified in both
viewports. Latest captures also check the padding/width, absence of a close
button and dismissal on the first outside click after interacting with a crop. Normal color transitions settle before theme captures.

Footer checks verify aligned 24px controls, natural wrapping at 320px, accessible
New/Unlink names, creation/cancel, reassignment focus and errors below the actions.
Only text/icons and borders carry sky (faces), emerald (verify/save), amber
(reassign/link), violet (new identity) and red (unlink/cancel). Standard outline
backgrounds, border geometry, sizing and focus states remain intact.
