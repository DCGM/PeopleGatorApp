# OIDC and provider replacement evidence

Actual Chromium captures from application revision `db957cb`, using synthetic
seeded data. Desktop is 1440 × 900 and mobile is 390 × 844 CSS pixels.
The resource API and issuer are independent processes. No bearer/refresh tokens
are persisted in browser storage or included in screenshots. Swagger operations
are collapsed before authorized screenshots so token-bearing Curl output is hidden.

The built-in journey uses frontend 5189, API 8089 and issuer 8189. Frontend
server-only proxies target the API/issuer, with OIDC authority at the frontend
origin. Run `node people-gator-app/scripts/check-oidc-login.mjs` after following
[Development](../../../DEVELOPMENT.md) with those ports. Existing auth-gateway and
Swagger check scripts remain compatibility entries for this standard journey.
Captures show light/dark issuer login, explicit failed-callback retry,
anonymous docs/Sign in, issuer login and failure, authenticated
docs, returned seeded app, logout and anonymous docs after SSO expires.

PR-prefill captures run the same independent issuer with the configured public
origin `https://pr-89.preview.peoplegator.dev:5195`, locally resolved and served
through a temporary TLS proxy. The form shows the synthetic `test` account only
on that exact PR hostname pattern, with password masked and explicit submission.
These are real issuer HTML responses, not frontend mocks. Local, staging, live
preview, production and lookalike hostnames were also checked for empty defaults.

## Separate Keycloak compatibility check

Keycloak **26.7.0** ran on loopback port 8194 with a disposable development realm.
The identical browser source was used at frontend 5194 and resource API 8094.
Only browser OIDC and API validation configuration changed. The synthetic
single-user realm maps the existing provisioned actor UUID and a flat permission
claim, and adds the API audience. No new actor UUID was generated for migration.
Keycloak screenshots show its own login form; app/docs code is unchanged.

Create a test realm from an existing **synthetic** account UUID:

```sh
uv run --locked python scripts/oidc_test_realm.py \
  --actor-id <existing-synthetic-actor-uuid> \
  --app-origin http://localhost:5194 \
  --output /tmp/people-gator-oidc-realm/realm.json
```

Start a disposable Keycloak container with that directory mounted read-only at
`/opt/keycloak/data/import`, bind port 8080 only to `127.0.0.1:8194`, and use
`start-dev --import-realm`. The fixture intentionally contains only the local
synthetic test account; do not import it into a shared or real-data realm.

Configure the second frontend with:

```dotenv
VITE_OIDC_AUTHORITY=http://localhost:8194/realms/people-gator-oidc
VITE_OIDC_CLIENT_ID=people-gator-browser
VITE_OIDC_SCOPE=openid profile
VITE_API_BASE_URL=http://localhost:5194
API_PROXY_TARGET=http://127.0.0.1:8094
```

Configure the second API's `AUTH` issuer to that realm, JWKS to its
`/protocol/openid-connect/certs`, audience `localhost`, algorithm `RS256`, actor
claim `uid` and scopes claim `permissions`. Use the same isolated seed store.
Then run the same browser script:

```sh
OIDC_APP_ORIGIN=http://localhost:5194 \
OIDC_AUTHORITY=http://localhost:8194/realms/people-gator-oidc \
OIDC_EVIDENCE=/tmp/people-gator-keycloak-evidence \
  node people-gator-app/scripts/check-oidc-login.mjs
```

Both providers passed desktop/mobile PKCE, callback/return query and fragment,
real Swagger protected requests, refresh, app/docs SSO, manual API-key isolation,
provider logout, expired SSO recovery and no persisted tokens. Tests also check
keyboard access and absence of an application header Sign out button. Non-Chromium
and physical-device checks were not run. Keycloak is a compatibility test, not a
new production deployment dependency.

## Rejected API-token recovery

A separate real API at port 8096 was configured with an intentionally unmapped
actor claim; frontend 5196 used the built-in issuer on frontend origin 5189 with
explicitly registered cross-origin callbacks. Desktop/mobile login completed,
the API rejected the signed token, and exactly one automatic reauthentication
was attempted before an explicit retry screen. No API responses were mocked.
This also verifies the issuer form CSP permits registered callback origins.

Reproduce with `OIDC_EXPECT_API_REJECTION=1`, `OIDC_APP_ORIGIN` set to that second
frontend and `OIDC_AUTHORITY` set to the issuer origin when running the same
browser script. These captures correspond to the recovery-hardening commit;
the earlier captures use the unchanged main OIDC flow from `db957cb`.
