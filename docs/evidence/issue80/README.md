# Person evidence review (#80)

Real Chromium captures of the running issue branch with synthetic local data.
Desktop is 1440 × 900 CSS pixels; mobile is 390 × 844. Each named state has a
matching `-desktop.png` / `-mobile.png` pair. `mobile-filters-mobile.png` also
shows the expanded below-640px controls.

Checks executed against the seeded API:

- Actual collapsed grid: 13 faces and an action card in two desktop rows, three
  faces and an action card in two mobile rows;
  expansion shows all 42, collapse restores two rows, and resizing to 700px
  recalculates two rows.
- Identity remains below the 52px sticky navigation deep in Faces. No horizontal overflow
  across captured states. Section tabs fit on one mobile row.
- Keyboard Enter expands mobile filters; Space selects a mention independently
  of its scan link. Context and import metadata open from the ellipsis button.
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
- Light and dark grouping captures; no browser page errors in the checked flow.

Fixtures: Lina Archivist, 42 linked faces, 27 mentions in three documents;
Lina A. and an unassigned face provide discovery candidates. Statistics counts
both linked-page libraries across all pages.
