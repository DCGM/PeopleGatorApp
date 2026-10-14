# Implementation workflow

All future implementation jobs must follow this GitHub workflow:

**GitHub issue → issue branch → commits for functional units → pull request.**

1. Start from a GitHub issue. Read its full description and acceptance criteria
   before implementing. Reuse the relevant existing issue; if none exists, create
   one describing the problem, intended behavior and scope, then work against it.
2. Create or reuse a dedicated branch for that issue, with the issue number in
   its name (for example, `issue2` or `issue/2-description`). Base new branches on
   the intended PR target. Keep implementation work off the default branch and
   preserve unrelated user changes in the worktree.
3. Commit as each coherent functional unit is complete and appropriately
   verified. Make partial implementation commits reviewable and working; do not
   wait until the entire issue is finished to commit everything together. Scope
   each commit to its functionality and use a clear message explaining the change.
4. Push the issue branch and create or update its pull request. Link the GitHub
   issue, describe the resulting behavior, and record relevant validation and
   material limitations. Keep the PR description current as the implementation
   changes. Use a draft PR when work is still incomplete.
5. Address review and CI findings with further focused commits on the same issue
   branch. Finish through the pull request workflow; merge only when the user has
   authorized merging. Do not include unrelated work in the commits or PR.

# Keeping pull-request previews representative

The preview seed is part of the application's maintained interface. Whenever you
add or change user-visible behavior, API schemas, persistence contracts, source
relationships, vectors, media formats, authentication attribution, or filters:

1. Update `people-gator-api/src/people_gator_api/seeding/` in the same change.
   Keep existing examples compatible and add a small, usable scenario for new
   functionality. Include the linked records and local media it needs; a schema
   default alone does not demonstrate a feature.
2. Keep all seed database reads/writes behind `persistence.contracts.Database`
   and its repositories. Use validated API request schemas and real actor
   contexts. Use the `Filesystem` contract and canonical media-key helpers for
   files. Do not seed through raw SQL, ORM models, or backend client shortcuts.
3. Preserve stable fixture keys, source UUID identities, and checkpoint IDs.
   Preview redeployments retain their database and storage. Reruns must add
   missing examples without duplicating records, undoing review edits, resetting
   evidence assignments, or changing last-processed timestamps unnecessarily.
   When a feature needs an upgrade to existing seed records, implement an explicit,
   narrowly scoped additive upgrade rather than resetting the preview database.
4. Keep fixtures synthetic, deterministic and self-contained. Do not copy real
   user data, add usable credentials, download external images, or require an
   embedding/OCR service. Register named models before inserting finite vectors
   of the matching dimension. Keep faces/keypoints and OCR polygons inside the
   stored page image, and ensure seeded links resolve in the application.
5. Extend `tests/services/persistence/test_preview_seed.py` with meaningful
   coverage for the new scenario. Check the feature through repository queries
   or media services, not just record counts. Retain rerun/edit-preservation and
   interrupted-checkpoint recovery coverage. Run the seed twice against an
   isolated, migrated PostgreSQL database and disposable local storage.
6. Update `people-gator-api/docs/preview-seeding.md` with the coverage and a way
   to explore it. Preserve PR deployment order: storage initialization, schema
   migration, seed, then backend/frontend startup. Seed failure must prevent the
   candidate deployment from being marked successful.

The PR CI workflow smoke-tests the real migration/seed CLI twice in a separate
`ci_seed` database and runs the seed integration tests with
`PEOPLE_GATOR_SCHEMA_TEST_URL`. Preview lifecycle tests live in
`deploy/preview/tests/`. Host controller/Compose changes must be installed from a
reviewed default-branch checkout as described in `deploy/preview/README.md`; PR
code must not replace the trusted host controller directly.

# Search and filter panels throughout the application

These rules apply everywhere in the application that provides search or filters,
including documents, scans, entities and annotation/discovery controls. Apply
these rules to new panels and changes to existing panels while retaining each
screen's filter semantics.

- Use 100% of the parent element's available width. Arrange controls in natural
  DOM order, left to right, using `display: flex`, `flex-direction: row` and
  `flex-wrap: wrap`. Use flexbox, not CSS floats, and include gaps in width
  calculations to avoid horizontal overflow.
- Search is always the first control, before filters and actions. A filters-only
  panel must not invent a nonfunctional search field.
- At `lg` (1024px and wider), search occupies the first half of the panel and
  filters begin at half its width, using the remaining half. At `sm` through
  below `lg` (640–1023px), search occupies the first two thirds and filters begin
  at two thirds, using the remaining third. These positions refer to the parent
  panel's width, not the viewport. Filters are visible and wrap left to right
  within their area at both sizes.
- Below 640px, keep search available beside a sliders icon button. Filters are
  collapsed by default and expand below that row across the full panel width.
  Use the standard shadcn-vue `Collapsible`; the toggle needs an accessible name,
  `aria-expanded`, and keyboard operation. Collapsing preserves search and all
  selected values.
- Use standard shadcn-vue setting controls: Input/InputGroup, Select,
  Popover/Command or Combobox for multi-select, Calendar, Button and Collapsible.
  Use standard variants and sizes. Only layout changes are allowed: width,
  flex basis/grow/shrink, wrapping, spacing, alignment and responsive placement.
  Do not override colors, backgrounds, borders, rounding, shadows, typography,
  or hover/focus/disabled states, or modify `src/components/ui/` for these panels.
  Shared filter controls must follow these same restrictions.
- Display active filters as standard Badge tags in a separate wrapping area
  below the panel, outside its container/card and before results. Each tag names
  its filter type and value and has an accessible X removal button, including
  removal of individual multi-select values. Removal updates the setting
  control, URL and results immediately. A standard clear-all button preserves
  search text; clearing search is a separate action. Tags stay accessible when
  mobile settings are collapsed and never overflow the parent. Hide the entire
  area when no filters are active.
- Keep keyboard navigation, standard focus states, and light/dark themes usable.
