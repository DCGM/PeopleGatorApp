# Documents table evidence (#111)

Captured from the running local application with synthetic PostgreSQL fixtures,
local storage, and Chromium 156.0.8078.4. Desktop is 1440 × 900 and mobile is
390 × 844 CSS pixels. No remote dataset or inference service was used.

## Reproduction on main f06c3f6

Open `/documents?library=preview-pagination`, enable First page,
and scroll vertically by 600px with a browser wheel event. With the first 12
rows, the unbounded table region measured 1916px high. Its horizontal scrollbar
was at y=2327.5 on desktop and y=2239.5 on mobile, below either viewport.
After the vertical scroll, the header occupied y=-188…-108 on desktop and
-276…-196 on mobile, so it could no longer identify horizontally scrolled cells.
The before images show those initial/scrolled states from main's source files.

This reproduces the navigation/scrollbar and disappearing-header problems. Wheel
scrolling itself worked; the original report did not specify a browser or a more
precise stuck-scroll interaction.

## Result and browser validation

The Documents view uses available content width. The page has no footer, title or subtitle, only the small Documents index label. On desktop, the table fills the entire remaining viewport below the filters, and scrolling to its last row loads the next batch (there is no Load more button). On mobile, the table section fills the viewport below the sticky top bar, which therefore never covers the table header. The standard shadcn-vue ScrollArea supplies both scrollbars; the header stays at its viewport top while rows scroll. The loading sentinel is inside it and sticks to its left edge, so
horizontal position cannot hide the cursor-loading trigger. The normal page can
still scroll to reach the table below expanded filters or many active tags.

`people-gator-app/scripts/check-document-navigation.mjs` ran successfully at both
viewports against migrated, twice-seeded PostgreSQL and local media. It checked:

- No footer, page title or Load more button; the Documents index label remains. The desktop table fills the remaining viewport, and resizing from 900px to 1200px gives the table the additional 300px. The mobile table section fills the viewport below the top bar, with its header uncovered.
- Both standard shadcn scrollbars are present.
- Exact eight-column defaults, header/body/colgroup alignment, stable pixel
  widths and no document-level horizontal overflow.
- Wheel and focused-region keyboard scrolling; sticky header visibility;
  one real opaque cursor request at left, middle and right positions, with all
  19 scenario documents reachable and horizontal position retained.
- Mobile horizontal/vertical touch swipes dispatched through Chromium's input
  protocol. Physical touch and trackpad hardware were not tested.
- A held cursor request keeps the twelve existing rows and appends exactly one aligned skeleton row, which disappears when the seven additional rows arrive.
- Keyboard resizing and restoring a title column; sort and load operations
  preserve its width model.
- Header keyboard sorting through ascending, descending and clearing; shared
  selector, URL, Back/Forward, and real server requests stay synchronized.
  Clearing restores name ascending for browse or relevance for search.
- No Columns button. The last **Add column** column fills the remaining width (desktop, after removing a column) or keeps 160px. Clicking a body cell in it opens the header menu, which lists only hidden fields grouped as Document fields, Annotations, Faces and Mentions. Count headers show their title with the mode (All, Automatic, …) in small text below. Choosing one appends that column last and closes the menu.
- Dragging a header's top handle (mouse on desktop, Chromium touch events on mobile) shows a drop indicator and moves the column without scrolling the table; the order survives reload. ←/→ on the handle moves it one position and announces the new position.
- Removal sits behind the header label: clicking it opens a menu with a red **Remove column** item. Escape closes the menu without removing; choosing the item removes the column.
- Session column choices and order survive reload and navigation away/back; Restore default columns
  restores the eight fields and default order. Unit tests separately cover invalid/obsolete stored
  IDs and blocked storage reads/writes.
- Document/library/first-page links (document links and thumbnails open the first-page viewer/editor), canonical full-document totals, empty pages,
  missing media, and light/dark rendering without browser page errors.

The after images show defaults, the Add column menu, a drag in progress, removal confirmation, a vertically/horizontally
scrolled table, ascending/descending sort controls and dark mode. The mobile default capture scrolls the normal page to show its full-height table section below the filters. First-page editor captures show the destination of document and thumbnail links.
