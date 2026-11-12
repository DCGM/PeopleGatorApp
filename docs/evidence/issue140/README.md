# Expanded document pages (#140)

Actual production-build Chromium captures from this issue branch against its
isolated, migrated, twice-seeded local PostgreSQL instance and local media.
Desktop is 1440 × 900 CSS pixels; mobile is 390 × 844 CSS pixels.

The browser checks cover compact/expanded mode, row-first ordering, vertical
pagination across the 18-page fixture, preserved current/person highlight
semantics, person-only face-or-mention filtering, excluded current pages,
opening a page, URL reload/Back/Forward, keyboard collapse, source-UUID redirects,
empty results, missing media, dark theme and absence of horizontal overflow.
The expanded grid reserves room for the vertical scrollbar so thumbnail
outlines stay visible. The collapse control stays outside the scrolling header.

Reproduce after `npm ci` / `uv sync --locked` and the local migration → seed →
seed setup described in `docs/DEVELOPMENT.md`:

```sh
# The CLI prints a JSON object followed by exploration links. Extract the JSON
# report without printing credentials; the report contains synthetic fixture IDs.
cd people-gator-api
python3 - <<'PY'
import json
from pathlib import Path
report, _ = json.JSONDecoder().raw_decode(Path('.cache/seed-second.json').read_text())
Path('.cache/seed-report.json').write_text(json.dumps(report))
PY
cd ../people-gator-app
npm run build
npm run preview -- --host 127.0.0.1 --port 5140 --strictPort
# In another shell, from people-gator-app:
PAGE_BROWSER_ORIGIN=http://127.0.0.1:5140 node scripts/check-page-browser.mjs
```

The API origin is configured at build time; these captures use 127.0.0.1:8140
and synthetic demo authentication. `PAGE_BROWSER_SEED` and
`PAGE_BROWSER_EVIDENCE` override the report and output paths.

Files pair `desktop-*` and `mobile-*` for compact, expanded, person-only,
missing-media, empty and dark states. Source data and image files are entirely
synthetic; no project or production store is used.

Dependency: this branch stacks on #133 / #131. Current main was synchronized
into this branch without modifying the prerequisite branch. No API schema,
SDK or database migration changes are introduced by #140.
