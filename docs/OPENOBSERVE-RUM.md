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

Each environment's settings ([GitHub setup](../deploy/GITHUB-SETUP.md)) carry
two optional groups, prefixed `PREVIEW_`, `STAGING_` or `PRODUCTION_`:

| Name | Kind | Meaning |
| --- | --- | --- |
| `OTEL_ENDPOINT` | variable | OTLP HTTP base URL on the `logging` network, for example `http://lgtm:4318`; the deployment derives the `/v1/traces`, `/v1/logs` and `/v1/metrics` endpoints and enables the SDK |
| `OTEL_HEADERS` | secret | Becomes `OTEL_EXPORTER_OTLP_HEADERS`, for example `Authorization=Basic …` |
| `RUM_CLIENT_TOKEN` | secret | The dedicated browser RUM token; enables RUM |
| `RUM_SITE` | variable | RUM site, default `openobserve.capturemyhand.com` |

The deploy job renders them into a private `telemetry.env` that only the API
runtime container reads (not frontend, migration, seed, check or database
snapshot workers). Leave a group unset to keep that feature off. Do not print the
rendered file or Compose configuration into CI logs.

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
`logging` network and a **traces** pipeline forwarding to OpenObserve. Every
stack points the backend at `OTEL_ENDPOINT` for logs, traces and metrics; there
is no separate container-log collector. Enable or adjust trace forwarding through an explicit
operator change.

The backend SDK exports traces, metrics and structured application logs directly
to `http://lgtm:4318` when OTEL is enabled in every deployment mode. The locked
logging instrumentor installs and preserves the root OTLP handler, including
trace/span correlation and exception attributes. Container stdout/stderr collection
is separate; see [backend versus container logs](OBSERVABILITY.md#direct-backend-otlp-traces-metrics-and-logs)
for duplicate copies and the release diagnostic-log path. The collector must
accept all configured signals. If server-side authorization is required,
put the standard `OTEL_EXPORTER_OTLP_HEADERS` value in the `OTEL_HEADERS` secret. Endpoint settings contain complete URLs, passed unchanged to the
exporters:

| API setting | Standard environment alias | Default |
| --- | --- | --- |
| `PEOPLE_GATOR_API__OTEL__TRACES_ENDPOINT` | `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` | `http://lgtm:4318/v1/traces` |
| `PEOPLE_GATOR_API__OTEL__LOGS_ENDPOINT` | `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT` | `http://lgtm:4318/v1/logs` |
| `PEOPLE_GATOR_API__OTEL__METRICS_ENDPOINT` | `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` | `http://lgtm:4318/v1/metrics` |

Settings resolve the aliases; exporters do not read or combine endpoint parts.
The API setting takes priority when both environment names are supplied. The
former `HTTP_ENDPOINT` plus signal paths, unused gRPC/profile settings and generic
backend base-URL expansion are removed. The deployment derives the three URLs
from `OTEL_ENDPOINT`. Prefer the existing LGTM collector for routing and
OpenObserve credentials.
Never use the browser RUM token as OTLP credentials.

## Rollout and verification

1. Review and merge the implementation. A PR preview deploys with its own
   branch's deploy code, so the complete path can be verified on the PR before
   merge; staging and releases pick it up from `main` and the tag.
2. Add the `OTEL_*` and `RUM_*` settings for each environment as described
   above. Keep the shared infrastructure unchanged.
3. Deploy a new eligible PR/main build or release through the normal lifecycle.
   Ensure backend startup and routed readiness succeed. No database migration,
   new seed records or frontend rebuild for credentials is needed.
4. In browser DevTools, confirm `/api/v1/rum-config` has the right environment and
   version, then API requests have `traceparent` and RUM ingestion succeeds.
   Do not share unredacted response bodies, HAR files or collector headers.
5. Navigate synthetic Documents and search for **Ada Novak** in a PR preview.
   In OpenObserve RUM, filter service/environment/version and inspect its API
   resources. With both sampling rates at 100, open the seed manifest's
   `openobserve-replay-person` (Ada Novak), then `openobserve-replay-page`
   (her linked synthetic face page). Inspect the session's replay for navigation
   and interactions with content masked. Repeat in another new browser session
   to confirm full sampling, and verify rate 0 disables replay for a new session.
   Find the matching `trace_id` in backend traces and confirm the
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
