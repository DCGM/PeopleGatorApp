# Standalone login evidence

Actual Chromium captures from the twice-seeded isolated instance, using separate
issuer (8189), API (8089) and browser application (5189) processes. The gateway
shares the browser origin with the application; issuer calls use configured CORS.
Desktop is 1440 × 900 and mobile is 390 × 844 CSS pixels. Captures show initial
login, failed login, expired-session recovery and returned seeded results with
Sign out. Login fields were cleared before failed-login captures.

Reproduce with `node people-gator-app/scripts/check-auth-gateway.mjs` and the
synthetic local setup in [Authentication](../../AUTHENTICATION.md). The script
checks keyboard field/button order, full return path, successful login, refresh
rotation, session expiry/recovery, logout, bounded page width and browser errors.
No physical-device or non-Chromium checks were performed.
