# Authentication and provider boundary

`people-gator-auth` is an independent FastAPI process in the API distribution.
It imports neither the resource application nor its settings, database, media,
embedding or inference lifecycle. It owns local accounts, Argon2 verification,
private signing keys, account disablement and process-local refresh sessions.
The resource API exposes none of its routes. Export the separate issuer OpenAPI
with `uv run --locked python scripts/export_auth_openapi.py /tmp/auth-openapi.json`
from `people-gator-api`; resource export/client generation stays separate. `/docs` describes resource bearer
and API-key authentication; obtain tokens from the issuer separately.

## Configuration and topology

The maintained topology serves the app and `/login.html` at one browser origin.
`/token/`, `/.well-known/` and `/auth/health` route to the issuer, `/api/` to the
resource API. Tokens remain in that origin's tab-local sessionStorage. Return
navigation carries only a local application path, never tokens or credentials.
The gateway is a separate HTML/Vue entry, without resource queries or telemetry.
On `pr-<number>.preview.peoplegator.dev`, its username and password are prefilled
with the synthetic `test` account. Sign in still requires submitting the form.
Other hostnames, including staging and local development, start with empty fields.
An alternate issuer origin works with `VITE_AUTH_BASE_URL` and an explicit
`PEOPLE_GATOR_AUTH__ALLOW_ORIGINS` JSON list. The gateway must still be hosted at
the **application** origin; sessionStorage does not cross origins. Use HTTPS
outside isolated local development. This is direct credential exchange, not an
OIDC authorization-code flow; no PKCE, ID tokens or client registration exists.

| Process | Settings |
| --- | --- |
| Resource API | `PEOPLE_GATOR_API__AUTH__ISSUER`, `AUDIENCE`, `JWKS_URL`, `ALGORITHMS` (JSON list, ES256/RS256), `ACTOR_CLAIM` (default `uid`), `SCOPES_CLAIM` (default `scopes`) |
| Issuer | `PEOPLE_GATOR_AUTH__ISSUER`, `AUDIENCE`, `STATE_DIR`, `HOST`, `PORT` (8002), `ACCESS_TOKEN_LIFETIME_SECONDS` (7200), `ALLOW_ORIGINS` |
| Browser | `VITE_API_BASE_URL` and `VITE_AUTH_BASE_URL`; empty auth base uses the browser origin. No username/password build settings. |
| API keys | `PEOPLE_GATOR_API__API_KEYS__KEYS_PATH` and `IDENTITY_ISSUER`; set the latter to the retained identity issuer, independently of a future bearer provider. |

Consumer public-key settings do not contain paths to issuer keys/accounts. The
issuer directory contains `accounts.json` and `jwks.json`; keep it private,
writable by the issuer, backed up, and separate from resource storage. Startup
readiness (`/auth/health`) validates accounts and loads/creates signing keys.
The API never creates keys or substitutes local keys for provider failure.

## Swagger browser session

Open `/docs` at the same public origin as the app and gateway. In **Authorize**,
choose **Sign in** to open the existing login page; the return path, query and
operation fragment are preserved. Tokens stay in sessionStorage and never appear
in navigation URLs. Existing app sessions are applied automatically. The shared
frontend auth client refreshes managed tokens before **Try it out** requests.

The resource API serves the docs HTML and public OpenAPI; `/swagger-auth.js` is a
small frontend entry with no-store caching and hashed shared imports. The API
still owns no passwords, signing keys or refresh sessions. Bearer/API-key OpenAPI
contracts stay intact. Manual authorization is respected; selecting an API key
clears only Swagger's automatically applied bearer and leaves the app session.
Anonymous docs remain accessible when a saved session cannot be refreshed.
Managed app tokens are sent only to same-origin `/api/` resources.

For separate native dev servers, use the frontend's `/docs` and set server-only
`API_PROXY_TARGET` to the API URL, as in [Development](DEVELOPMENT.md). The raw API
origin is a different sessionStorage origin and supports manual authorization;
no cross-origin token handoff is assumed. ReDoc remains a reference view.

## Claims, scopes and keys

Access tokens require a trusted signature and `iss`, `aud`, nonempty string
`sub`, integer `iat` and `exp`, a UUID string `uid`, and space-separated string
`scopes`. Expiry and not-before are validated. Only configured algorithms are
accepted. Built-in tokens mark `token_use=access` or `refresh`; refresh tokens
also lack access-token actor/expiry claims. They cannot authorize resource calls.
External providers may omit `token_use` or use `access`; their access-token `jti`
is allowed. A valid signature still needs each endpoint's application scopes.

