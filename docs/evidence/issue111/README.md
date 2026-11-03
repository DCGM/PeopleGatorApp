# Documents table evidence (#111)

Captured from the running local application with synthetic PostgreSQL fixtures,
local storage, and Chromium 156.0.8078.4. Desktop is 1440 × 900 and mobile is
390 × 844 CSS pixels. No remote dataset or inference service was used.

## Reproduction on main f06c3f6

Open `/documents?library=preview-pagination`, enable First page in Columns,
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

The Documents view now uses available content width with one table overflow
region bounded to min(65dvh, 26rem). Its header stays at that region's top while
rows scroll. The loading sentinel is inside it and sticks to its left edge, so
horizontal position cannot hide the cursor-loading trigger. The normal page can
still scroll to reach the table below expanded filters or many active tags.

`people-gator-app/scripts/check-document-navigation.mjs` ran successfully at both
viewports against migrated, twice-seeded PostgreSQL and local media. It checked:

- Exact eight-column defaults, header/body/colgroup alignment, stable pixel
  widths and no document-level horizontal overflow.
- Wheel and focused-region keyboard scrolling; sticky header visibility;
  one real opaque cursor request at left, middle and right positions, with all
  19 scenario documents reachable and horizontal position retained.
- Mobile horizontal/vertical touch swipes dispatched through Chromium's input
  protocol. Physical touch and trackpad hardware were not tested.
- Keyboard resizing and restoring a title column; sort and load operations
  preserve its width model.
- Header keyboard sorting through ascending, descending and clearing; shared
  selector, URL, Back/Forward, and real server requests stay synchronized.
  Clearing restores name ascending for browse or relevance for search.
- Session column choices survive reload and navigation away/back; Restore defaults
  restores the eight fields. Unit tests separately cover invalid/obsolete stored
  IDs and blocked storage reads/writes.
- Document/library/first-page links, canonical full-document totals, empty pages,
  missing media, and light/dark rendering without browser page errors.

The after images show defaults, Columns settings, a vertically/horizontally
scrolled table and dark mode. The mobile default capture scrolls the normal page
slightly to show the complete table region below the five active library tags.
