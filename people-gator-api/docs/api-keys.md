# API-key authentication

Protected routes accept either `Authorization: Bearer <JWT>` or `X-API-Key: <key>`.
Both headers return 400; missing or invalid credentials return 401; insufficient
endpoint scopes return 403. Login and refresh continue to issue JWTs. Swagger's
Authorize dialog offers both methods; supply one at a time.

Set `PEOPLE_GATOR_API__API_KEYS__KEYS_PATH` to a JSON object in the configured
filesystem (default `peoplegator_api/api-keys.json`):

```json
{
  "archive-importer": {
    "display_name": "Archive importer",
    "username": "archive-service",
    "hash": "<Argon2 hash of the API key>",
    "scopes": ["people-gator:browse", "people-gator:ingest"]
  }
}
```

Generate a high-entropy secret and hash it with `argon2.PasswordHasher().hash`.
Store the secret in the integration client's secret store. Object keys are stable
identifiers; never reuse an identifier for a different identity. The username is
a service account under the configured JWT issuer, so matching JWT and API-key
users share the same database identity. Allowed scopes are browse, annotate,
ingest and admin, each prefixed with `people-gator:`.

The file is validated on every API-key request. Remove an entry to revoke a key
on its next use; `{}` revokes all keys. Missing, malformed or unreadable files are
configuration errors. Registration follows credential and scope verification;
a database unique constraint preserves the same ID under concurrent requests.
Display-name changes preserve that identity. Secrets and hashes are never stored
in the registry or returned by the API.

`GET /api/v1/api-keys` lists registered IDs, identifiers, display names and account
IDs, including revoked keys for historical filtering. It requires browse access
and supports cursor pagination. `GET /api/v1/user-filter-options` provides user
IDs and names without granting access to user administration.

Run `uv run alembic upgrade head` before starting in schema validation mode. The
migration extends the complete-schema revision `c82e7f4a901d`.
