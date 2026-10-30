# Person evidence review (#80)

Real Chromium captures of the running issue branch with synthetic local data.
Desktop is 1440 × 900 CSS pixels; mobile is 390 × 844. Each named state has a
matching `-desktop.png` / `-mobile.png` pair. `mobile-filters-mobile.png` also
shows the expanded below-640px controls.

Checks executed against the seeded API:

- Actual collapsed grid: 13 faces and an action card in two desktop rows, three
  faces and an action card in two mobile rows;
  expansion shows all 42, collapse restores two rows, and resizing to 700px
  recalculates two rows. The action tile has a transparent background, a subtle
  dashed outline, a thin plus icon and muted text in light and dark themes.
- Identity remains below the 52px sticky navigation deep in Faces. No horizontal overflow
  across captured states. Section tabs fit on one mobile row.
- Keyboard Enter expands mobile filters; Space selects a mention independently
  of its scan link. The info icon opens the shared two-line relative last-change
  and user display on hover, click or keyboard activation.
- Document/Page groups cover three distinct documents and nine pages; duplicate
  document titles stay separate. Grouping survives reload. Browser Back restores
  prior URL choices; old Discover URLs activate Faces and retain discovery text,
  model and local evidence scope.
- Verify on the selected 27-occurrence exact-text group reaches all 27 records,
  including seven unloaded children. Unlink with one library selected removes
  nine links, retains the 18 outside scope and preserves all 27 OCR records.
  Unfiltered tab totals refresh after the write.
- Found faces has no search input or modality selector. Face model and Assignment
  share one desktop line in that order. Similar people has its own search and matching
  selectors. Changes to either section preserve the other; typing people search
  never sends a face text query. Independent choices survive reload.
- Found faces uses the same tracks and metadata space as assigned faces:
  147.4 × 275.4px cards at desktop, 173 × 301px at mobile. It starts with 13/20
  candidates plus the action tile on desktop and 3/20 plus the tile on mobile.
  Show more reveals two rows at a time, fetching the next 14-record cursor page
  only when needed. All 20 candidates were reached without duplicates.
- Simulated next-page failures retain cards and selection; the tile changes to
  Retry and successfully continues the same cursor. The assignment selector
  starts a fresh server-filtered query; its count matches the returned records.
  Both retry states, filtered results and loaded-more results are captured.
- Light and dark grouping captures; no browser page errors in the checked flow.

Fixtures: Lina Archivist, 42 linked faces, 27 mentions in three documents;
Lina A. and an unassigned face provide discovery candidates. Statistics counts
both linked-page libraries across all pages.

Mention follow-up: default expanded groups and the global Expand/Compact option
were checked in all four views. Group headings have no individual expand controls. Compact groups retain selection controls; group
checkboxes cycle through none/some/all via the standard parent/child behavior.
Selecting all 27 also selects the seven children loaded later. Deselecting a child
shows a minus; changing density retains that state. Compact URL reload, orange
underlined spans in serif context, library labels, metadata hover/keyboard and no
horizontal overflow passed at both viewport sizes. `mentions-compact-*` records
the new global collapsed state; group/flat/document/page/dark/info pairs are refreshed.

Expanded mention groups retain separators between occurrences, but omit the
last child border and the load-more wrapper divider so only the outer group
separator marks the bottom. The Flat view also uses separators only between items.
Browser computed-border checks passed for Mention, Document and Page on
desktop and mobile.

Mention selection uses the shared floating face-action bar in every mode, with
matching position, responsive layout and Clear/Unlink/Verify controls. Browser
checks compare its CSS classes and bottom offset to Faces, clear selection in
all four mention views and exercise grouped selection through the same bar.
Expanded/compact, Flat/Document/Page/Mention and dark screenshots show the bar.

Shift-click checks passed at both viewport sizes: forward/reverse additive Flat
ranges, anchor reset after Clear, ranges spanning newly fetched cursor pages,
individual ranges across Document/Page boundaries with mixed parent checkboxes,
and compact whole-group ranges. `mentions-shift-flat-*`,
`mentions-shift-group-*` and `mentions-shift-compact-*` capture these selections.

Mention skeleton captures delay actual local API requests: three expanded groups
with two nested rows, three compact headers, dark theme, three pending nested/Flat
rows and two appended cursor rows. Desktop/mobile checks toggle density while
pending, confirm placeholders have no focusable controls, retain all 20 existing
occurrences during the next request and replace placeholders with all 27 records
on completion. `mentions-loading-*` provides each paired state.

Face-only discovery checks use a legacy URL containing name-only modalities and
text. Every Found faces request still sends only `query.entity_annotations=faces`
and omits text. Similar people retains its modality control and name/text query.
Desktop/mobile captures in `found-faces-face-only-*` show the simplified controls;
existing found-face pagination/retry/filter/theme evidence is refreshed.

Review follow-up: Page groups keep each document's pages together. Pages of the
two same-titled "Review ledger" documents no longer interleave, including across
cursor pages and under text/count sorting. Mention links and document/page group
headings show full document and page UUIDs, wrapping without horizontal overflow.
`mentions-page-*`, `mentions-document-*` and `mentions-flat-*` are refreshed;
`mentions-flat-compact-*` and `mentions-page-compact-*` show the compact labels.
Group Verify now skips occurrences that are already verified, so its count reports
only changed records. Other mention captures predate the full-UUID labels.

Document view group headings use the occurrence-link style at normal text size: an underlined
`library · document name` link that opens the document's scans
(`/scans?document=…`), without the document UUID. `mentions-document-*` is
refreshed; the link was followed at both viewport sizes without page errors.
