# OpenObserve RUM and API traces

PeopleGator uses OpenObserve browser SDKs 0.4.3 with deployment-time configuration.
The configured destination is OpenObserve v1.1.2 at
`https://openobserve.capturemyhand.com`, organization `default`. Actual ingestion
and trace forwarding must be verified on the deployed instance; local checks do
not establish live OpenObserve compatibility or collector configuration.

## Credentials and runtime configuration

Use the dedicated **RUM client token** from OpenObserve's **Ingestion → RUM**
page. One token can serve all PeopleGator PR previews, staging and releases.
This token is browser-visible by design. Account passwords and server OTLP
exporter authorization never belong in browser settings, Git, image build args
or frontend `VITE_*` variables.

Create an operator-owned mode-600 file outside the checkout, utility installation
and deployment state directories, for example `/home/RUNNER/private/people-gator-telemetry.env`:

```dotenv
PEOPLE_GATOR_API__RUM__ENABLED=true
PEOPLE_GATOR_API__RUM__CLIENT_TOKEN=REPLACE_WITH_DEDICATED_RUM_TOKEN
PEOPLE_GATOR_API__RUM__SITE=openobserve.capturemyhand.com
PEOPLE_GATOR_API__RUM__ORGANIZATION_IDENTIFIER=default
PEOPLE_GATOR_API__RUM__APPLICATION_ID=people-gator-app
PEOPLE_GATOR_API__RUM__SESSION_SAMPLE_RATE=100
PEOPLE_GATOR_API__OTEL__ENABLED=true
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://lgtm:4318/v1/traces
OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=http://lgtm:4318/v1/logs
OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=http://lgtm:4318/v1/metrics
```

Use literal, unquoted `KEY=value` entries. The deployment telemetry file uses
Compose's raw env-file format, so dollar signs are not expanded and quotes would
become part of the value. Only API RUM, API OTEL and `OTEL_EXPORTER_OTLP*` keys are
allowed; deployment identity and application/storage/auth settings cannot be
supplied through this file. Do not print its contents or rendered Compose
configuration into CI logs. Replace `lgtm` with the actual reachable collector
hostname if different.

For **each** environment descriptor (`pr`, `staging`, `release`), merge:

```json
{
  "telemetry_file": "/home/RUNNER/private/people-gator-telemetry.env",
  "otel_network": "logging"
}
```

Use that host's absolute file path and collector's Docker network. The same file
can be referenced by multiple environments on one host; other hosts need their
own operator-managed copy. Existing staging/release `runtime_file` settings are
retained. Telemetry-file values override matching runtime-file values. Only the
API runtime container receives this extra file, not frontend, migration, seed,
check or database snapshot workers. Without `telemetry_file`, telemetry remains
disabled by default (existing staging/release runtime settings can still enable
it). The extra backend network defaults to the web network when `otel_network`
is absent.

The API serves an explicit allowlist of public RUM settings at
`GET /api/v1/rum-config`, with `Cache-Control: no-store`. It is unauthenticated
because monitoring starts before login; it exposes no backend OTLP credentials.
It is an operational endpoint excluded from application OpenAPI/client generation,
owned by `routes/v1/rum_config.py` and registered through the v1 router.
The frontend reads it before loading router/client modules. Disabled settings,
older-backend 404s and failed requests leave the app usable; configuration fetch
has a three-second timeout. A missing token with RUM enabled is a server
configuration error and fails settings validation.

The frontend uses HTTPS ingestion, masks captured page content, records no
session replays and does not identify users. Browser errors are forwarded to
OpenObserve logs; console messages are not forwarded automatically. API paths,
error messages and interaction metadata can still contain application information.

## Deployment identity

| Deployment | `env` | `version` | Global browser context |
| --- | --- | --- | --- |
| PR preview | `preview` | Commit SHA | `commit`, `pr_number` |
| Staging | `staging` | Commit SHA | `commit` |
| Tagged release | `release` | Release tag | `commit` |

Frontend service is `people-gator-app`; backend service is `people-gator-api`.
Backend resource attributes include `deployment.environment.name`,
`service.version`, `vcs.ref.head.revision` and the preview PR number. Compose
supplies identity independently of the private file, keeping one shared token
and backend/frontend versions consistent. Application restarts/redeployments
apply token rotation; already open browser tabs retain their previous token
until reloaded. Stale/repeated deployment events remain subject to existing
lifecycle idempotency rules; editing a file alone does not recreate containers.

## Trace path and collector prerequisites

