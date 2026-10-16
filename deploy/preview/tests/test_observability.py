"""Optional Docker smoke test; uses only disposable containers and a private network."""

import base64
import json
import os
from pathlib import Path
import subprocess
import time
import unittest
import uuid


@unittest.skipUnless(os.environ.get("PREVIEW_TEST_OTEL"), "set PREVIEW_TEST_OTEL=1 for Docker log delivery test")
class LogDeliveryTests(unittest.TestCase):
    def docker(self, *args):
        return subprocess.run(["docker", *args], capture_output=True, text=True,
                              check=True, timeout=60).stdout.strip()

    def test_all_preview_services_deliver_logs_and_metadata_over_otlp(self):
        prefix = "pg-preview-test-" + uuid.uuid4().hex[:12]
        network, sink, collector = prefix, prefix + "-sink", prefix + "-collector"
        # Print decoded OTLP protobuf payloads as base64 for assertions, avoiding
        # a dependency on protobuf/OTel packages in the host controller test suite.
        server = """
import base64, gzip
from http.server import BaseHTTPRequestHandler, HTTPServer
class Sink(BaseHTTPRequestHandler):
    def do_POST(self):
        assert self.path == '/v1/logs', self.path
        data = self.rfile.read(int(self.headers['Content-Length']))
        if self.headers.get('Content-Encoding') == 'gzip':
            data = gzip.decompress(data)
        print(base64.b64encode(data).decode(), flush=True)
        self.send_response(200)
        self.send_header('Content-Length', '0')
        self.end_headers()
    def log_message(self, *args): pass
HTTPServer(('0.0.0.0', 4318), Sink).serve_forever()
"""
        config = Path(__file__).resolve().parents[1] / "otel-collector.yaml"
        try:
            self.docker("network", "create", network)
            self.docker("run", "-d", "--rm", "--name", sink, "--network", network,
                        "--network-alias", "sink", "python:3.12", "python", "-u", "-c", server)
            self.docker("run", "-d", "--rm", "--name", collector, "--network", network,
                        "--user", "0:0",
                        "-p", "127.0.0.1::24224", "-e", "OTEL_EXPORTER_OTLP_ENDPOINT=http://sink:4318",
                        "-v", f"{config}:/etc/otelcol/preview.yaml:ro",
                        "otel/opentelemetry-collector-contrib:0.162.0", "--config=/etc/otelcol/preview.yaml")
            inspected = json.loads(self.docker("inspect", collector))[0]
            port = inspected["NetworkSettings"]["Ports"]["24224/tcp"][0]["HostPort"]
            for service in ("frontend", "backend", "migrate", "seed", "storage-init"):
                self.docker("run", "--rm", "--network", "none",
                            "--label", "people-gator.preview.pr=123",
                            "--label", "people-gator.preview.sha=" + "a" * 40,
                            "--label", "com.docker.compose.service=" + service,
                            "--log-driver", "fluentd",
                            "--log-opt", f"fluentd-address=127.0.0.1:{port}",
                            "--log-opt", "fluentd-async=true",
                            "--log-opt", "fluentd-sub-second-precision=true",
                            "--log-opt", "labels=people-gator.preview.pr,people-gator.preview.sha,com.docker.compose.service",
                            "python:3.12", "python", "-c",
                            f"import sys; print('preview-smoke-{service}', flush=True); print('preview-stderr-{service}', file=sys.stderr, flush=True)")
            for service in ("frontend", "backend", "migrate", "check"):
                self.docker("run", "--rm", "--network", "none",
                            "--label", "people-gator.environment=staging",
                            "--label", "people-gator.staging.sha=" + "b" * 40,
                            "--label", "com.docker.compose.service=" + service,
                            "--log-driver", "fluentd", "--log-opt", f"fluentd-address=127.0.0.1:{port}",
                            "--log-opt", "fluentd-async=true",
                            "--log-opt", "labels=people-gator.environment,people-gator.staging.sha,com.docker.compose.service",
                            "python:3.12", "python", "-c", f"print('staging-smoke-{service}', flush=True)")
            deadline = time.monotonic() + 20
            payload = b""
            while time.monotonic() < deadline:
                payload = b"".join(base64.b64decode(line) for line in self.docker("logs", sink).splitlines())
                if all(f"preview-stderr-{name}".encode() in payload
                       for name in ("frontend", "backend", "migrate", "seed", "storage-init")) and b"staging-smoke-check" in payload:
                    break
                time.sleep(0.25)
            for service in ("frontend", "backend", "migrate", "seed", "storage-init"):
                self.assertIn(f"preview-smoke-{service}".encode(), payload,
                              self.docker("logs", collector))
                self.assertIn(f"preview-stderr-{service}".encode(), payload)
                self.assertIn(f"people-gator-preview.{service}".encode(), payload)
            for service in ("frontend", "backend", "migrate", "check"):
                self.assertIn(f"staging-smoke-{service}".encode(), payload, self.docker("logs", collector))
                self.assertIn(f"people-gator-staging.{service}".encode(), payload)
            self.assertIn(b"b" * 40, payload)
            self.assertIn(b"people-gator.environment", payload)
            for attribute in (b"people-gator.preview.pr", b"123", b"vcs.ref.head.revision",
                              b"a" * 40, b"log.iostream", b"stdout", b"stderr", b"container.id"):
                self.assertIn(attribute, payload)
        finally:
            for name in (collector, sink):
                subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=30)
            subprocess.run(["docker", "network", "rm", network], capture_output=True, timeout=30)


if __name__ == "__main__":
    unittest.main()
