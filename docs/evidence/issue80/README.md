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
- Found faces has no search input. Modalities, Face model and Assignment share
  one desktop line in that order. Similar people has its own search and matching
  selectors. Changes to either section preserve the other; typing people search
  never sends a face text query. Independent choices survive reload.
- Found faces uses the same tracks and metadata space as assigned faces:
  147.4 × 282px cards at desktop, 173 × 301px at mobile. It starts with 13/20
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
