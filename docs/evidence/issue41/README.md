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

## Assigned-person footer follow-up

The `*-actions.png` captures show all five controls aligned in the card footer
at the desktop/mobile sizes above. `*-create.png`, `*-verification-error.png`
and `*-verified.png` show creation/cancel, a failed verification inside the card,
and the already-verified state. The error capture uses an intercepted synthetic
503 response; no verification change is persisted.

Additional browser checks confirm a shared baseline and standard 24px button
heights, natural wrapping without overflow at 320px, accessible names for the
New/Unlink icon buttons, creation/cancel behavior, reassignment search focus,
error placement below the actions and verification details on the state badge.
All gallery captures were refreshed after this layout change.

## Outline action colors

The action row uses sky (faces), emerald (verify/save), amber (reassign/link),
violet (new identity) and destructive red (unlink/cancel) for text/icons and
borders. Backgrounds, border width/style, sizing and layout remain standard
shadcn outline controls. `*-actions-dark.png` shows the settled dark-theme colors;
all other captures were refreshed too. Browser style checks verify five distinct
text/border colors, shared neutral backgrounds, solid 1px borders, and a red
unlink border matching its text in both themes. Save and Cancel also use outline
variants. Theme captures wait for the standard color transitions to finish.
