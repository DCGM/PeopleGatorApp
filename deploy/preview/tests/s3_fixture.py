"""Disposable TLS S3 providers for staging runtime tests; never real buckets."""
import json
from pathlib import Path
import secrets
import subprocess
import tempfile
import time


MINIO_IMAGE = "quay.io/minio/minio:RELEASE.2025-04-22T22-12-26Z"


class S3Fixture:
    def __init__(self, network):
        self.network = network
        self.names = []
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def __enter__(self):
        import boto3
        from botocore.config import Config
        certs = self.root / "certs"
        certs.mkdir()
        self.ca = certs / "public.crt"
        subprocess.run(["openssl", "req", "-x509", "-nodes", "-newkey", "rsa:2048", "-days", "1",
            "-keyout", str(certs / "private.key"), "-out", str(self.ca), "-subj", "/CN=staging-s3",
            "-addext", "subjectAltName=DNS:staging-s3,DNS:source-s3,IP:127.0.0.1"],
            capture_output=True, check=True)
        try:
            for kind in ("staging", "source"):
                name = "staging-test-s3-" + secrets.token_hex(8)
                self.names.append(name)
                secret = secrets.token_hex(24)
                subprocess.run(["docker", "run", "--rm", "-d", "--name", name, "--log-driver", "none",
                    "--network", self.network, "--network-alias", kind + "-s3", "-p", "127.0.0.1::9000",
                    "--tmpfs", "/data:size=256m", "--mount", f"type=bind,src={certs},dst=/certs,readonly",
                    "-e", "MINIO_ROOT_USER=fixture-" + kind, "-e", "MINIO_ROOT_PASSWORD=" + secret,
                    MINIO_IMAGE, "server", "/data", "--certs-dir", "/certs", "--address", ":9000"],
                    capture_output=True, check=True)
                port = subprocess.check_output(["docker", "inspect", "--format",
                    '{{(index (index .NetworkSettings.Ports "9000/tcp") 0).HostPort}}', name], text=True).strip()
                client = boto3.client("s3", endpoint_url="https://127.0.0.1:" + port,
                    region_name="us-east-1", aws_access_key_id="fixture-" + kind,
                    aws_secret_access_key=secret, verify=str(self.ca),
                    config=Config(connect_timeout=1, read_timeout=1, retries={"max_attempts": 0}))
                for attempt in range(50):
                    try:
                        client.list_buckets()
                        break
                    except Exception:
                        if attempt == 49:
                            raise
                        time.sleep(0.2)
                bucket = kind + "-fixture"
                client.create_bucket(Bucket=bucket)
                config = {"endpoint_url": f"https://{kind}-s3:9000", "region": "us-east-1",
                          "bucket_name": bucket, "access_key_id": "fixture-" + kind, "secret_access_key": secret}
                setattr(self, kind, client)
                setattr(self, kind + "_config", config)
            return self
        except Exception:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *args):
        for name in self.names:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        self.temporary.cleanup()

    def worker_command(self, controller):
        original = controller.command
        def command(args, *, sql=None):
            if args[:2] == ["docker", "run"]:
                args = [*args[:2], "--mount", f"type=bind,src={self.ca},dst=/test-ca.crt,readonly",
                        "--env", "AWS_CA_BUNDLE=/test-ca.crt", *args[2:]]
                if args[-1] == "download":
                    args = [*args[:2], "--network", self.network, *args[2:]]
            return original(args, sql=sql)
        return command

    def compose_override(self, path):
        path.write_text(json.dumps({"services": {name: {
            "logging": {"driver": "none"},
            "environment": {"AWS_CA_BUNDLE": "/test-ca.crt"},
            "labels": {"traefik.enable": "false"},
            "volumes": [{"type": "bind", "source": str(self.ca), "target": "/test-ca.crt", "read_only": True}],
        } for name in ("backend", "migrate", "check")}}))

    def objects(self):
        return {item["Key"]: self.staging.get_object(Bucket=self.staging_config["bucket_name"], Key=item["Key"])["Body"].read()
                for page in self.staging.get_paginator("list_objects_v2").paginate(Bucket=self.staging_config["bucket_name"])
                for item in page.get("Contents", [])}
