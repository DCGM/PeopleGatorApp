"""GitHub Deployments hygiene: only the current deployment of each environment stays active.

Every deploy job declares a GitHub Environment, so GitHub records a Deployment
with the environment URL. After a successful deploy, older deployments of the
same environment (and, for previews, the same PR head branch) are set
``inactive``; closed PRs' previews are retired. History is never deleted.
"""
from __future__ import annotations

import os
import re

from .core import DeployError
from .host import github_api

ENVIRONMENTS = ("preview", "staging", "production")
REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,254}")


class Deployments:
    def __init__(self, repository: str | None = None):
        self.repository = repository or os.environ.get("GITHUB_REPOSITORY", "")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", self.repository):
            raise DeployError("Deployment hygiene requires GITHUB_REPOSITORY (owner/name)")

    def api(self, endpoint, *, method="GET", data=None):
        return github_api(self.repository, endpoint, method=method, data=data)

    def paginated(self, endpoint):
        page = 1
        while True:
            items = self.api(f"{endpoint}&per_page=100&page={page}")
            if not isinstance(items, list):
                raise DeployError("GitHub returned an unexpected deployment listing")
            yield from items
            if len(items) < 100:
                return
            page += 1

    def listing(self, environment, ref=None):
        """Deployments of one environment, newest first, as (id, ref) pairs."""
        if environment not in ENVIRONMENTS:
            raise DeployError(f"Unknown deployment environment {environment!r}")
        query = f"deployments?environment={environment}"
        if ref:
            if not REF.fullmatch(ref):
                raise DeployError("Invalid deployment ref")
            query += f"&ref={ref}"
        return [(int(item["id"]), str(item["ref"])) for item in self.paginated(query)]

    def state(self, deployment):
        statuses = self.api(f"deployments/{int(deployment)}/statuses?per_page=1")
        return statuses[0].get("state", "") if statuses else ""

    def deactivate(self, deployment, environment, ref):
        if self.state(deployment) == "inactive":
            return False
        print(f"Setting deployment {deployment} inactive ({environment}, {ref})", flush=True)
        self.api(f"deployments/{int(deployment)}/statuses", method="POST", data={"state": "inactive"})
        return True

    def supersede(self, environment, ref=None):
        """Keep the newest deployment (the current one); set every older one inactive."""
        deactivated = []
        for deployment, deployed_ref in self.listing(environment, ref)[1:]:
            if self.deactivate(deployment, environment, deployed_ref):
                deactivated.append(deployment)
        return deactivated

    def retire(self, ref):
        """A closed PR has no current preview: set all its deployments inactive."""
        return [deployment for deployment, deployed_ref in self.listing("preview", ref)
                if self.deactivate(deployment, "preview", deployed_ref)]

    def open_refs(self):
        """Head branches of open same-repository pull requests."""
        refs = set()
        for pull in self.paginated("pulls?state=open"):
            head = pull.get("head") or {}
            if (head.get("repo") or {}).get("full_name", "").lower() == self.repository.lower() and head.get("ref"):
                refs.add(head["ref"])
        return refs

    def prune(self):
        """Safety net: one active deployment per environment, one per open PR branch for previews."""
        deactivated = {"staging": self.supersede("staging"), "production": self.supersede("production"), "preview": []}
        open_refs = self.open_refs()
        kept = set()
        for deployment, ref in self.listing("preview"):
            if ref in open_refs and ref not in kept:
                kept.add(ref)
                continue
            if self.deactivate(deployment, "preview", ref):
                deactivated["preview"].append(deployment)
        return deactivated

    def execute(self, action, *, environment=None, ref=None):
        if action == "supersede":
            return {"environment": environment, "inactive": self.supersede(environment, ref)}
        if action == "retire":
            return {"environment": "preview", "ref": ref, "inactive": self.retire(ref)}
        if action == "prune":
            return {"inactive": self.prune()}
        raise DeployError(f"Unsupported deployments action: {action}")
