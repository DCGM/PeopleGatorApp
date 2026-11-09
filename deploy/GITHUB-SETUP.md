# GitHub setup for the deploy pipeline

Step-by-step configuration of the repository so the [CI workflow](../.github/workflows/ci.yml)
can deploy previews, staging and releases. The deploy jobs read every setting
from GitHub; the meaning and defaults of each name are in the
[configuration reference](people-gator-deploy/README.md#configuration), and the
hosts, runners and shared stack are prepared in [HOSTS.md](people-gator-deploy/HOSTS.md).
Each step shows the `gh` command and the Settings page; run the commands from a
checkout with `gh auth login` done and admin rights on the repository.

## 1. Repository variables for the preview host

The preview cleanup jobs have no GitHub Environment, so the preview host's
non-secret settings are **repository** variables (Settings → Secrets and
variables → Actions → Variables → New repository variable):

```sh
gh variable set PREVIEW_DOCKER_CONTEXT --body rootless
gh variable set PREVIEW_DOMAIN --body preview.peoplegator.dev
# Only when the host differs from the defaults:
# gh variable set PREVIEW_POSTGRES_CONTAINER --body people-gator-preview-infra-postgres-1
# gh variable set PREVIEW_OTEL_HTTP_ENDPOINT --body http://lgtm:4318
# gh variable set PREVIEW_STATE_DIR --body /srv/people-gator/state/pr
```

Optional names: `PREVIEW_STATE_DIR`, `PREVIEW_POSTGRES_CONTAINER`,
`PREVIEW_POSTGRES_ADMIN_USER`, `PREVIEW_DATABASE_NETWORK`, `PREVIEW_WEB_NETWORK`,
`PREVIEW_CERTIFICATE_RESOLVER`, `PREVIEW_OTEL_NETWORK`, `PREVIEW_OTEL_HTTP_ENDPOINT`,
`PREVIEW_OTEL_ENABLED`.

## 2. The `preview` environment (secrets only)

Settings → Environments → New environment `preview`. Leave the deployment
branch policy open (previews run for pull requests). Add the secrets:

```sh
gh secret set PREVIEW_USERS_JSON --env preview < /private/preview-users.json
gh secret set PREVIEW_TELEMETRY_ENV --env preview < /private/preview-telemetry.env   # optional: RUM settings, OTLP headers
```

`PREVIEW_TELEMETRY_ENV` must not contain `PEOPLE_GATOR_API__OTEL__ENABLED` or
`OTEL_EXPORTER_OTLP_*_ENDPOINT` lines; the deployment sets those.

## 3. The `staging` environment

Settings → Environments → New environment `staging` → Deployment branches and
tags → **Selected branches and tags** → add `main`.

```sh
gh variable set DEPLOY_DOCKER_CONTEXT --env staging --body rootless
gh variable set DEPLOY_HOST --env staging --body staging.peoplegator.dev
gh secret set DEPLOY_RUNTIME_ENV --env staging < /private/staging-runtime.env
gh secret set DEPLOY_SNAPSHOT_SOURCE --env staging < /private/staging-backup-source.json
gh secret set DEPLOY_TELEMETRY_ENV --env staging < /private/staging-telemetry.env    # optional
```

Optional variables: `DEPLOY_PROJECT`, `DEPLOY_STATE_DIR`, `DEPLOY_POSTGRES_CONTAINER`,
`DEPLOY_POSTGRES_ADMIN_USER`, `DEPLOY_DATABASE_NETWORK`, `DEPLOY_WEB_NETWORK`,
`DEPLOY_CERTIFICATE_RESOLVER`, `DEPLOY_OTEL_NETWORK`, `DEPLOY_OTEL_HTTP_ENDPOINT`,
`DEPLOY_OTEL_ENABLED`. Staging shares the preview host's PostgreSQL, so its
container, admin user and database network must equal the `PREVIEW_*` values.

## 4. The `production` environment

Settings → Environments → New environment `production` → Deployment branches
and tags → **Selected branches and tags** → add tag pattern `v*`. Optionally add
**Required reviewers** for a manual gate before every release job.

```sh
gh variable set DEPLOY_DOCKER_CONTEXT --env production --body rootless
gh variable set DEPLOY_HOST --env production --body people.example.org
gh variable set DEPLOY_DATABASE_NETWORK --env production --body people-gator-production-db
gh variable set DEPLOY_ACCESS_REVIEWED --env production --body true   # after reviewing the access boundary
gh secret set DEPLOY_RUNTIME_ENV --env production < /private/release-runtime.env
gh secret set DEPLOY_MIGRATION_ENV --env production < /private/release-migration.env
gh secret set DEPLOY_TELEMETRY_ENV --env production < /private/release-telemetry.env   # optional
```

Optional variables: `DEPLOY_PROJECT`, `DEPLOY_STATE_DIR`, `DEPLOY_WEB_NETWORK`,
`DEPLOY_CERTIFICATE_RESOLVER`, `DEPLOY_OTEL_NETWORK`, `DEPLOY_BACKEND_MEMORY`.

## 5. Actions settings and runners

- Settings → Actions → General → Fork pull request workflows: require approval
  for all outside collaborators. Workflow permissions can stay read-only; the
  jobs request `packages: write` and `deployments: write` themselves.
- Settings → Rules: protect `v*` tags so only maintainers create them.
- Register the self-hosted runners with labels `people-gator-preview`,
  `people-gator-staging` and `people-gator-release`, install the
  [job-started guard](runner/job-started.sh) with `PEOPLE_GATOR_RUNNER_ENVIRONMENT`
  listing the environments each runner serves, and start the shared stack on
  the preview/staging host ([HOSTS.md](people-gator-deploy/HOSTS.md),
  [one-time host setup](people-gator-deploy/README.md#one-time-host-setup)).
- For private GHCR packages, grant the repository's Actions access to
  `peoplegatorapp-frontend` and `peoplegatorapp-backend`.

## 6. Check

```sh
gh variable list
gh variable list --env staging && gh variable list --env production
gh secret list --env preview && gh secret list --env staging && gh secret list --env production
gh api repos/{owner}/{repo}/environments --jq '.environments[].name'
```

Then run the workflow once by hand on `main` (Actions → CI → Run workflow,
`operation=update`, or `snapshot-init` for a fresh staging database) and open a
pull request: `deploy-staging` and `deploy-preview` print the resolved settings
in their `preflight` step and fail with the missing variable's name if anything
is absent. Each successful deploy appears under the repository's Deployments.
