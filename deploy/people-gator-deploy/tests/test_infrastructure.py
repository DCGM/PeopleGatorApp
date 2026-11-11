"""The operator-run shared stack (deploy/infrastructure) keeps the contract the deploy utility checks."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest

import yaml

INFRASTRUCTURE = Path(__file__).resolve().parents[2] / "infrastructure"
SAMPLE = {"POSTGRES_ADMIN_PASSWORD": "synthetic-admin", "PGADMIN_DEFAULT_PASSWORD": "synthetic-pgadmin",
          "PGADMIN_DEFAULT_EMAIL": "operator@example.test", "PGADMIN_HOST": "pgadmin.example.test"}


class InfrastructureStackTests(unittest.TestCase):
    def test_example_env_lists_every_variable_the_stack_interpolates(self):
        compose = (INFRASTRUCTURE / "compose.yaml").read_text()
        interpolated = {name for name in __import__("re").findall(r"\$\{([A-Z_]+)", compose)}
        example = {line.split("=", 1)[0] for line in (INFRASTRUCTURE / "example.env").read_text().splitlines()
                   if line and not line.startswith("#")}
        self.assertEqual(interpolated, example)
        document = yaml.safe_load(compose)
        self.assertEqual(document["name"], "people-gator-preview-infra")  # existing volumes keep matching
        self.assertEqual(document["services"]["postgres"]["container_name"], "people-gator-postgres")
        self.assertEqual(document["networks"]["database"]["name"], "db")
        self.assertEqual(document["services"]["postgres"]["networks"]["database"]["aliases"], ["preview-postgres"])
        self.assertNotIn("otel-collector", compose)  # the backend exports telemetry itself
        self.assertEqual(json.loads((INFRASTRUCTURE / "pgadmin-servers.json").read_text())["Servers"]["1"]["Host"], "preview-postgres")

    @unittest.skipUnless(shutil.which("docker"), "Docker Compose not installed")
    def test_stack_routes_pgadmin_and_keeps_database_private(self):
        environment = {key: os.environ[key] for key in ("PATH", "HOME") if key in os.environ}
        result = subprocess.run(["docker", "compose", "-f", str(INFRASTRUCTURE / "compose.yaml"), "config", "--format", "json"],
                                env={**environment, **SAMPLE}, text=True, capture_output=True, check=True)
        config = json.loads(result.stdout)
        postgres = config["services"]["postgres"]
        self.assertFalse(postgres.get("ports"))
        self.assertNotIn("web", postgres["networks"])
        self.assertEqual(postgres["container_name"], "people-gator-postgres")
        self.assertEqual(postgres["networks"]["database"]["aliases"], ["preview-postgres"])
        pgadmin = config["services"]["pgadmin"]
        self.assertFalse(pgadmin.get("ports"))
        self.assertEqual(set(pgadmin["networks"]), {"database", "web"})
        self.assertEqual(pgadmin["labels"]["traefik.http.routers.pg-preview-pgadmin.rule"], "Host(`pgadmin.example.test`)")
        self.assertEqual(pgadmin["environment"]["PGADMIN_CONFIG_SESSION_COOKIE_SECURE"], "True")
        self.assertEqual(set(config["services"]), {"postgres", "pgadmin"})
        self.assertTrue(config["networks"]["database"]["internal"])


if __name__ == "__main__":
    unittest.main()
