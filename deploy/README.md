# Deployment entry points

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
configuration's `repository` to `DCGM/PeopleGatorApp`. Install from a reviewed
`main` checkout, preserve existing state/configuration and run the installation
check required by the workflow. Application PRs supply candidate images; they
must not install controller code onto the trusted host.

Production-format Dockerfiles are in the two application directories. There is
no general-purpose production deployment stack or automatic release workflow.
Keep operator secrets and rendered Compose environments out of Git/public logs,
and verify backup/restore before migrations on retained data.
