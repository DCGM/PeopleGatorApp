# Swagger gateway session evidence

Actual Chromium captures from the migrated synthetic instance at its frontend
origin, with docs/API proxying to the independently running API and login/refresh
targeting the independently running issuer. Desktop is 1440 × 900 and mobile is
390 × 844 CSS pixels. Captures show Authorize with Sign in, the existing gateway,
and docs after automatic bearer authorization. No token-bearing Curl panel is
visible; operations are collapsed before the authorized capture.

Reproduce with `node people-gator-app/scripts/check-swagger-session.mjs` using the
[local configuration](../../../DEVELOPMENT.md). The script checks return query and
fragment, keyboard navigation, real authenticated Try it out, refresh rotation,
existing app-session reuse, expired-session recovery and API-key isolation.