A future provider supplies the **existing persisted actor UUID**, using `uid`
or the configured actor claim, and space-separated scopes via the configured
scopes claim. Provision/map users explicitly before issuing tokens; never derive
a random UUID from a subject or resolve users on every resource call. Changing
provider issuer/keys and claim mapping requires no resource-router changes.
API-key identity mapping can retain the old issuer during a bearer transition.

JWKS comes only from configured `JWKS_URL`, never token `jku`, `x5u` or `iss`.
Redirects are refused. A per-process lock coalesces fetches; a five-second
`REFRESH_INTERVAL_SECONDS` bounds unknown-kid and failure retries. Successful
keys are cached for `KEY_CACHE_TTL_SECONDS` (3600). Known cached keys work during
outages until that TTL expires. A key miss refreshes once when the cooldown
permits; publish rotated keys before using them and allow the cooldown to pass.
Unknown keys remain 401. With no usable cached keys, network, provider or invalid
JWKS failures return 503, including during the retry cooldown. Fetches have a
five-second `TIMEOUT_SECONDS`, a 64 KiB bound and a 64-key bound. JWKS must contain
public EC/RSA material only. For emergency revocation, restart API workers or
reduce TTL in advance; removing a key cannot invalidate existing worker caches
instantly. Rotate by publishing overlapping public keys, then changing the
signing key and retiring the old public key after access tokens/cache expire.

## Accounts, provisioning and retained-data rollout

Before rollout, back up retained credentials, keys and user identities. Keep the
original issuer value when running the explicit provisioning bridge:

```sh
# With resource persistence/storage settings and issuer settings configured:
people-gator-auth-provision /private/retained-users.json
```

The source has the existing username → `{hash, scopes}` shape. This operator
command uses `Database.users.get_or_create` by issuer/subject and stores the
persisted UUID with each provider account. Existing identities and historical
foreign keys stay unchanged; newly provisioned accounts get real persisted users.
The running issuer does not connect to the database. Provisioning reruns add
missing accounts and preserve provider hashes, scopes, UUIDs and disablement.
Run one provisioning command at a time. For S3-backed legacy credentials, export
the users JSON privately first; this command accepts a local file.

Edit `accounts.json` at the provider boundary to change allowed scopes or
`is_active`; replace the file atomically and preserve UUIDs. Removing/disabling
an account blocks new login/refresh. A rejected refresh consumes that session.
Issued access tokens stay valid until expiry. Resource `/users`, `/me` and user
filter routes own domain profiles/attribution, not passwords or browser account
administration. Their `is_active` remains the domain/API-key access flag;
changing it does not disable a provider login account. Set provider account
policy separately. Referenced users cannot be deleted by resource routes.

Retained `jwks.json` can be copied privately into the issuer state directory
before its first start, preserving key IDs, issuer and audience. Without that
explicit copy, the issuer generates a new ES256 key and **forces re-login**.
Never copy private keys into API settings/storage for validation. Old access
tokens carrying `uid` remain valid to expiry when the original public key is
retained. Refresh sessions were already process-local: issuer restarts force
re-login for renewal regardless of retained signing keys. Old API issuer routes
are removed; reverse-proxy compatibility paths target the standalone issuer.

Refresh tokens rotate on every successful exchange. An atomic process lock
permits one winner for concurrent reuse. Four sessions per username are retained;
the logout API removes the current session. A browser sign-out control is deferred. These sessions are **single-process only**:
run one issuer worker/replica. Restart loses sessions, and multi-worker refresh
is unsupported. No general account platform, durable refresh database or SSO
protocol is introduced. The browser clears a failed session and opens login once;
failed login stays on the form, with no automatic credential fallback.

## Validation

Follow [Development](DEVELOPMENT.md) for isolated stores and separate processes.
`test_auth_service.py`, `test_bearer_auth_http.py` and `test_public_jwks.py` cover
provider policy/replay, forbidden database access, claim rejection, real HTTP
JWKS, rotation/cooldown/outages, alternate claim mapping and import boundaries.
The seed lifecycle test exercises separate issuer/resource apps and attributed
mutations through migrated PostgreSQL. `node
people-gator-app/scripts/check-auth-gateway.mjs` runs real-browser login,
keyboard, return navigation, refresh and expiry recovery at 1440×900 and
390×844. It expects the synthetic local instance at ports 5189/8089/8189 (or set
`AUTH_GATEWAY_ORIGIN`); credentials are entered only by that local test script.

The real-browser Swagger check is `node people-gator-app/scripts/check-swagger-session.mjs`.
It covers the gateway return/hash, existing app session reuse, authenticated
**Try it out**, refresh, recovery, API-key isolation and keyboard use at desktop
and mobile viewports. Set `SWAGGER_ORIGIN` for a same-origin preview.
