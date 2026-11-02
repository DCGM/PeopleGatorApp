# Authentication and provider boundary

The browser uses OpenID Connect Authorization Code flow with mandatory S256 PKCE.
A shared provider interface supplies valid access tokens to the app and Swagger;
neither consumer knows provider endpoints, credentials or token storage keys.
The standard client uses `oidc-client-ts` for transactions/state/nonce/PKCE and
refresh, with `jose` validating ID-token signature, issuer, audience and expiry.

`people-gator-auth` runs the independent `people_gator_auth` application package.
It owns the built-in login form, accounts, private keys and durable issuer-only
sessions. It imports no resource application/settings/database/media/inference.
The resource API imports no issuer application. Both entry points share a wheel
and image to preserve reviewed deployment-controller compatibility. The explicit
provisioning CLI belongs to resource-side setup, not running issuer startup.
See [Issuer implementation](../people-gator-api/docs/ISSUER.md).

## Browser flow and storage

1. `/login.html` starts authorization at the configured provider; passwords are
   entered only on the provider's page.
2. The provider authenticates the user and redirects to an exact registered
   application callback with a temporary authorization code and state.
3. The OIDC client validates transaction state, exchanges the code using PKCE,
   validates nonce and verifies the ID token. It restores the validated original
   path, query and fragment before resource requests or application routing.
4. Access tokens are sent as bearer credentials. Refresh is coalesced and performed
   through the provider's standard token endpoint when expiry approaches.

Access, refresh and ID tokens stay in memory. Session storage contains only
short-lived state/nonce/PKCE transactions and a non-secret issuer/client SSO hint.
Legacy custom-provider stored tokens are removed. A full navigation or reload
can recover fresh tokens through a top-level `prompt=none` authorization round
trip using the provider's HttpOnly login-session cookie. This does not rely on
third-party iframe cookies. Without a valid provider session, docs remain public;
protected app use starts an interactive sign-in. Callback failures show an
explicit retry, never automatically replay a code or loop redirects.

Application callbacks are `/auth-callback.html` for app pages and `/docs` for
Swagger. The app callback initializes OIDC before mounting the router in that
same document. Swagger completes its callback in its own document; no token
handoff between page storage or navigation URLs is necessary. Credentials and
access/refresh tokens are never placed in navigation URLs. Standard logout may
use an ID-token hint, which is not an API bearer credential.

The built-in issuer form prefills the synthetic `test` account only when its
configured public hostname exactly matches `pr-<number>.preview.peoplegator.dev`.
Submission is still required. Local/staging/production forms start empty. The
application header has no Sign out control; provider/client logout remains tested.

## Configuration and topology

| Process | Settings |
| --- | --- |
| Resource API | `PEOPLE_GATOR_API__AUTH__ISSUER`, `AUDIENCE`, `JWKS_URL`, `ALGORITHMS` (ES256/RS256), `ACTOR_CLAIM` (default `uid`), `SCOPES_CLAIM` (default `scopes`) |
| Built-in issuer | `PEOPLE_GATOR_AUTH__ISSUER`, `AUDIENCE`, `STATE_DIR`, optional exact `CLIENTS` registrations, `ALLOW_ORIGINS`, lifetimes and port |
| Browser | `VITE_OIDC_AUTHORITY` (default browser origin), `VITE_OIDC_CLIENT_ID` (default `people-gator-browser`), `VITE_OIDC_SCOPE` (default `openid profile offline_access`), `VITE_API_BASE_URL` |
| API keys | `PEOPLE_GATOR_API__API_KEYS__KEYS_PATH`, `IDENTITY_ISSUER`; keep the retained identity issuer independently of a bearer-provider replacement |

`VITE_AUTH_BASE_URL` remains a compatibility alias for the OIDC authority, not a
custom password API base. These public build settings contain no client secret.
The maintained proxy sends `/token/`, `/.well-known/` and `/auth/health` to the
issuer, `/api/`, `/docs` and `/openapi.json` to the resource API, and frontend
entries/assets to the frontend. Issuer and application may be on different
origins with exact callback registrations and provider CORS settings. Use HTTPS
except loopback development. Native Vite uses `API_PROXY_TARGET` and
`AUTH_PROXY_TARGET`; see [Development](DEVELOPMENT.md).

## Swagger

Open `/docs` at the application origin. **Authorize → Sign in** starts the same
provider flow and preserves the selected operation, query and fragment. An
existing issuer SSO session can authorize docs without another password prompt.
The request hook obtains fresh access tokens from the shared interface before
**Try it out** and limits managed credentials to same-origin `/api/` requests.

