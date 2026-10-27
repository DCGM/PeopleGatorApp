# Person evidence review (#80)

Real Chromium captures of the running issue branch with synthetic local data.
Desktop is 1440 × 900 CSS pixels; mobile is 390 × 844. Each named state has a
matching `-desktop.png` / `-mobile.png` pair. `mobile-filters-mobile.png` also
shows the expanded below-640px controls.

Checks executed against the seeded API:

- Actual collapsed grid: 14 cards in two desktop rows, four in two mobile rows;
  expansion shows all 18, collapse restores two rows, and resizing to 700px
  recalculates two rows.
- Identity remains at the viewport top deep in Faces. No horizontal overflow
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
- Light and dark grouping captures; no browser page errors in the checked flow.

Fixtures: Lina Archivist, 18 linked faces, 27 mentions in three documents;
Lina A. and an unassigned face provide discovery candidates. Statistics counts
both linked-page libraries across all pages.
