# Document creation columns (#128)

Actual Chromium captures of the migrated, twice-seeded synthetic application.
Desktop is 1440 × 900 CSS pixels; mobile is 390 × 844 CSS pixels. The scenario
is `/documents?library=preview-creation&sort=name`. Existing table controls were
used to keep Document name and add Created / Created by. Mobile captures scroll
the table horizontally to show the date and creator separately.

- `desktop-creation.png` / `mobile-creation.png`: created dates and Unknown legacy values.
- `desktop-creation.png` / `mobile-creator.png`: user and API-key creator attribution.
- `desktop-add-columns.png` / `mobile-add-columns.png`: both optional columns in Add column.

Reproduce from `people-gator-app`, with the API and frontend running from this
revision against isolated PostgreSQL and disposable local storage:

```sh
DOCUMENT_CREATION_ORIGIN=http://127.0.0.1:5128 \
DOCUMENT_CREATION_EVIDENCE=../docs/evidence/issue128 \
node scripts/check-document-creation.mjs
```

The script checks hidden defaults, add, keyboard move, remove/re-add, session
reload persistence, dates, user/API-key names, Unknown values, absence of creation
sorting and absence of document-level horizontal overflow at both viewports.
It fails on browser errors. Physical touch/trackpad devices were not tested.

The [creation-filter evidence](creation-filters/README.md) covers the shared date,
creator and API-key controls on the Documents, Scans and People screens.
