# Standalone OIDC issuer

`people-gator-auth` runs `people_gator_auth.app`, a separate application package.
It imports no resource API modules and never initializes the resource database,
media, embeddings or inference. The shared wheel/image contains both independent
entry points for compatibility with the reviewed deployment controller.
`people-gator-auth-provision` is an explicit resource-side setup CLI that maps
existing issuer/subject identities to persisted application UUIDs and publishes
accounts only after the database transaction commits. It is not issuer startup.

The issuer uses Authlib's authorization-code, PKCE and OpenID Connect extensions.
Only public clients using authorization code + mandatory S256 PKCE are supported.
Credential collection belongs to the issuer's HTML form, not the app or Swagger.
Password/implicit token grants and dynamic registration are not supported.

## Endpoints

- `/.well-known/openid-configuration`: standard discovery.
- `/.well-known/jwks.json`: public signing keys only.
- `/token/authorize`: authorization; issuer login or existing SSO cookie.
- `/token/login`: issuer form submission, protected by a one-time interaction and cookie.
- `/token/oidc`: standard form-encoded code/refresh grants, `client_id`, no client secret.
- `/token/revoke`: client-bound refresh-token revocation.
- `/token/logout`: RP-initiated logout with a signed ID-token hint and exact registered redirect.
- `/auth/health`: accounts, keys and writable issuer-state readiness.

Keeping issuer endpoints under `/token/` preserves the existing trusted reverse
proxy topology. The resource API does not serve any of these routes.

## Configuration and retained state

Settings use `PEOPLE_GATOR_AUTH__`. Configure `ISSUER`, resource `AUDIENCE`,
`STATE_DIR`, and optionally `CLIENTS`, a JSON array of registrations:

```json
[{"client_id":"people-gator-browser","redirect_uris":["https://app.example/auth-callback.html","https://app.example/docs"],"post_logout_redirect_uris":["https://app.example/login.html"]}]
```

With `CLIENTS` omitted, those exact callbacks are registered at the configured
issuer origin. Additional browser origins require explicit registrations.
Wildcards/fragments and insecure non-loopback redirects are rejected. Browser
CORS origins derive from registered callbacks plus explicit `ALLOW_ORIGINS`.

Preserve `accounts.json` (Argon2 hashes, permissions, persisted user UUIDs),
`jwks.json` (private signing keys) and `oidc.sqlite3` in the issuer state directory.
Never mount this directory in the resource API. Issuer-only SQLite transactions
cover complete code and refresh exchanges, preventing double redemption across
workers. Opaque codes, refresh tokens, interaction and session handles are
indexed by SHA-256 hashes; cookies are HttpOnly, SameSite=Lax, and Secure on HTTPS.
Signing keys and account files keep their retained format and identities.
Existing signed access tokens remain valid to expiry with the retained keys;
legacy browser refresh tokens are discarded and require a fresh OIDC login.

Codes expire after 60 seconds, interactions after 10 minutes, login sessions
after 8 hours and refresh tokens after 24 hours by default. Sessions and refresh
rotation survive restarts. Account disablement prevents new login/SSO/refresh.
Refresh-token replay revokes the active refresh family and issuer SSO session.
A rejected disabled-account refresh is revoked, including after reactivation.
Issued access tokens remain valid to expiry. Database files must be on a local
filesystem supporting SQLite locking; shared network storage and multi-host
issuer replicas are not supported by this implementation.
The previous four-session in-memory cap is replaced by expiration-managed durable
sessions; per-user device/session administration is outside this implementation.

The issuer grants this first-party application's registered resource audience
its account's assigned API permissions when no narrower API scopes are requested.
Explicit API scopes cannot exceed assigned permissions. ID tokens target the
browser client; access tokens target the resource audience. They carry different
`token_use` values, and the resource API rejects ID tokens.

This is a constrained first-party OIDC provider, not a certified general identity
platform. Registration, consent administration, password reset and MFA are out of
scope. Replace it through standard issuer/client configuration when needed.
