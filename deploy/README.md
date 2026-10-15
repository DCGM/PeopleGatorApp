# Deployment entry points

For automatic main deployments and explicit production-snapshot initialization,
see [Staging](preview/STAGING.md). Staging retains its own database, credentials and media;
PR previews continue to use the automatic synthetic seed.

Use [Deployment](../docs/DEPLOYMENT.md) for workflow selection, image build/start
order, configuration and CI/CD. Use [Development](../docs/DEVELOPMENT.md) for local
Compose Watch or native API/Vite development.

| Files | Role |
| --- | --- |
| [`../compose.dev.yaml`](../compose.dev.yaml) | Local Traefik, PostgreSQL, API and frontend with reload |
| [`../compose.live-preview.yaml`](../compose.live-preview.yaml) | Existing shared development preview; external Traefik/S3 dependencies |
| [`preview/compose.infrastructure.yaml`](preview/compose.infrastructure.yaml) | Shared preview PostgreSQL, collector and pgAdmin |
| [`preview/compose.pr.yaml`](preview/compose.pr.yaml) | Per-PR images, migration/seed tools and storage |
| [`preview/release.py`](preview/release.py) | Validates and atomically publishes reviewed `main` bundles without recurring sudo |
| [`preview/preview.py`](preview/preview.py) | Trusted lifecycle controller executed from a versioned runner-owned release |
| [`preview/README.md`](preview/README.md) | Host installation, credentials, upgrades, recovery and checks |

Before installing previews, read the host guide fully and set the example
configuration's `repository` to `DCGM/PeopleGatorApp`. Provision private runner-owned
release/state directories and separate operator settings once. Lifecycle jobs
automatically validate and publish their exact reviewed `main` controller bundle
without sudo, preserving existing configuration and data. Application PRs supply
candidate images and must not supply the host controller. Shared-infrastructure
initialization/upgrades remain explicit operator actions.

Production-format Dockerfiles are in the two application directories. There is
no general-purpose production deployment stack or automatic release workflow.
Keep operator secrets and rendered Compose environments out of Git/public logs,
and verify backup/restore before migrations on retained data.