```text
Browser ── RUM events/error logs ──HTTPS──► OpenObserve
   │
   └── API/login requests + traceparent ──► FastAPI
                                               │
                                               └── OTLP HTTP ──► existing LGTM collector ──► OpenObserve
```

The SDK injects W3C trace context into requests matching the exact configured API
origin and `/api/` or `/token/` path boundaries, including an API base-path prefix.
It does not inject tracing headers into assets or other origins. FastAPI
instrumentation continues the supplied trace; its parent-based sampling respects
the caller's sampled flag. The API already permits tracing headers through its
CORS middleware; separately hosted frontends need their origin in the API CORS
settings. OpenObserve must allow browser ingestion from PR, staging and release
origins; ensure any proxy/CSP permits HTTPS connections to its host.

The existing LGTM collector must have an OTLP HTTP receiver reachable from the
backend's `otel_network` and a **traces** pipeline forwarding to OpenObserve.
Working container logs alone do not establish this. The deployment utility's
bundled Fluent Forward collector only handles container logs; this change does
not modify that shared infrastructure or substitute it for the LGTM receiver.
Enable or adjust trace forwarding through an explicit operator change.

The backend SDK exports traces, metrics and structured application logs directly
to `http://lgtm:4318` when OTEL is enabled in every deployment mode. The locked
logging instrumentor installs and preserves the root OTLP handler, including
trace/span correlation and exception attributes. Container stdout/stderr collection
is separate; see [backend versus container logs](OBSERVABILITY.md#direct-backend-otlp-traces-metrics-and-logs)
for duplicate copies and the release diagnostic-log path. The collector must
accept all configured signals. If server-side authorization is required,
put standard `OTEL_EXPORTER_OTLP_HEADERS` or per-signal headers in the private
telemetry file. Endpoint settings contain complete URLs, passed unchanged to the
exporters:

| API setting | Standard environment alias | Default |
| --- | --- | --- |
| `PEOPLE_GATOR_API__OTEL__TRACES_ENDPOINT` | `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` | `http://lgtm:4318/v1/traces` |
| `PEOPLE_GATOR_API__OTEL__LOGS_ENDPOINT` | `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT` | `http://lgtm:4318/v1/logs` |
| `PEOPLE_GATOR_API__OTEL__METRICS_ENDPOINT` | `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` | `http://lgtm:4318/v1/metrics` |

Settings resolve the aliases; exporters do not read or combine endpoint parts.
The API setting takes priority when both environment names are supplied. The
former `HTTP_ENDPOINT` plus signal paths, unused gRPC/profile settings and generic
backend base-URL expansion are removed. Migrate existing backend telemetry files
to the complete per-signal URLs above. The deployment utility's separate
container-log collector retains its own standard OTLP base configuration.
Prefer the existing LGTM collector for routing and OpenObserve credentials.
Never use the browser RUM token as OTLP credentials.

## Rollout and verification

1. Review and merge the implementation. Lifecycle workflows install their exact
   reviewed `main` utility revision; PR code must not become host-controller code.
   A preview using the older trusted controller will not consume `telemetry_file`
   or apply the new identity/network settings. Use a fresh eligible build after
   reviewed-main rollout to verify the complete deployment path.
2. Create the private file, merge the descriptor fields with
   `people-gator-deploy <environment> configure --input <private-json>` and run
   the environment's `preflight`. Keep the shared infrastructure unchanged.
3. Deploy a new eligible PR/main build or release through the normal lifecycle.
   Ensure backend startup and routed readiness succeed. No database migration,
   new seed records or frontend rebuild for credentials is needed.
4. In browser DevTools, confirm `/api/v1/rum-config` has the right environment and
   version, then API requests have `traceparent` and RUM ingestion succeeds.
   Do not share unredacted response bodies, HAR files or collector headers.
5. Navigate synthetic Documents and search for **Ada Novak** in a PR preview.
   In OpenObserve RUM, filter service/environment/version and inspect its API
   resources. Find the matching `trace_id` in backend traces and confirm the
   server span continues the browser parent span. Check a second PR to verify
   PR-number separation, then staging and a tagged release for their metadata.
6. Check failed telemetry does not prevent application navigation. To disable,
   set RUM enabled to false and recreate the API runtime through the reviewed
   lifecycle; disable backend OTEL separately if desired.

Local tests cover public-config isolation, real FastAPI parent continuation,
SDK configuration/URL boundaries, and rendered Compose settings for all three
environments. A local OTLP HTTP sink also verifies actual backend protobuf
trace/log/metric export, correlated info/error logs and collector authorization
for preview, staging and release identities. Live delivery, browser ingestion CORS and the external LGTM trace
pipeline require the operator checks above.
