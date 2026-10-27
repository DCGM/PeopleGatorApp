# Backend pytest performance investigation (#81)

Measured on 2026-10-27 from `main` at `d9e7e8d` and the issue #81 branch.
Linux x86-64 (Ubuntu kernel 7.0.0-38), Intel i7-13700KF, CPython 3.14.3,
pytest 9.0.3, pytest-asyncio 1.4.0; parallel runs add pytest-xdist 3.8.0.
PostgreSQL 16.15/pgvector runs in a dedicated Docker container on localhost,
with separate disposable repository and schema databases and default durability
settings. No project database, external inference service or live Weaviate was used.
Dependency installation is excluded. These are local observations, not CI budgets;
the host also runs other services.

## Baseline and diagnosis

Commands ran from `people-gator-api`, with the locked environment. Full runs used
`--durations=30 --durations-min=0.1`; a representative test also ran under
`python -m cProfile -o /tmp/issue81-seed.prof -m pytest ... --durations=0`.

| Main baseline command | Result | pytest time | Wall time (`time -p`) |
| --- | --- | --- | --- |
| `uv run --locked pytest --collect-only -q` | 626 collected | 4.89 s | 6.76 s |
| `uv run --locked pytest -q --durations=30 --durations-min=0.1` without DB URLs | 470 passed, 156 skipped | 14.65 s | 16.36 s |
| Same full command with both disposable PostgreSQL URLs | 625 passed, 1 skipped | 466.74 s | 469.76 s |

The slowest 30 full-run entries were all preview-seed test **calls**, ranging
from 5.23 to 7.61 seconds. They exercise real repositories, seed/rerun/recovery,
media and schema behavior. A profiled representative,
`test_document_table_default_link_has_usable_rows_and_media`, measured **0.67 s
setup, 7.72 s call, 0.02 s teardown** (profiling adds overhead). Its profile showed
thousands of database operations and event-loop waits; image rendering was
about 0.46 s. Repeated migration setup contributes cost, but sharing migrations
alone would leave the dominant test-call work intact.

Keep function-scoped migration fixtures and real seed executions. Distribute
whole test cases across isolated workers instead of sharing transactions or
seeded records. A second, small fixture change restores dynamically attached ORM
index definitions after every test, extending the existing discovery-only guard
to prevent ordering-dependent bootstrap behavior.

## Worker-count comparison

Full comparison commands use the same container/URLs:

```sh
time uv run --locked pytest -q -n 2 --dist=worksteal --durations=0
time uv run --locked pytest -q -n 4 --dist=worksteal --durations=0
```

| Issue branch run | Result | pytest time | Wall time (`time -p`) |
| --- | --- | --- | --- |
| Two workers, work stealing | 632 passed, 1 skipped | 305.42 s | 307.57 s |
| Four workers, work stealing | 632 passed, 1 skipped | 167.61 s | 174.10 s |

The first four-worker run reduced wall time by **62.9% (2.70× faster)** versus
the sequential baseline. Two workers reduced wall time by 34.5%; use four for
CI. The approximate two-minute aim was not reached on this host; repeated real
seed/repository work and parallel overhead remain. No assertions or seed
executions were removed to reach these results.

Added tests protect distinct worker databases, independent committed writes and
DDL, metadata isolation, partial allocation failure and cleanup after worker/drop
failure. Final verification also covers nested settings overrides, schema-only
worker settings and rejection of parallel live Weaviate opt-ins.

## Isolation and limits

Each worker gets separate empty repository/schema databases before collection,
including fresh application persistence settings. Destructive extension and
migration tests cannot affect another worker's database. Function-scoped private
schemas, independent SQLAlchemy sessions, parameterized cases and actual SDK
storage/concurrency checks are retained. No production schema, migration, API,
seed or database semantics change; no preview scenario update is needed.

The controller cleans allocated databases on normal exit and worker failure.
Force-killing the controller still requires manual cleanup of that invocation's
`pytest_worker_<uuid>` databases. Live Weaviate remains sequential and skipped in
these measurements. Four workers need more CPU, memory and PostgreSQL connections;
use two on smaller hosts. Expensive seed/repository calls remain the main work.
See [runner commands and permissions](TEST.md#faster-backend-feedback).
