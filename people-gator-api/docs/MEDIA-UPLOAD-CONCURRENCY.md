# Reproduce media upload connection starvation

[Issue #10](https://github.com/DCGM/PeopleGatorApp/issues/10) has a confirmed
PostgreSQL failure path on the affected revision: media uploads retain their
request's database connection after looking up the page, throughout the storage
wait. Fifteen pending uploads
consume the default connection pool in one API worker (five pooled connections
plus ten overflow connections). Independent searches, entity lists and uploads
then wait for a connection. The health endpoint remains responsive.

The fix scopes page image/layout GET and PUT database sessions to their page
lookup. The returned `PageResponse` contains the canonical media identity and
needs no live session.
Closing the context returns the connection before reading the multipart file,
preparing images, waiting for the existing page lock, or awaiting storage. The
request-scoped dependency used by other routes is unchanged. Authentication also
uses an explicit short context: its detached actor/user/key schemas need no
live session. This releases the user repository's transaction-scoped identity
lock before media I/O, so concurrent bearer requests for the same user can
authenticate independently. Context dependencies are uncached because each is
single-use and authentication and media lookups require separate instances.
No pool limits, storage timeouts, media receipts or per-page cache ordering are
changed.

## Verify the fix

From `people-gator-api`:

```sh
uv run --locked python scripts/reproduce_media_pool_starvation.py --expect-fixed
```

For both upload routes, all four probes must complete with 14 and 15 uploads
still held behind storage gates. The actual pool must report zero checked-out
connections once every held upload reaches storage. Successful uploads must
remain readable with matching receipt sizes and media types after release.
The final line is:

```text
FIXED: independent requests complete with 14 and 15 stalled uploads.
```

The original diagnostic mode below remains available for comparison with the
affected revision (`71c2908`). Running without `--expect-fixed` on fixed code
intentionally fails its assertions about the old connection-retention behavior.

The CI regression suite additionally exercises actual authentication and
user/API-key repositories, stubbing only credential verification. With the
disposable schema-test URL configured as in Development, run:

```sh
uv run --locked pytest tests/routes/test_page_upload_concurrency.py -q
```

The tests cover 14/15 gated uploads for both media types and authentication
methods, delayed S3 denial and actual SDK read timeout/retry, recovery on the
same page, readable results and receipts, and 15 readers plus 15 replacements
waiting behind one page image lock without retaining database connections.

## Run the minimal setup

Requirements: Docker with a running daemon, uv and Python 3.14, as described in
[Development](../../docs/DEVELOPMENT.md). From the repository root:

```sh
cd people-gator-api
uv sync --locked --python 3.14
uv run --locked python scripts/reproduce_media_pool_starvation.py
```

The script automatically creates a disposable `pgvector/pgvector:pg16` container
with a random localhost port, migrates it, and seeds the synthetic preview twice.
It starts one Uvicorn worker and a local HTTP endpoint implementing the S3
requests needed by this reproduction. The application's unmodified S3 adapter
and SDK send real HTTP requests to that endpoint. Authentication is overridden
with a synthetic actor; database dependencies, middleware and lifespan run
normally. Image processing uses small generated images.

No database URL, S3 account, private data, inference service or `.env` is needed.
Inherited application settings are ignored. The script removes its container and
temporary local storage on normal completion or a Python exception.

## Expected result on the affected revision

For **both** image and page-layout PUT endpoints, the script holds storage writes
on distinct pages until explicitly released, then checks four independent HTTP
requests: entity listing, seeded Ada text search, another upload and health.

| Held uploads | Requests completed before storage release | Requests waiting |
| --- | --- | --- |
| 14 | List, search, independent upload, health | None of the probes |
| 15 | Health | List, search, independent upload |

It prints four JSON records with the pool's actual checked-out connection count
and blocked requests. Each case has a one-second observation window after every
held upload has reached storage. All held uploads must remain pending during
that window. It releases storage and verifies every request completes with HTTP
200, list/search results contain records, and uploaded media is readable with
the expected receipt metadata. The final line is:

```text
REPRODUCED: 15 stalled uploads starve database requests; 14 do not.
```

**Exit 0 in the original mode confirms reproduction of the bug on the affected
revision.** It fails if the observations differ. Use `--expect-fixed` and the
regression suite above to require independent progress while storage gates
remain held.

## Boundaries

This confirms connection-pool starvation on PostgreSQL, rather than an event
loop freeze or a backend-wide storage mutex. Increasing the pool only changes
the saturation threshold. The existing per-page image lock separately makes a
read or replacement of the same page wait; this setup uses distinct pages.

The earlier single-upload investigation found that delayed success, S3 denial
and SDK timeout allow independent requests to progress. Denial and timeout
return HTTP 502 with `storage_error`, and subsequent reads/uploads succeed.
Those failure modes are not part of this minimal saturation script.

The original legacy environment, real provider permission policy, Weaviate and
multiple API workers have not been tested. The local S3 endpoint implements
only the operations needed here. The one-second window demonstrates blocked
requests; it does not wait for the database pool's acquisition timeout. This
endpoint is a controlled test double, not a full S3 provider validation.
