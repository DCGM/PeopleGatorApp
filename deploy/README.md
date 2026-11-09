# Deployment entry points

PR previews, staging from `main` and tagged releases are deploy jobs of the
single [CI workflow](../.github/workflows/ci.yml). Each job runs the
[`people-gator-deploy`](people-gator-deploy/README.md) utility from its own
checkout with settings kept in GitHub (repository variables and the `preview`,
`staging` and `production` environments); nothing is installed on the hosts
beyond the one-time setup.
PR previews use the automatic synthetic seed; staging retains its own
original-data database snapshot with storage managed externally; releases run
the tested tagged images against real, operator-provided data.

Use [Deployment](../docs/DEPLOYMENT.md) for workflow selection, image build/start
order, configuration and CI/CD. Use [Development](../docs/DEVELOPMENT.md) for local
Compose Watch or native API/Vite development.

| Files | Role |
| --- | --- |
| [`../compose.dev.yaml`](../compose.dev.yaml) | Local Traefik, PostgreSQL, API and frontend with reload |
| [`../compose.live-preview.yaml`](../compose.live-preview.yaml) | Existing shared development preview; external Traefik/S3 dependencies |
| [`../.github/workflows/ci.yml`](../.github/workflows/ci.yml) | Tests, images and the preview/staging/release deploy jobs |
| [`../.github/actions/deploy-tools`](../.github/actions/deploy-tools/action.yml) | Installs the utility into the job's temporary directory |
| [`GITHUB-SETUP.md`](GITHUB-SETUP.md) | Step-by-step: repository variables, environments, secrets, policies and runners |
| [`infrastructure/`](infrastructure/compose.yaml) | Operator-run shared PostgreSQL and pgAdmin for previews and staging; the deploy jobs only check it |
| [`runner/job-started.sh`](runner/job-started.sh) | Self-hosted runner hook admitting only this repository's events for the runner's environment |
| [`people-gator-deploy/`](people-gator-deploy/README.md) | Package, CLI, lifecycle operations, `DEPLOY_*` settings and recovery |
| [`people-gator-deploy/HOSTS.md`](people-gator-deploy/HOSTS.md) | DNS, proxy, runners, GitHub Environments, buckets and accounts to prepare |
| [`people-gator-deploy/examples/`](people-gator-deploy/examples/) | Shape of the staging backup-source secret |
| [`people-gator-deploy/src/people_gator_deploy/assets/`](people-gator-deploy/src/people_gator_deploy/assets/) | Frontend + backend Compose stacks for PR previews, staging and production releases |
| [`backup/README.md`](backup/README.md) | Independent PostgreSQL backup publisher, restore loader and opt-in scheduled worker |

A pull request deploys its preview with the deploy code of its own branch, so a
broken deploy change only breaks that PR's preview; staging always uses `main`
and releases use the tagged commit. Fork pull requests are only tested.
The shared infrastructure is started and upgraded by an operator with plain
Docker Compose; the utility checks it and never installs anything.
Keep secrets in the GitHub Environments and host state directories, never in
Git or public logs, and verify backup/restore before migrations on retained
data.
