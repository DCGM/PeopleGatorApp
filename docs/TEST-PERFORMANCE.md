# Backend pytest performance

## CI runner speed-up (#156)

Measured on 2026-11-12 from the issue #156 branch (based on `main` at
`26db464`). CI: GitHub-hosted `ubuntu-24.04`, 4 vCPUs, 15 GB RAM, 7.9 GB
`/dev/shm`, CPython 3.14.10, PostgreSQL 18/pgvector service container.
Local: the #81 host below (24 threads, other services running), CPython
3.14.3 and the same PostgreSQL 18 image in a dedicated container on localhost.
Times are the pytest step only, from pytest's summary line.

### Where the time goes

All slowest 50 CI cases were preview-seed calls: **49–81 s each** on the
runner (the slowest was the alignment upgrade case), against 24–36 s locally
for the same four-worker run. Setup and teardown were under one second. The
101 preview-seed cases are 12% of the 871 cases and nearly all of the time,
so progress reached 75% in 1.4 minutes and then took 21 minutes for the rest.

Profiling one fresh seed case locally (`cProfile`, one seed run):

- PostgreSQL executed 14,346 statements in **0.4 s** of server time
  (`pg_stat_statements`), and a localhost round trip took 0.045 ms. Neither
  the database server nor the network is the bottleneck.
- `LocalFilesystem.write_bytes` fsyncs every file, and one seed writes about
  1,900 (mostly manifest checkpoints). On disk, the event loop spent 8.5 s
  waiting for those threads; with pytest's temporary directory on tmpfs it
  spent 2.1 s, and the case took **8.0 s instead of 13.8 s**.
- The remainder is Python CPU in repository code: SQLAlchemy statement
  construction and compilation, link-statistics queries, pydantic models and
  page-image rendering. A rerun costs about as much as a fresh seed (three
  seeds took 17 s profiled), and migrating a private schema per case takes
  0.2 s, so sharing migrations would not help.

On the runner that CPU work, PostgreSQL and the four workers share 4 vCPUs.
Six workers were no faster and two upload-concurrency tests timed out.

### Options compared

One CI run per configuration, all on the same commit and started together.
Hosted runners vary by about 15% between runs, so differences smaller than
that are not meaningful.

| Configuration (`-n 4 --dist=worksteal` unless noted) | CI pytest step | Local |
| --- | --- | --- |
| Baseline: collection order | 1332 s | 651 s |
| Seed cases first | 1283 s | — |
| Seed cases first + tmpfs `--basetemp` | 1486 s | 363 s |
| … + PostgreSQL `fsync`/`synchronous_commit`/`full_page_writes` off | 1178 s | 327 s |
| … with `-n 6` | 1238 s, 2 timeouts | — |
| … with `-n 8` | — | 218 s |
| … shard 1 of 3 (`--shard=1/3`) | 348 s | — |
| Seed cases spread, tmpfs, durability off, `--shard=I/4` | 274–360 s per shard (3 runs) | 372 s (no shard, durability on) |
| … + one fresh seed per worker, copied into eligible cases | 186–259 s per shard | 200 s (no shard) |
| … + one template per run, shards balanced by cost, `--shard=I/6` (final) | see below | 194 s (no shard) |

tmpfs and disabled durability help a lot locally but are within runner noise
on CI, where the work is CPU-bound. What shortens the CI critical path is
doing less seed work and splitting the rest across runners.

### Reusing the fresh seed

Most preview-seed cases begin by seeding an empty migrated store, the same
seconds of CPU every time. The first case of a run that needs it seeds once
into a template database and storage directory, under a file lock in the
run's shared temporary directory; the other workers reuse it. An eligible case
gets `CREATE DATABASE … TEMPLATE` (about 0.3 s locally) and a storage copy,
and its first `seed_preview` call returns the template's result. Every later
call in the case (reruns after edits, upgrades, checkpoint recovery) runs the
real seed, so those behaviors are still verified against real seed runs.

A case is eligible only when its body starts with the `seed_target` unpacking
followed directly by `await preview.seed_preview(database, filesystem)`, read
from its source, so nothing it does can precede the replaced call. That covers
74 of the module's 94 test functions. The 18 that prepare legacy state, patch
the seed or test recovery before seeding keep a real fresh seed automatically.
So do `test_seed_graph_vectors_filters_and_media_are_usable` and
`test_worker_seed_copy_matches_a_fresh_seed` (`@fresh_seed`); the latter
checks that a copy matches a real fresh seed: fixture keys, record counts,
all 299 other stored files, and a rerun that keeps every identity and adds nothing.
Copies also re-register the face models' index definitions on the ORM table,
as the replaced seed run would have done in the process.

Fresh-seed cases still cost two to three times as much as copied ones, so
shards split three tiers round robin (fresh seed, copied seed, fast) and each
tier is spaced evenly through the shard.

### Result

The `backend` job is a matrix: six pytest shards and a `tools` part (CLI
migration/seed smoke test, snapshot and deployment utility suites, utility
installation), all in parallel. Each shard has its own PostgreSQL service,
private worker databases and tmpfs `--basetemp`.

| CI run | Slowest shard (pytest) | `backend` job wall time |
| --- | --- | --- |
| Before: [43271445350](https://github.com/DCGM/PeopleGatorApp/actions/runs/43271445350) | 1332 s (one job) | 24 min 0 s |
| 4 shards, run 1: [43281628144](https://github.com/DCGM/PeopleGatorApp/actions/runs/43281628144) | 347 s (others 282–342 s) | 6 min 16 s |
| 4 shards, run 2: [43283091214](https://github.com/DCGM/PeopleGatorApp/actions/runs/43283091214) | 320 s (others 295–319 s) | 5 min 50 s |
| 4 shards, run 3: [43284470634](https://github.com/DCGM/PeopleGatorApp/actions/runs/43284470634) | 360 s (others 274–329 s) | 6 min 31 s |
| 4 shards + seed copies: [43292218225](https://github.com/DCGM/PeopleGatorApp/actions/runs/43292218225) | 259 s (others 186–226 s) | 4 min 50 s |
| Final, run 1: [43294289516](https://github.com/DCGM/PeopleGatorApp/actions/runs/43294289516) | 142 s (others 100–120 s) | 2 min 54 s |

The final job is about **8× faster** (24 min to under 3 min). Its shards ran
883 passed and 1 skipped: the original 870 + 1 skipped, the 12 scheduling
tests and the copy check. Per-case times of real seed runs are unchanged
(48–81 s on CI); there are fewer of them, and each runner has a sixth.
The tools part finishes in under two minutes.

Each tier is spaced evenly through its shard, so the progress counter tracks
elapsed time: final shard 1 reached 48% after 1.4 minutes and 97% after 2.2
of 2.4 minutes. Before, progress reached 75% in 1.4 of 22 minutes.

## Parallel workers (#81)

Measured on 2026-10-27 from `main` at `d9e7e8d` and the issue #81 branch.
Linux x86-64 (Ubuntu kernel 7.0.0-38), Intel i7-13700KF, CPython 3.14.3,
pytest 9.0.3, pytest-asyncio 1.4.0; parallel runs add pytest-xdist 3.8.0.
PostgreSQL 16.15/pgvector runs in a dedicated Docker container on localhost,
with separate disposable repository and schema databases and default durability
settings. No project database, external inference service or live Weaviate was used.
Dependency installation is excluded. These are local observations, not CI budgets;
the host also runs other services.

### Baseline and diagnosis

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

### Worker-count comparison

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

### Isolation and limits

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
