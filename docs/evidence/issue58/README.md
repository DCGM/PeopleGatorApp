# Issue #58 discovery evidence

Captured from the production Vite build against an isolated, migrated PostgreSQL
store and synthetic local media. The migration → seed → seed → schema-check CLI
sequence passed before starting the API and frontend. No external inference or
private dataset was used.

Each state has desktop **1440 × 900** and mobile **390 × 844** captures:

- `all-inputs`: compact entity discovery with all reference inputs; mobile settings
  start collapsed while search remains available.
- `input-choices`: open Reference inputs combobox; mobile settings expanded.
- `faces-only`: selected source tag, compatible matches and finite face scores.
- `aliases-only`: recorded-alias inputs and text matches, without fake cosine scores.
- `no-signal`: real API 422 from a faces-only model without compatible reference
  embeddings, with source controls and Retry available.

Real Chromium checks at both viewports covered keyboard opening of the settings
and source chooser, selection of faces/aliases/name and combinations, selected
values in URLs and API requests, mobile collapse preserving source values/tags,
individual tag removal, empty-input guidance, clearing sources while retaining
search and evidence state, and retry/recovery from the no-signal error. Every
observed discovery request used the entity contract without enumerated face IDs.
The rendered pages had no horizontal overflow or browser JavaScript errors.

Automated component tests additionally cover assignment/merge selection, source
removal/reset and error retry; query tests check cursor/cache reset when changing
or revisiting source choices and entity IDs. Browser captures supplement those
checks and do not assert visual equivalence to the unavailable reported dataset.
