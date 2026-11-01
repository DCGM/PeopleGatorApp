# Standalone login evidence

Actual Chromium captures from the twice-seeded isolated instance, using separate
issuer (8189), API (8089) and browser application (5189) processes. The gateway
shares the browser origin with the application; issuer calls use configured CORS.
Desktop is 1440 × 900 and mobile is 390 × 844 CSS pixels. Captures show initial
login, failed login, expired-session recovery and returned seeded results and the standard header navigation. Login fields were cleared before failed-login captures.

Reproduce with `node people-gator-app/scripts/check-auth-gateway.mjs` and the
synthetic local setup in [Authentication](../../AUTHENTICATION.md). The script
checks keyboard field/button order, full return path, successful login, refresh
rotation, session expiry/recovery, bounded page width and browser errors.
No physical-device or non-Chromium checks were performed.

Initial login and expired-session captures also exercise the PR-only prefilled
synthetic account. These were refreshed from the production build served locally
over TLS with a `pr-89.preview.peoplegator.dev` browser hostname. Separate local
hostname checks confirm both fields start empty outside PR previews.
