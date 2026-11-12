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
        self.assertEqual(document["name"], "peoplegator-infra")
        self.assertEqual(set(document["services"]), {"postgres", "traefik"})
        postgres = document["services"]["postgres"]
        self.assertEqual(postgres["container_name"], "postgres")
        self.assertEqual(postgres["networks"], ["db"])
        self.assertEqual((document["networks"]["db"]["name"], document["networks"]["web"]["name"]), ("db", "web"))
        traefik = document["services"]["traefik"]
        # Older Traefik cannot talk to Docker Engine 29 ("client version 1.24 is too old").
        major, minor = map(int, traefik["image"].removeprefix("traefik:v").split(".")[:2])
        self.assertGreaterEqual((major, minor), (3, 6))
        self.assertEqual(traefik["command"], ["--configfile=/etc/traefik/traefik.yaml"])
        self.assertEqual(traefik["ports"], ["${HTTPS_PORT:-443}:443"])  # HTTPS only, on a chosen host port
        self.assertNotIn("certresolver", compose)  # certificates come from traefik.yaml's entry point
        labels = dict(label.split("=", 1) for label in traefik["labels"])
        # The dashboard is reachable only through its host name, behind basic auth.
        self.assertEqual(labels["traefik.http.routers.traefik-dashboard.service"], "api@internal")
        self.assertEqual(labels["traefik.http.routers.traefik-dashboard.rule"], "Host(`${TRAEFIK_DASHBOARD_HOST:-traefik-preview.peoplegator.dev}`)")
        self.assertEqual(labels["traefik.http.routers.traefik-dashboard.middlewares"], "traefik-dashboard-auth")
        self.assertEqual(labels["traefik.http.middlewares.traefik-dashboard-auth.basicauth.usersfile"], "/etc/traefik/dashboard.users")

    def test_example_traefik_config_serves_only_https_with_an_acme_resolver(self):
        config = yaml.safe_load((INFRASTRUCTURE / "traefik.example.yaml").read_text())
        # The application stacks route on `websecure`; there is no HTTP entry point.
        self.assertEqual(set(config["entryPoints"]), {"websecure"})
        websecure = config["entryPoints"]["websecure"]
        self.assertEqual(websecure["address"], ":443")
        # Per-host certificates on first request: no fixed domain list to maintain.
        self.assertEqual(websecure["http"]["tls"], {"certResolver": "letsencrypt"})
        self.assertEqual(config["providers"]["docker"], {"endpoint": "unix:///var/run/docker.sock", "exposedByDefault": False, "network": "web"})
        self.assertEqual(config["api"], {"dashboard": True})  # no `insecure`: only the authenticated router serves it
        acme = config["certificatesResolvers"]["letsencrypt"]["acme"]
        self.assertEqual(acme["storage"], "/acme/acme.json")  # the traefik-acme volume
        self.assertEqual(acme["tlsChallenge"], {})  # TLS-ALPN-01 on public 443: no HTTP port, no DNS credentials
        self.assertNotIn("httpChallenge", acme)
        self.assertNotIn("dnsChallenge", acme)

    def test_application_routers_inherit_tls_and_the_resolver_from_the_entry_point(self):
        # A router-level TLS setting (even `tls=true`) replaces the entry point's
        # TLS defaults, so such a router would get Traefik's default certificate
        # instead of one from the `letsencrypt` resolver in traefik.yaml.
        assets = Path(__file__).resolve().parents[1] / "src/people_gator_deploy/assets"
        for stack in sorted(assets.glob("compose*.yaml")):
            with self.subTest(stack=stack.name):
                text = stack.read_text()
                self.assertNotRegex(text, r"traefik\.http\.routers\.[^=\s]+\.tls")
                self.assertIn("entrypoints=websecure", text)

    @unittest.skipUnless(shutil.which("docker"), "Docker Compose not installed")
    def test_stack_keeps_the_database_private_and_routes_only_through_traefik(self):
        with tempfile.TemporaryDirectory() as private:
            config = Path(private) / "traefik.yaml"
            config.write_text((INFRASTRUCTURE / "traefik.example.yaml").read_text())
            environment = {key: os.environ[key] for key in ("PATH", "HOME") if key in os.environ}
            environment.update(POSTGRES_PASSWORD="synthetic", TRAEFIK_CONFIG=str(config), HTTPS_PORT="8443")
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
        self.assertEqual([(port["published"], port["target"]) for port in traefik["ports"]], [("8443", 443)])
        mounts = {mount["target"]: mount for mount in traefik["volumes"]}
        self.assertTrue(mounts["/var/run/docker.sock"]["read_only"])
        self.assertTrue(mounts["/etc/traefik/traefik.yaml"]["read_only"])
        self.assertEqual(mounts["/acme"]["type"], "volume")


if __name__ == "__main__":
    unittest.main()