FastAPI serves standard Swagger HTML through a small wrapper loading the
frontend's no-store `/swagger-auth.js`. Manual bearer tokens and API keys remain
supported. Choosing a manual key clears only Swagger's managed bearer. Anonymous
docs remain usable when provider recovery fails. The resource API still owns no
passwords, signing keys or refresh state, and its HTTP bearer/API-key security
schemas remain unchanged. Raw API-origin docs support manual authorization;
use the frontend origin for integrated login. ReDoc remains reference-only.

## Replacing the issuer with Keycloak

Use a public OIDC client, enable Standard Flow and enforce S256 PKCE. Register
both exact application callbacks and the exact `/login.html` post-logout URL;
register the browser web origin. Disable direct password grants. Set browser
OIDC authority/client/scope and resource issuer/JWKS/audience/algorithm/claim
settings; no browser adapter or resource-router edits are needed.

Keycloak commonly issues RS256 access tokens and a `scope` claim. Configure a
space-separated custom permissions claim when application permissions differ
from OIDC scopes. Configure the API audience and a UUID claim containing the
**existing persisted application user UUID**. A Keycloak subject is not a
replacement UUID; provision/map identities explicitly and preserve attribution.
Keep API-key identity configuration independent during this transition.

For ordinary Keycloak browser sessions, `VITE_OIDC_SCOPE="openid profile"`
receives refresh tokens within the provider's session policy. Request
`offline_access` only when the user/client is explicitly permitted offline
sessions; otherwise Keycloak rejects the exchange. This scope is configurable.
The same browser journey was exercised against the built-in issuer and a separate
Keycloak instance; see the PR for exact executed evidence/version and limitations.

## API validation and permissions

Access tokens require a trusted signature, issuer/audience, nonempty subject,
integer issued-at/expiry, a UUID actor claim and space-separated permissions.
Only configured ES256/RS256 algorithms are accepted. The API rejects built-in ID
and refresh tokens as access credentials. External access tokens may omit
`token_use` or mark it `access`. Endpoint permissions remain explicit; admin
permission does not implicitly grant every other permission. Bearer
validation/actor construction performs no database lookups.

Public keys come only from configured `JWKS_URL`, never token-supplied URLs.
Redirects are refused. Fetches have a five-second timeout, 64 KiB/64-key bounds,
coalescing and a five-second retry cooldown. Public keys are cached for one hour
by default; usable cached keys permit validation during outages until TTL expiry.
Unknown keys remain 401; an unavailable provider with no usable cache returns
503. Publish overlapping keys before signing with a rotated key. Existing
worker caches cannot be revoked instantly; restart workers or adjust TTL when
required. No local/private-key fallback exists in the API.

## Provisioning, account policy and rollout

`people-gator-auth-provision /private/retained-users.json` explicitly maps the
retained issuer/subject to `Database.users.get_or_create`, then publishes issuer
accounts after the resource transaction commits. Reruns add missing accounts
without replacing passwords, permissions, UUIDs or account disablement. Keep
provisioning single-writer. The issuer itself never connects to that database.

Retain issuer `accounts.json`, `jwks.json` and `oidc.sqlite3` outside utility
installations, separate from resource media/API-key storage. The initial upgrade
preserves account/key formats and existing access-token validity when issuer,
audience and keys remain unchanged. Legacy custom refresh tokens require fresh
OIDC login. Codes, sessions and rotated refresh tokens survive later restarts;
SQLite transactions serialize redemption across local workers.
Refresh-token replay revokes the active refresh family and SSO session. Multi-host
issuer replicas/shared network filesystem storage are unsupported.

Provider disablement blocks new login, SSO and refresh; issued access tokens stay
valid to expiry. A rejected disabled-account refresh is revoked. Resource
`/users` and `/me` remain domain profile/attribution operations. Their `is_active`
flag governs existing API-key access and does not administer the provider account.
Account provisioning must preserve historical user UUIDs and foreign keys.

Preview startup remains storage initialization → migration → seed → explicit
account provisioning → issuer/API/frontend health. Seed/provisioning failure
blocks activation. The reviewed-main deployment controller is unchanged; PR code
never becomes the host controller.

## Validation

Backend tests cover PKCE, code/client/redirect binding, expiry/replay/concurrent
redemption, nonce, refresh rotation, account policy, restart persistence, public
keys, alternate claim mappings, database-free bearer requests and import isolation.
The seeded lifecycle verifies real attributed mutations and identity preservation.
Run `node people-gator-app/scripts/check-oidc-login.mjs` against a synthetic
same-origin app/API proxy. Configure `OIDC_APP_ORIGIN`, `OIDC_AUTHORITY` and
`OIDC_EVIDENCE` for another instance/provider. It exercises desktop/mobile code
login and return, real protected Swagger requests, refresh, app/docs SSO, manual
API-key isolation, logout, expiry recovery and absence of persisted tokens.
