# Deployment entry points

PR previews, staging from `main` and tagged releases are operated by one
installable utility, [`people-gator-deploy`](people-gator-deploy/README.md):
install it once per deployment account, configure each environment's single
descriptor once, and let the short workflows invoke it. PR previews use the
automatic synthetic seed; staging retains its own original-data snapshot,
credentials and media; releases run the tested tagged images against real,
operator-provided data.

Use [Deployment](../docs/DEPLOYMENT.md) for workflow selection, image build/start
order, configuration and CI/CD. Use [Development](../docs/DEVELOPMENT.md) for local
Compose Watch or native API/Vite development.

| Files | Role |
| --- | --- |
| [`../compose.dev.yaml`](../compose.dev.yaml) | Local Traefik, PostgreSQL, API and frontend with reload |
| [`../compose.live-preview.yaml`](../compose.live-preview.yaml) | Existing shared development preview; external Traefik/S3 dependencies |
| [`install.py`](install.py) | Canonical installer for user or system scope, CI bootstrap and upgrades |
| [`people-gator-deploy/`](people-gator-deploy/README.md) | Package, CLI, lifecycle operations, descriptors and recovery |
| [`people-gator-deploy/HOSTS.md`](people-gator-deploy/HOSTS.md) | DNS, proxy, runners, tokens, buckets and accounts to prepare |
| [`people-gator-deploy/examples/`](people-gator-deploy/examples/) | Placeholder descriptors for `pr`, `staging` and `release` |
| [`people-gator-deploy/src/people_gator_deploy/assets/`](people-gator-deploy/src/people_gator_deploy/assets/) | Packaged infrastructure, PR, staging and production release Compose stacks |
| [`backup/README.md`](backup/README.md) | Independent PostgreSQL backup publisher, restore loader and opt-in scheduled worker |

Application PRs supply candidate images and never supply host tooling, installer
code or Compose templates. Shared-infrastructure initialization/upgrades remain
explicit operator actions. Keep descriptors, secrets and rendered Compose
environments out of Git/public logs, and verify backup/restore before migrations
on retained data.
