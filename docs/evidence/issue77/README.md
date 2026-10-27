# Issue #77: scan annotations without hover popups

Real Chromium captures of the running issue branch with isolated PostgreSQL and
synthetic local preview media. Desktop: **1600 × 900 CSS pixels**. Mobile:
**390 × 844 CSS pixels**, with touch enabled. Light and dark captures show the
`scan-annotation-hover` preview example (Annotation review ledger, preview-mzk).

- `scan-*`: pointer over the verified scan face.
- `transcription-*`: pointer over the Irena Evidence transcription mention.
- `gallery-*`: pointer over the verified Page faces thumbnail.

Visible state icons and selection highlights remain. No annotation tooltip is
open in these states. The sidebar's existing current-face details are retained.
The before capture is linked from [issue #77](https://github.com/DCGM/PeopleGatorApp/issues/77).

Browser checks covered automatic, manual, verified and unassigned examples via
`scan-annotation-hover`, `scan-toolbar` and `scan-toolbar-union`: annotation
hover and native-title absence, Enter/Space activation, retained selection,
mobile touch activation and no horizontal document overflow. Component tests
also cover accessible names and shared badge tooltips outside this workspace.

The desktop width includes all three workspace columns. At 1440 pixels the
existing layout clips the transcription row; scan face hover was checked at
that width separately. Mobile's existing floating scan controls overlap part
of the face regions; hover/touch checks use their exposed lower area.
