# Issue 16: staging sign-in evidence

Captures show the actual staging-only `staging-login.html` (now
`deploy/people-gator-deploy/src/people_gator_deploy/assets/staging-login.html`) from
this issue branch, served with the compiled application and real API against a
disposable, migrated PostgreSQL/pgvector 16 database containing synthetic preview
data. No production data, usable deployment credentials or tokens are included.

| State | Desktop (1440 × 900 CSS pixels) | Mobile (390 × 844 CSS pixels) |
| --- | --- | --- |
| Sign in, light | [Capture](login-desktop.png) | [Capture](login-mobile.png) |
| Annotator account/permissions selected | [Capture](permissions-desktop.png) | [Capture](permissions-mobile.png) |
| Failed sign-in | [Capture](error-desktop.png) | [Capture](error-mobile.png) |
| Sign in, dark | [Capture](login-dark-desktop.png) | [Capture](login-dark-mobile.png) |

`capture.cjs` performs the browser checks and captures. It accepts a local-only
`STAGING_CAPTURE_URL` and optional synthetic `STAGING_CAPTURE_PASSWORD`, plus
`PLAYWRIGHT_MODULE` when Playwright is not installed in Node's normal module path.
Serve the compiled app with `VITE_API_BASE_URL=/`, the static sign-in page and
same-origin proxy routes `/api/` and `/token/` to the actual API. Provision only
synthetic staging example credentials in a disposable S3 bucket using
`staging.storage.example.json` and the staging preparation worker. The existing
captures show the unchanged sign-in UI; the S3 storage correction is verified by
the separate disposable TLS S3 runtime suite.

Executed Chromium checks at both viewports:

- Keyboard account selection updates the documented permission set.
- Invalid credentials produce an announced error and restore password focus.
- Valid annotator login establishes a session consumed by the real app; people
  search loads the synthetic/sanitized entity list.
- Viewer login requests browse scope only; a real entity mutation is rejected
  with HTTP 403 by the backend.
- No horizontal overflow in either viewport or light/dark capture.

The page is mounted only by staging Compose; PR previews keep their existing
synthetic demo authentication. Deployment, migration, data-isolation and recovery
checks are separate from these screenshots; see
[the deployment utility guide](../../../deploy/people-gator-deploy/README.md).
