"""The operator-run shared stack (deploy/infrastructure) keeps the contract the deploy utility checks."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

import yaml

INFRASTRUCTURE = Path(__file__).resolve().parents[2] / "infrastructure"


class InfrastructureStackTests(unittest.TestCase):
    def test_example_env_lists_every_variable_the_stack_interpolates(self):
        compose = (INFRASTRUCTURE / "compose.yaml").read_text()
        interpolated = set(re.findall(r"\$\{([A-Z_]+)", compose))
        example = {line.split("=", 1)[0] for line in (INFRASTRUCTURE / "example.env").read_text().splitlines()
                   if line and not line.startswith("#")}
        self.assertEqual(interpolated, example)
        document = yaml.safe_load(compose)
        self.assertEqual(document["name"], "people-gator-preview-infra")  # existing volumes keep matching
        self.assertEqual(set(document["services"]), {"postgres", "traefik"})
        postgres = document["services"]["postgres"]
        self.assertEqual(postgres["container_name"], "postgres")
        self.assertEqual(postgres["networks"]["db"]["aliases"], ["postgres", "preview-postgres"])
        self.assertEqual((document["networks"]["db"]["name"], document["networks"]["web"]["name"]), ("db", "web"))
        self.assertNotIn("certresolver", compose)  # Traefik serves the operator's certificates

    @unittest.skipUnless(shutil.which("docker"), "Docker Compose not installed")
    def test_stack_keeps_the_database_private_and_routes_only_through_traefik(self):
        with tempfile.TemporaryDirectory() as certs:
            environment = {key: os.environ[key] for key in ("PATH", "HOME") if key in os.environ}
            environment.update(POSTGRES_PASSWORD="synthetic", CERTS_DIR=certs)
            result = subprocess.run(["docker", "compose", "-f", str(INFRASTRUCTURE / "compose.yaml"), "config", "--format", "json"],
                                    env=environment, text=True, capture_output=True, check=True)
        config = json.loads(result.stdout)
        postgres = config["services"]["postgres"]
        self.assertFalse(postgres.get("ports"))
        self.assertEqual(set(postgres["networks"]), {"db"})
        self.assertEqual(postgres["environment"]["POSTGRES_USER"], "postgres")
        self.assertTrue(config["networks"]["db"]["internal"])
        traefik = config["services"]["traefik"]
        self.assertEqual(set(traefik["networks"]), {"web"})
        self.assertEqual(sorted(port["published"] for port in traefik["ports"]), ["443", "80"])
        self.assertIn("--providers.docker.exposedbydefault=false", traefik["command"])
        self.assertIn("--entrypoints.websecure.address=:443", traefik["command"])
        socket = next(mount for mount in traefik["volumes"] if mount["target"] == "/var/run/docker.sock")
        self.assertTrue(socket["read_only"])


if __name__ == "__main__":
    unittest.main()
